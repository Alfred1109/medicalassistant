"""
数据库连接模块
提供MongoDB连接功能
"""
from motor.motor_asyncio import AsyncIOMotorClient
from ..core.config import settings

# 全局数据库连接对象
_client = None

async def get_database():
    """获取数据库连接"""
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(settings.MONGODB_URL)
    return _client[settings.MONGODB_DB_NAME]

async def close_database_connection():
    """关闭数据库连接"""
    global _client
    if _client is not None:
        _client.close()
        _client = None 