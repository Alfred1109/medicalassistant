"""
设备维修服务
提供设备维修记录管理和查询功能
"""
from typing import Dict, List, Optional, Any
from datetime import datetime
from bson import ObjectId

from ..db.mongodb import get_db
from ..models.device_repair_log import DeviceRepairLog

class DeviceRepairService:
    """设备维修服务类"""
    
    async def get_repair_history(
        self, 
        device_id: Optional[str] = None, 
        limit: int = 20
    ) -> List[Dict]:
        """
        获取设备维修历史
        
        参数:
        - device_id: 可选的设备ID，如果提供则只返回特定设备的维修历史
        - limit: 返回的记录数量限制
        
        返回:
        - 维修历史记录列表
        """
        db = await get_db()
        query = {}
        if device_id:
            query["device_id"] = device_id
            
        repair_logs = await db.device_repair_logs.find(query).sort(
            "repair_time", -1
        ).limit(limit).to_list(None)
        
        # 转换ObjectId为字符串
        for log in repair_logs:
            if "_id" in log:
                log["_id"] = str(log["_id"])
                
        return repair_logs
    
    async def create_repair_log(self, repair_data: Dict) -> Dict:
        """
        创建设备维修记录
        
        参数:
        - repair_data: 维修记录数据
        
        返回:
        - 创建的维修记录
        """
        db = await get_db()
        
        # 确保包含必要字段
        if "device_id" not in repair_data:
            raise ValueError("缺少必要字段: device_id")
            
        # 添加时间戳
        if "repair_time" not in repair_data:
            repair_data["repair_time"] = datetime.utcnow()
            
        result = await db.device_repair_logs.insert_one(repair_data)
        repair_data["_id"] = str(result.inserted_id)
        
        return repair_data
        
    async def get_repair_stats(self, device_id: Optional[str] = None) -> Dict:
        """
        获取设备维修统计信息
        
        参数:
        - device_id: 可选的设备ID
        
        返回:
        - 维修统计信息
        """
        db = await get_db()
        match_stage = {}
        if device_id:
            match_stage["device_id"] = device_id
            
        pipeline = [
            {"$match": match_stage},
            {"$group": {
                "_id": "$device_type",
                "count": {"$sum": 1},
                "success_count": {"$sum": {"$cond": ["$overall_success", 1, 0]}},
                "fail_count": {"$sum": {"$cond": ["$overall_success", 0, 1]}},
                "avg_repair_time": {"$avg": {"$toDouble": {"$subtract": [
                    {"$ifNull": ["$repair_end_time", datetime.utcnow()]}, 
                    "$repair_time"
                ]}}}
            }},
            {"$project": {
                "device_type": "$_id",
                "total_repairs": "$count",
                "success_rate": {"$divide": ["$success_count", "$count"]},
                "avg_repair_time_ms": "$avg_repair_time",
                "_id": 0
            }}
        ]
        
        stats = await db.device_repair_logs.aggregate(pipeline).to_list(None)
        
        # 如果没有找到数据，返回空统计信息
        if not stats:
            return {
                "total_repairs": 0,
                "success_rate": 0,
                "by_device_type": []
            }
            
        # 计算总体统计信息
        total_repairs = sum(stat["total_repairs"] for stat in stats)
        success_rate = sum(stat["success_rate"] * stat["total_repairs"] for stat in stats) / total_repairs if total_repairs > 0 else 0
        
        return {
            "total_repairs": total_repairs,
            "success_rate": success_rate,
            "by_device_type": stats
        }

# 单例实例
device_repair_service = DeviceRepairService() 