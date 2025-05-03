"""
数据库连接模块
提供MongoDB连接的管理和访问
"""
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from typing import AsyncGenerator, Optional
import logging
from app.core.config import settings

logger = logging.getLogger(__name__)

class DatabaseConnectionError(Exception):
    """数据库连接异常"""
    pass

class Database:
    """数据库连接管理类"""
    client: Optional[AsyncIOMotorClient] = None
    db: Optional[AsyncIOMotorDatabase] = None
    
    def is_connected(self) -> bool:
        """检查数据库是否已连接"""
        return self.client is not None and self.db is not None
    
    async def ping(self) -> bool:
        """检查数据库连接是否正常"""
        if not self.is_connected():
            return False
        
        try:
            # 使用MongoDB的ping命令检查连接是否正常
            await self.db.command('ping')
            return True
        except Exception as e:
            logger.error(f"数据库ping失败: {str(e)}")
            return False
    
db = Database()

async def get_database() -> AsyncGenerator:
    """获取数据库连接"""
    if not db.is_connected():
        await connect_to_mongodb()
    
    if not await db.ping():
        logger.warning("检测到数据库连接异常，尝试重新连接")
        await connect_to_mongodb()
        
        if not await db.ping():
            raise DatabaseConnectionError("无法连接到MongoDB数据库")
    
    yield db.db

async def connect_to_mongodb():
    """连接到MongoDB"""
    try:
        logger.info(f"正在连接到MongoDB: {settings.MONGODB_URL}...")
        # 设置连接参数
        db.client = AsyncIOMotorClient(
            settings.MONGODB_URL,
            maxPoolSize=settings.MONGODB_MAX_CONNECTIONS,
            minPoolSize=settings.MONGODB_MIN_CONNECTIONS,
            maxIdleTimeMS=settings.MONGODB_MAX_IDLE_TIME_MS,
            waitQueueTimeoutMS=settings.MONGODB_WAIT_QUEUE_TIMEOUT_MS,
            connectTimeoutMS=settings.MONGODB_CONNECT_TIMEOUT_MS,
            retryWrites=True,
            serverSelectionTimeoutMS=settings.MONGODB_SERVER_SELECTION_TIMEOUT_MS
        )
        db.db = db.client[settings.MONGODB_DB_NAME]
        
        # 验证连接
        await db.ping()
        logger.info("成功连接到MongoDB")
    except Exception as e:
        logger.error(f"连接MongoDB失败: {str(e)}")
        raise DatabaseConnectionError(f"无法连接到MongoDB: {str(e)}")
    
async def close_mongodb_connection():
    """关闭MongoDB连接"""
    if db.client:
        logger.info("关闭MongoDB连接")
        db.client.close()
        db.client = None
        db.db = None 