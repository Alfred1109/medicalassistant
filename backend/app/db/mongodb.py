"""
数据库连接模块
提供MongoDB连接的管理和访问
"""
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from typing import AsyncGenerator, Optional
import asyncio
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
_connection_lock = asyncio.Lock()

async def get_database() -> AsyncGenerator:
    """获取数据库连接"""
    yield await get_db()

# 为了向后兼容，添加get_db函数作为get_database的别名
async def get_db() -> AsyncIOMotorDatabase:
    """获取数据库连接 (get_database的别名)"""
    if not db.is_connected():
        await connect_to_mongodb()
    
    if not await db.ping():
        # Motor 复用连接池并自动重新选择服务器；保留已交付的句柄，
        # 避免并发请求关闭彼此使用的 client。
        raise DatabaseConnectionError("无法连接到MongoDB数据库")
    
    return db.db

async def connect_to_mongodb():
    """验证连接后才发布数据库句柄，失败时关闭候选连接。"""
    async with _connection_lock:
        if db.is_connected():
            if not await db.ping():
                raise DatabaseConnectionError("无法连接到MongoDB")
            return
        candidate = None
        try:
            # URI 可能包含凭据，不写入日志。
            logger.info("正在连接到MongoDB...")
            candidate = AsyncIOMotorClient(
                settings.MONGODB_URL,
                maxPoolSize=settings.MONGODB_MAX_CONNECTIONS,
                minPoolSize=settings.MONGODB_MIN_CONNECTIONS,
                maxIdleTimeMS=settings.MONGODB_MAX_IDLE_TIME_MS,
                waitQueueTimeoutMS=settings.MONGODB_WAIT_QUEUE_TIMEOUT_MS,
                connectTimeoutMS=settings.MONGODB_CONNECT_TIMEOUT_MS,
                retryWrites=True,
                serverSelectionTimeoutMS=settings.MONGODB_SERVER_SELECTION_TIMEOUT_MS
            )
            candidate_db = candidate[settings.MONGODB_DB_NAME]
            await candidate_db.command('ping')
            db.client, db.db = candidate, candidate_db
            candidate = None
            logger.info("成功连接到MongoDB")
        except Exception as e:
            logger.error("连接MongoDB失败: %s", type(e).__name__)
            raise DatabaseConnectionError("无法连接到MongoDB") from e
        finally:
            # 包含异步取消：未发布的候选句柄必须释放，取消原样传播。
            if candidate is not None:
                candidate.close()
    
async def close_mongodb_connection():
    """关闭MongoDB连接"""
    async with _connection_lock:
        if db.client is not None:
            logger.info("关闭MongoDB连接")
            db.client.close()
            db.client = None
            db.db = None
