from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from pymongo.database import Database


class AnalyticsService:
    """数据分析和可视化服务

    诚实数据约定（2026-11-08 修复）：
    - 所有指标均来自真实集合聚合；当前无数据源支撑的指标返回 0 / 空序列，
      并通过 dataAvailable 标记显式声明不可用，绝不返回随机模拟值；
    - 任何异常如实上抛（由路由层转 500），不再回退模拟数据。
    """

    def __init__(self, db: Database):
        """初始化数据分析服务

        Args:
            db: MongoDB数据库连接
        """
        self.db = db
        # 患者与医生统一存于 users 集合（User.collection_name），按 role 区分；
        # patients/doctors 为无写入路径的遗留集合名，读取收敛到唯一集合
        self.patients_collection = db.users
        self.doctors_collection = db.users
        self.devices_collection = db.devices
        # TODO(orphan-read, 待业务决策): rehabilitation_records 是无写入方的孤儿集合
        # （BASE03 集合收敛 9133342 已确认全库（含历史提交 65e990b 引入时）不存在任何
        # 写入路径；migrate_legacy_collections.py 将其列为 REPORT_ONLY 待人工决策）。
        # 此处读取期望的文档形状：含数值型 duration（分钟）的训练记录，仅支撑
        # get_stats_overview 的 avgTrainingTime 指标（消费端点 GET /system/visualization/overview）。
        # 现存唯一集合 rehab_plans / rehab_progress / rehab_assessments 的字段形状
        # 均不匹配（无每文档数值 duration），不做猜测映射。
        # 空集合时下方循环不执行，avgTrainingTime 安全回退为 0，端点返回 200。
        # 待决策项：新建"训练记录"写入域后改指唯一集合；或改由 rehab_plans 的
        # exercises[].progress 聚合计算；或确认废弃该指标后删除此引用。
        self.rehabilitation_collection = db.rehabilitation_records

    # 趋势/对比聚合的数据源：data_type -> (集合名, 附加过滤条件)
    # 患者与医生均来自 users 集合（按 role 区分）；设备、康复计划各归唯一集合
    _TREND_SOURCES = {
        "patient": ("users", {"role": "patient"}),
        "doctor": ("users", {"role": "doctor"}),
        "device": ("devices", {}),
        "rehabilitation": ("rehab_plans", {}),
    }

    # 趋势窗口配置：time_range -> (桶数量, 桶单位, $dateToString 格式)
    _TREND_BUCKETS = {
        "day": (24, "hour", "%Y-%m-%dT%H:00:00"),
        "week": (7, "day", "%Y-%m-%d"),
        "month": (30, "day", "%Y-%m-%d"),
        "quarter": (90, "day", "%Y-%m-%d"),
        "year": (12, "month", "%Y-%m"),
    }

    # 分布聚合的数据源：data_type -> (集合名, 过滤条件, 分组字段表达式)
    # 分组字段均为文档真实存在的字段，缺省值在结果中归入"未填写"，不发明业务分类
    _DISTRIBUTION_SOURCES = {
        "patient": ("users", {"role": "patient"}, "$demographic_info.gender"),
        "doctor": ("users", {"role": "doctor"}, "$department"),
        "device": ("devices", {}, "$device_type"),
        "rehabilitation": ("rehab_plans", {}, "$status"),
    }

    # 对比聚合的数据源：data_type -> (集合名, 过滤条件, 类别标签)
    # 对比语义：该实体在当前窗口的"新增数量" vs 对比窗口的"新增数量"
    _COMPARISON_SOURCES = {
        "patient": ("users", {"role": "patient"}, "新增患者"),
        "doctor": ("users", {"role": "doctor"}, "新增医生"),
        "device": ("devices", {}, "新增设备"),
        "rehabilitation": ("rehab_plans", {}, "新增康复计划"),
    }

    # 对比窗口长度：time_range -> 当前统计窗口时长
    _COMPARISON_WINDOW = {
        "day": timedelta(hours=24),
        "week": timedelta(days=7),
        "month": timedelta(days=30),
        "quarter": timedelta(days=90),
        "year": timedelta(days=365),
    }

    @classmethod
    def _trend_bucket_starts(cls, time_range: str) -> List[datetime]:
        """按 time_range 计算趋势序列各桶的起始时间（升序，含当前桶）。"""
        count, unit, _fmt = cls._TREND_BUCKETS[time_range]
        now = datetime.utcnow()
        if unit == "hour":
            hour0 = now.replace(minute=0, second=0, microsecond=0)
            return [hour0 - timedelta(hours=count - 1 - i) for i in range(count)]
        if unit == "day":
            day0 = now.replace(hour=0, minute=0, second=0, microsecond=0)
            return [day0 - timedelta(days=count - 1 - i) for i in range(count)]
        # month：自然月对齐
        this_month_index = now.year * 12 + (now.month - 1)
        starts = []
        for i in range(count):
            total = this_month_index - (count - 1 - i)
            year, month0 = divmod(total, 12)
            starts.append(datetime(year, month0 + 1, 1))
        return starts

    async def get_stats_overview(self) -> Dict[str, Any]:
        """获取系统统计数据概览

        所有字段均为真实集合聚合；异常如实上抛（不回退模拟数据）。

        Returns:
            包含各种统计数据的字典；rehabilitationRate / patientSatisfaction
            当前无真实数据源，恒为 0 并在 dataAvailable 中标记为不可用
        """
        # 计算患者数量
        patient_count = await self.patients_collection.count_documents({"role": "patient"})

        # 计算医生数量
        doctor_count = await self.doctors_collection.count_documents({"role": "doctor"})

        # 计算设备数量
        device_count = await self.devices_collection.count_documents({})

        # 计算活跃设备比例
        active_devices = await self.devices_collection.count_documents({"status": "active"})
        active_device_rate = (active_devices / device_count * 100) if device_count > 0 else 0

        # 计算一周内的患者增长率
        one_week_ago = datetime.utcnow() - timedelta(days=7)
        previous_patient_count = await self.patients_collection.count_documents(
            {"role": "patient", "created_at": {"$lt": one_week_ago}}
        )
        week_patient_change = ((patient_count - previous_patient_count) / previous_patient_count * 100) if previous_patient_count > 0 else 0

        # 计算平均训练时间（分钟）
        rehab_records = self.rehabilitation_collection.find({})
        total_duration = 0
        record_count = 0

        async for record in rehab_records:
            if "duration" in record:
                total_duration += record.get("duration", 0)
                record_count += 1

        avg_training_time = total_duration / record_count if record_count > 0 else 0

        return {
            "patientCount": patient_count,
            "weekPatientChange": round(week_patient_change, 1),
            "doctorCount": doctor_count,
            "totalDevices": device_count,
            "activeDeviceRate": round(active_device_rate, 1),
            "avgTrainingTime": round(avg_training_time, 1),
            # 康复有效率/患者满意度：全库无疗效评定与满意度评价的写入路径，
            # 无真实数据源，如实返回 0 并显式标记不可用（此前为硬编码模拟值 68/92）
            "rehabilitationRate": 0,
            "patientSatisfaction": 0,
            "dataAvailable": {
                "rehabilitationRate": False,
                "patientSatisfaction": False,
            },
        }

    async def get_trend_data(self, data_type: str, time_range: str) -> List[Dict[str, Any]]:
        """获取趋势数据

        语义：对应实体按 created_at 落库时间的"新增数量"时间序列
        （patient/doctor -> users 按 role，device -> devices，rehabilitation -> rehab_plans）。
        缺少 created_at（或 created_at 非日期类型）的历史文档不计入，桶内无数据补 0。
        未知 data_type / time_range 返回空列表（不伪造序列）；异常如实上抛。

        Args:
            data_type: 数据类型 (patient, doctor, device, rehabilitation)
            time_range: 时间范围 (day, week, month, quarter, year)

        Returns:
            趋势数据列表 [{timestamp, value}, ...]
        """
        source = self._TREND_SOURCES.get(data_type)
        if source is None or time_range not in self._TREND_BUCKETS:
            return []

        collection_name, extra_match = source
        _count, _unit, fmt = self._TREND_BUCKETS[time_range]
        starts = self._trend_bucket_starts(time_range)

        pipeline = [
            {"$match": {
                **extra_match,
                # $type: "date" 排除遗留字符串日期，避免 $dateToString 对非日期类型报错
                "created_at": {"$gte": starts[0], "$type": "date"},
            }},
            {"$group": {
                "_id": {"$dateToString": {"format": fmt, "date": "$created_at"}},
                "count": {"$sum": 1},
            }},
        ]
        rows = await self.db[collection_name].aggregate(pipeline).to_list(length=None)
        counts = {row["_id"]: row["count"] for row in rows}

        return [
            {"timestamp": start.isoformat(), "value": counts.get(start.strftime(fmt), 0)}
            for start in starts
        ]

    async def get_distribution_data(self, data_type: str, time_range: str) -> List[Dict[str, Any]]:
        """获取分布数据

        语义：对应实体集合当前总体按真实字段的分组计数（不做时间切片，
        time_range 参数仅为 API 兼容保留）。字段缺失/空值归入"未填写"。
        未知 data_type 返回空列表；异常如实上抛。

        Args:
            data_type: 数据类型 (patient, doctor, device, rehabilitation)
            time_range: 时间范围（仅兼容保留，不影响结果）

        Returns:
            分布数据列表 [{category, value}, ...]，按 value 降序
        """
        source = self._DISTRIBUTION_SOURCES.get(data_type)
        if source is None:
            return []

        collection_name, match, field_expr = source
        pipeline = [
            {"$match": match},
            {"$group": {
                "_id": {"$ifNull": [field_expr, None]},
                "value": {"$sum": 1},
            }},
            {"$sort": {"value": -1}},
        ]
        rows = await self.db[collection_name].aggregate(pipeline).to_list(length=None)

        result = []
        for row in rows:
            category = row["_id"]
            if category is None or category == "":
                category = "未填写"
            result.append({"category": category, "value": row["value"]})
        return result

    async def get_comparison_data(self, data_type: str, time_range: str, compare_with: str) -> List[Dict[str, Any]]:
        """获取对比数据

        语义：对应实体在当前窗口（按 time_range）的"新增数量"与对比窗口的
        "新增数量"对比。compare_with=lastPeriod 为紧邻的等长上一窗口，
        lastYear 为一年前的等长窗口，target 无真实目标值数据源返回 null。
        未知 data_type / time_range 返回空列表；未知 compare_with 上抛 ValueError；
        异常如实上抛。

        Args:
            data_type: 数据类型 (patient, doctor, device, rehabilitation)
            time_range: 时间范围 (day, week, month, quarter, year)
            compare_with: 对比对象 (lastPeriod, lastYear, target)

        Returns:
            对比数据列表 [{category, currentValue, compareValue}, ...]
        """
        source = self._COMPARISON_SOURCES.get(data_type)
        if source is None or time_range not in self._COMPARISON_WINDOW:
            return []

        collection_name, extra_match, label = source
        window = self._COMPARISON_WINDOW[time_range]
        now = datetime.utcnow()
        current_start = now - window

        current_value = await self.db[collection_name].count_documents(
            {**extra_match, "created_at": {"$gte": current_start, "$type": "date"}}
        )

        if compare_with == "target":
            # 无真实目标值数据源，返回 null 而非伪造目标
            compare_value = None
        else:
            if compare_with == "lastPeriod":
                prev_start, prev_end = current_start - window, current_start
            elif compare_with == "lastYear":
                prev_start, prev_end = current_start - timedelta(days=365), current_start
            else:
                raise ValueError(f"不支持的对比对象: {compare_with}")
            compare_value = await self.db[collection_name].count_documents(
                {**extra_match,
                 "created_at": {"$gte": prev_start, "$lt": prev_end, "$type": "date"}}
            )

        return [{
            "category": label,
            "currentValue": current_value,
            "compareValue": compare_value,
        }]
