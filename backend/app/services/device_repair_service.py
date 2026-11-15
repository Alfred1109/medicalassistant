"""
设备维修服务
提供设备维修记录管理和查询功能
"""
from typing import Dict, List, Optional

from ..db.mongodb import get_db
from ..models.device_repair_log import DeviceRepairLog

class DeviceRepairService:
    """设备维修服务类"""
    
    def __init__(self, db=None):
        self.db = db

    async def _database(self):
        return self.db if self.db is not None else await get_db()

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
        db = await self._database()
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

# 单例实例
device_repair_service = DeviceRepairService()