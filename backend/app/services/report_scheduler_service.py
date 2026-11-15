"""
报表调度服务
处理报表的自动生成和分发

T53 死代码处置（兼容分析结论，详见 docs/t53-dead-code-disposal-report-scheduler.md）：
自仓库引入（dac0330，2025-05-10）起 start()/_scheduler_loop()/stop() 就没有任何
调用方——main.py 不启动它，路由只按请求实例化 ReportSchedulerService 做 CRUD
（report_scheduler_router.get_report_scheduler_service），部署脚本/文档也无引用，
属引入即死的调度路径。且 _scheduler_loop 是 fire-then-update：create_task 后立即
_update_next_run_time，无原子领取，启用即复刻 T34 发现的 D1 缺陷（多进程重复
执行）。据此删除 start()/stop()/_scheduler_loop() 三件套及其派生状态
（is_running/_scheduler_task）。

报表生成与发送的执行链（_process_schedule → _generate_report → _export_report /
_send_report_email）与 nextRunTime 计算保留：它们被领域收敛文档引用
（患者集合名登记于 PATIENTS_COLLECTION_NAME，见
docs/patient-domain-cutover-plan.md），且属待业务
决策的潜在复用件。但它们当前没有任何调度入口（死代码）——未来若要恢复后台
报表调度，必须先参照 T37 备份调度的 find_one_and_update 原子领取重写扫描领取
逻辑（filter 含到点条件、领取成功者才执行），再接入应用启动，否则会原样复刻
D1 重复执行缺陷。禁止单独恢复 _scheduler_loop。

3.4 伪实现下线（docs/business-redundancy-review-2026-11-15.md）：原
_export_report 把 JSON 写进 .pdf、把 CSV 写进 .excel——文件名承诺的格式与
内容不符，是「点得进去、拿到的永远是假东西」的空壳实现。现在 PDF/Excel 一律
如实拒绝（不再产出格式不符的文件），HTML 分支保持真实产出。恢复真报表导出
前不得改回写假文件的做法。
"""
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import logging
from bson import ObjectId
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
import tempfile
import os

from ..db.mongodb import get_db
from ..core.config import settings
from ..patients.repository import PATIENTS as CANONICAL_PATIENTS_COLLECTION
from .analytics_service import observe_patient_domain_state

# 患者域唯一集合名（legacy 模式：患者统一存于 users 集合，按 role 区分）。
# T66 域感知：legacy 分支仍读此常量（users + role 过滤，口径逐字不变）；
# canonical 分支改读 clinical_patients（集合名取自 patients/repository.py
# 的 PATIENTS 常量），按域分派见 _get_patient_stats。
PATIENTS_COLLECTION_NAME = "users"

# canonical 域患者聚合源：clinical_patients（与 analytics_service 同源
# patients/repository.PATIENTS 常量）；status=="active" 对齐 legacy
# users.is_active 语义（迁移映射见 patients/migration.project_legacy_patient）。
CANONICAL_PATIENTS_COLLECTION_NAME = CANONICAL_PATIENTS_COLLECTION

# 患者聚合源按域分派：mode -> (集合名, 过滤条件)。
# 口径差异声明（T12 审计）：legacy created_at = 账号注册时间；canonical 的
# created_at 对迁移患者继承 legacy 注册时间、对无账号患者（create_from_source）
# 是建档时间——「日新增患者」跨域不可比，域切换瞬间序列存在口径漂移（已知限制）。
_PATIENT_AGGREGATE_SPECS = {
    "legacy": (PATIENTS_COLLECTION_NAME, {"role": "patient"}),
    "canonical": (CANONICAL_PATIENTS_COLLECTION_NAME, {"status": "active"}),
}

logger = logging.getLogger(__name__)

class ReportSchedulerService:
    """报表调度服务：按请求实例化承载报表调度计划的 CRUD。

    当前不存在后台调度循环（T53 已删除引入即死的 start/_scheduler_loop/stop，
    见模块头注释）；本类实例只服务路由层的 CRUD 请求。
    """

    def __init__(self, db=None):
        """初始化报表调度服务"""
        self.db = db

    async def _database(self):
        """Use the request database when injected; retain standalone lifecycle support."""
        if self.db is None:
            self.db = await get_db()
        return self.db

    # 当前无调度入口（T53 死代码处置，见模块头注释）：以下执行链仅在「先按
    # T37 同款原子领取重写扫描逻辑」之后才允许被调度路径调用。
    async def _process_schedule(self, schedule: Dict[str, Any]):
        """处理单个调度任务"""
        schedule_id = str(schedule["_id"])
        report_id = schedule.get("reportId")
        
        logger.info(f"开始执行调度任务: {schedule_id}, 报表: {report_id}")
        
        try:
            # 获取报表配置
            report_config = await self.db.reports.find_one({"_id": ObjectId(report_id)})
            if not report_config:
                raise ValueError(f"找不到报表配置: {report_id}")
            
            # 生成报表数据
            report_data = await self._generate_report(report_config)
            
            # 根据格式导出报表
            report_format = schedule.get("format", "pdf")
            report_file = await self._export_report(report_data, report_format, report_config.get("title", "报表"))
            
            # 发送邮件
            if schedule.get("recipients") and len(schedule.get("recipients")) > 0:
                await self._send_report_email(
                    recipients=schedule["recipients"],
                    subject=f"自动报表: {report_config.get('title', '数据分析报表')}",
                    report_file=report_file,
                    report_format=report_format,
                    schedule_name=schedule.get("name", "自动报表"),
                    report_name=report_config.get("title", "数据分析报表")
                )
            
            # 更新执行状态
            await self.db.report_schedules.update_one(
                {"_id": ObjectId(schedule_id)},
                {"$set": {
                    "lastRunTime": datetime.utcnow(),
                    "lastRunStatus": "success"
                }}
            )
            
            logger.info(f"调度任务执行成功: {schedule_id}")
        except Exception as e:
            logger.error(f"调度任务执行失败: {schedule_id}, 错误: {str(e)}")
            
            # 更新执行状态为失败
            await self.db.report_schedules.update_one(
                {"_id": ObjectId(schedule_id)},
                {"$set": {
                    "lastRunTime": datetime.utcnow(),
                    "lastRunStatus": "error"
                }}
            )
    
    async def _update_next_run_time(self, schedule: Dict[str, Any]):
        """更新调度任务的下次执行时间"""
        schedule_id = schedule["_id"]
        frequency = schedule.get("frequency")
        now = datetime.utcnow()
        
        if frequency == "once":
            # 一次性任务执行后禁用
            await self.db.report_schedules.update_one(
                {"_id": schedule_id},
                {"$set": {"enabled": False}}
            )
            return
        
        # 计算下次执行时间
        next_run_time = None
        
        if frequency == "daily":
            # 获取配置的小时和分钟
            time_parts = schedule.get("time", "00:00").split(":")
            hour = int(time_parts[0])
            minute = int(time_parts[1])
            
            next_run_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if next_run_time <= now:
                next_run_time += timedelta(days=1)
        
        elif frequency == "weekly":
            weekday = schedule.get("weekday", 0)  # 0-6, 周日为0
            time_parts = schedule.get("time", "00:00").split(":")
            hour = int(time_parts[0])
            minute = int(time_parts[1])
            
            # 计算当前周几
            current_weekday = now.weekday()
            # 调整为周日为0的系统
            current_weekday = (current_weekday + 1) % 7
            
            # 计算距离下次执行的天数
            days_until_next = (weekday - current_weekday) % 7
            if days_until_next == 0:
                # 如果是同一天，但时间已过，则设为下周
                next_run_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                if next_run_time <= now:
                    days_until_next = 7
            
            next_run_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            next_run_time += timedelta(days=days_until_next)
        
        elif frequency == "monthly":
            month_day = schedule.get("monthDay", 1)  # 每月几号
            time_parts = schedule.get("time", "00:00").split(":")
            hour = int(time_parts[0])
            minute = int(time_parts[1])
            
            # 设置为本月指定日期
            next_run_time = now.replace(day=min(month_day, 28), hour=hour, minute=minute, second=0, microsecond=0)
            
            # 如果已过，则设为下月
            if next_run_time <= now:
                if now.month == 12:
                    next_run_time = next_run_time.replace(year=now.year+1, month=1)
                else:
                    next_run_time = next_run_time.replace(month=now.month+1)
        
        if next_run_time:
            await self.db.report_schedules.update_one(
                {"_id": schedule_id},
                {"$set": {"nextRunTime": next_run_time}}
            )
    
    async def _generate_report(self, report_config: Dict[str, Any]) -> Dict[str, Any]:
        """根据报表配置生成报表数据"""
        charts = report_config.get("charts", [])
        report_data = {
            "title": report_config.get("title", "数据分析报表"),
            "description": report_config.get("description", ""),
            "generated_at": datetime.utcnow(),
            "charts_data": []
        }
        
        for chart in charts:
            chart_type = chart.get("type")
            data_type = chart.get("dataType")
            time_range = chart.get("timeRange")
            
            # 根据图表类型和数据类型获取数据
            chart_data = await self._get_chart_data(chart_type, data_type, time_range)
            
            report_data["charts_data"].append({
                "title": chart.get("title", "图表"),
                "type": chart_type,
                "data": chart_data
            })
        
        return report_data
    
    async def _get_chart_data(self, chart_type: str, data_type: str, time_range: str) -> List[Dict[str, Any]]:
        """获取图表数据"""
        # 这里应该根据不同的数据类型调用相应的服务获取数据
        # 下面是一个示例实现
        
        days = self._time_range_to_days(time_range)
        
        if data_type == "patient":
            # 获取患者相关数据
            return await self._get_patient_stats(days)
        elif data_type == "device":
            # 获取设备相关数据
            return await self._get_device_stats(days)
        else:
            # 默认返回空数据
            return []
    
    def _time_range_to_days(self, time_range: str) -> int:
        """将时间范围转换为天数"""
        if time_range == "day":
            return 1
        elif time_range == "week":
            return 7
        elif time_range == "month":
            return 30
        elif time_range == "quarter":
            return 90
        elif time_range == "year":
            return 365
        else:
            return 30  # 默认为一个月
    
    async def _get_patient_stats(self, days: int) -> List[Dict[str, Any]]:
        """获取患者统计数据（患者聚合源按域分派，T66）。

        legacy：users + role=="patient"（原有管道逐字保留）；canonical：
        clinical_patients + status=="active"（含无账号患者）。created_at
        口径差异与域切换瞬间漂移见 _PATIENT_AGGREGATE_SPECS 注释。

        域状态读取失败/未知状态 fail-safe 返回 []（不猜测域，与
        analytics_service.observe_patient_domain_state 的 unknown 口径一致；
        纯列表响应无 unknown 通道，空序列与"无数据"不可区分属已知限制）。
        """
        mode = await observe_patient_domain_state(self.db)
        spec = _PATIENT_AGGREGATE_SPECS.get(mode)
        if spec is None:
            return []

        collection_name, match = spec
        start_date = datetime.utcnow() - timedelta(days=days)

        pipeline = [
            # 患者聚合源按域分派（legacy: PATIENTS_COLLECTION_NAME=users；
            # canonical: clinical_patients，见 _PATIENT_AGGREGATE_SPECS），
            # 聚合语义（按天分桶计数）不变
            {"$match": {**match, "created_at": {"$gte": start_date}}},
            {"$group": {
                "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}},
                "count": {"$sum": 1}
            }},
            {"$sort": {"_id": 1}}
        ]

        result = []
        async for doc in self.db[collection_name].aggregate(pipeline):
            result.append({
                "date": doc["_id"],
                "value": doc["count"]
            })
        
        return result
    
    async def _get_device_stats(self, days: int) -> List[Dict[str, Any]]:
        """获取设备统计数据"""
        start_date = datetime.utcnow() - timedelta(days=days)
        
        pipeline = [
            {"$match": {"timestamp": {"$gte": start_date}}},
            {"$group": {
                "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$timestamp"}},
                "count": {"$sum": 1},
                "avg_value": {"$avg": "$value"}
            }},
            {"$sort": {"_id": 1}}
        ]
        
        result = []
        async for doc in self.db.device_data.aggregate(pipeline):
            result.append({
                "date": doc["_id"],
                "count": doc["count"],
                "average": doc["avg_value"]
            })
        
        return result
    
    async def _export_report(self, report_data: Dict[str, Any], format: str, title: str) -> str:
        """导出报表为指定格式的文件。

        PDF/Excel 导出**未实现**（3.4 伪实现下线，见
        docs/business-redundancy-review-2026-11-15.md）：原实现把 JSON 写进
        .pdf、把 CSV 写进 .excel——文件名承诺的格式与内容不符，一旦被当成
        真报表消费就是坏文件。此处如实拒绝，不再产出格式不符的文件；待接入
        真正的 PDF/Excel 生成库后再放开。HTML 分支是真实产出，保持不变。

        本方法当前不可达（T53 已删除调度入口，见模块头注释）；恢复调度前须
        先满足模块头登记的原子领取前置条件。
        """
        if format in {"pdf", "excel"}:
            raise ValueError(f"报表格式 {format} 尚未实现，拒绝产出格式不符的文件")

        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{format}") as temp:
            # 生成简单的HTML报表
            html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <title>{title}</title>
                <style>
                    body {{ font-family: Arial, sans-serif; margin: 20px; }}
                    h1 {{ color: #333; }}
                    table {{ border-collapse: collapse; width: 100%; margin-bottom: 20px; }}
                    th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
                    th {{ background-color: #f2f2f2; }}
                    .chart-container {{ margin-bottom: 30px; }}
                </style>
            </head>
            <body>
                <h1>{title}</h1>
                <p>生成时间: {report_data['generated_at']}</p>
                <p>{report_data.get('description', '')}</p>
            """

            for chart in report_data["charts_data"]:
                html += f"""
                <div class="chart-container">
                    <h2>{chart['title']}</h2>
                    <table>
                        <thead>
                            <tr>
                """

                # 获取所有可能的列
                columns = set()
                for item in chart["data"]:
                    columns.update(item.keys())

                # 写入列头
                for col in columns:
                    html += f"<th>{col}</th>"
                html += "</tr></thead><tbody>"

                # 写入数据行
                for item in chart["data"]:
                    html += "<tr>"
                    for col in columns:
                        html += f"<td>{item.get(col, '')}</td>"
                    html += "</tr>"

                html += "</tbody></table></div>"

            html += "</body></html>"
            temp.write(html.encode('utf-8'))

            return temp.name
    
    async def _send_report_email(self, recipients: List[str], subject: str, report_file: str, 
                                report_format: str, schedule_name: str, report_name: str):
        """发送报表邮件"""
        if not settings.SMTP_HOST or not settings.SMTP_PORT:
            logger.error("SMTP配置缺失，无法发送邮件")
            return
        
        try:
            # 创建多部分邮件
            msg = MIMEMultipart()
            msg['From'] = settings.SMTP_SENDER
            msg['To'] = ", ".join(recipients)
            msg['Subject'] = subject
            
            # 添加邮件正文
            body = f"""
            <html>
            <body>
                <h2>自动报表: {report_name}</h2>
                <p>您订阅的自动报表 "{schedule_name}" 已生成，请查看附件。</p>
                <p>报表生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
                <p>此邮件由系统自动发送，请勿回复。</p>
            </body>
            </html>
            """
            msg.attach(MIMEText(body, 'html'))
            
            # 添加附件
            with open(report_file, "rb") as file:
                attachment = MIMEApplication(file.read())
                file_extension = report_format.lower()
                attachment.add_header(
                    "Content-Disposition", 
                    f"attachment; filename={report_name}_{datetime.now().strftime('%Y%m%d')}.{file_extension}"
                )
                msg.attach(attachment)
            
            # 连接SMTP服务器并发送
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
                if settings.SMTP_USE_TLS:
                    server.starttls()
                
                if settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
                    server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
                
                server.send_message(msg)
            
            logger.info(f"已成功发送报表邮件至 {len(recipients)} 位接收者")
        except Exception as e:
            logger.error(f"发送邮件失败: {str(e)}")
        finally:
            # 删除临时文件
            try:
                os.unlink(report_file)
            except:
                pass
    
    async def create_schedule(self, schedule_data: Dict[str, Any]) -> str:
        """创建新的报表调度计划"""
        await self._database()
        
        # 设置创建时间
        schedule_data["createdAt"] = datetime.utcnow()
        
        # 设置下次运行时间
        if schedule_data.get("frequency") == "once":
            schedule_data["nextRunTime"] = schedule_data.get("nextRunTime", datetime.utcnow())
        else:
            # 根据频率设置下次运行时间
            time_parts = schedule_data.get("time", "00:00").split(":")
            hour = int(time_parts[0])
            minute = int(time_parts[1])
            
            next_run = datetime.utcnow().replace(hour=hour, minute=minute, second=0, microsecond=0)
            
            if schedule_data.get("frequency") == "daily":
                if next_run <= datetime.utcnow():
                    next_run += timedelta(days=1)
            elif schedule_data.get("frequency") == "weekly":
                weekday = schedule_data.get("weekday", 0)
                days_until = (weekday - next_run.weekday() - 1) % 7
                if days_until == 0 and next_run <= datetime.utcnow():
                    days_until = 7
                next_run += timedelta(days=days_until)
            elif schedule_data.get("frequency") == "monthly":
                month_day = schedule_data.get("monthDay", 1)
                next_run = next_run.replace(day=min(month_day, 28))
                if next_run <= datetime.utcnow():
                    if next_run.month == 12:
                        next_run = next_run.replace(year=next_run.year+1, month=1)
                    else:
                        next_run = next_run.replace(month=next_run.month+1)
            
            schedule_data["nextRunTime"] = next_run
        
        # 插入记录
        result = await self.db.report_schedules.insert_one(schedule_data)
        return str(result.inserted_id)
    
    async def update_schedule(self, schedule_id: str, schedule_data: Dict[str, Any]) -> bool:
        """更新报表调度计划"""
        await self._database()
        
        # 移除不允许更新的字段
        for field in ["_id", "createdAt", "lastRunTime", "lastRunStatus"]:
            if field in schedule_data:
                del schedule_data[field]
        
        # 如果修改了频率相关设置，更新下次运行时间
        frequency_fields = ["frequency", "weekday", "monthDay", "time", "nextRunTime"]
        needs_update_next_run = any(field in schedule_data for field in frequency_fields)
        
        if needs_update_next_run:
            # 获取完整的计划数据
            current_schedule = await self.db.report_schedules.find_one({"_id": ObjectId(schedule_id)})
            if not current_schedule:
                return False
            
            # 合并新的数据
            updated_schedule = {**current_schedule, **schedule_data}
            
            # 根据新的频率设置计算下次运行时间
            if updated_schedule.get("frequency") == "once":
                if "nextRunTime" in schedule_data:
                    updated_schedule["nextRunTime"] = schedule_data["nextRunTime"]
                else:
                    updated_schedule["nextRunTime"] = datetime.utcnow()
            else:
                # 根据频率设置下次运行时间
                time_parts = updated_schedule.get("time", "00:00").split(":")
                hour = int(time_parts[0])
                minute = int(time_parts[1])
                
                next_run = datetime.utcnow().replace(hour=hour, minute=minute, second=0, microsecond=0)
                
                if updated_schedule.get("frequency") == "daily":
                    if next_run <= datetime.utcnow():
                        next_run += timedelta(days=1)
                elif updated_schedule.get("frequency") == "weekly":
                    weekday = updated_schedule.get("weekday", 0)
                    days_until = (weekday - next_run.weekday() - 1) % 7
                    if days_until == 0 and next_run <= datetime.utcnow():
                        days_until = 7
                    next_run += timedelta(days=days_until)
                elif updated_schedule.get("frequency") == "monthly":
                    month_day = updated_schedule.get("monthDay", 1)
                    next_run = next_run.replace(day=min(month_day, 28))
                    if next_run <= datetime.utcnow():
                        if next_run.month == 12:
                            next_run = next_run.replace(year=next_run.year+1, month=1)
                        else:
                            next_run = next_run.replace(month=next_run.month+1)
                
                schedule_data["nextRunTime"] = next_run
        
        # 更新记录
        result = await self.db.report_schedules.update_one(
            {"_id": ObjectId(schedule_id)},
            {"$set": schedule_data}
        )
        
        return result.modified_count > 0
    
    async def delete_schedule(self, schedule_id: str) -> bool:
        """删除报表调度计划"""
        await self._database()
        result = await self.db.report_schedules.delete_one({"_id": ObjectId(schedule_id)})
        return result.deleted_count > 0
    
    async def get_schedule(self, schedule_id: str) -> Optional[Dict[str, Any]]:
        """获取单个报表调度计划"""
        await self._database()
        schedule = await self.db.report_schedules.find_one({"_id": ObjectId(schedule_id)})
        if schedule:
            schedule["_id"] = str(schedule["_id"])
        return schedule
    
    async def get_schedules(self, user_id: Optional[str] = None, report_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取报表调度计划列表"""
        await self._database()
        
        query = {}
        if user_id:
            query["createdBy"] = user_id
        if report_id:
            query["reportId"] = report_id
        
        schedules = []
        async for schedule in self.db.report_schedules.find(query).sort("createdAt", -1):
            schedule["_id"] = str(schedule["_id"])
            schedules.append(schedule)
        
        return schedules
    
    async def toggle_schedule(self, schedule_id: str, enabled: bool) -> bool:
        """启用或禁用报表调度计划"""
        await self._database()
        result = await self.db.report_schedules.update_one(
            {"_id": ObjectId(schedule_id)},
            {"$set": {"enabled": enabled}}
        )
        return result.modified_count > 0


# 创建服务实例
report_scheduler_service = ReportSchedulerService()
