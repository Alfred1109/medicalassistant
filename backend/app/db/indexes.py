"""
索引基建：应用启动期统一声明通信域集合的唯一/辅助索引。

现有代码没有启动期建索引的统一惯例（health_alert_service 的 initialize()
从未被任何启动路径调用），本模块按最小基建落地：startup 事件里 connect_to_mongodb()
成功后调用 ensure_communication_indexes(db)。索引声明幂等（create_index 对已存在
的同名同参索引为 no-op），失败不阻断历史读取；新消息写入前必须成功建立索引。

集合创建收敛：普通启动不隐式创建任何集合（messages 集合不存在时跳过索引声明）；
首个写请求在落库前声明索引，失败时拒绝该写请求。
"""
import logging
from typing import Any

from pymongo import ASCENDING

logger = logging.getLogger(__name__)

# (conversation_id, sender_id, client_message_id) partial unique index：
# 仅对携带 client_message_id 的文档生效，支撑消息幂等键的 DB 层兜底
# （应用层先查后插之外，并发窗口内的重复投递由 DuplicateKeyError 拦截）。
# 注意：partialFilterExpression 仅支持 $exists: true，缺失字段的文档不进入索引。
MESSAGE_IDEMPOTENCY_INDEX_NAME = "uniq_conversation_sender_client_message_id"


class CommunicationStorageUnavailable(Exception):
    """The database cannot enforce the message-write contract."""


async def ensure_communication_indexes(db: Any, *, for_write: bool = False) -> bool:
    """Startup preserves empty stores; all new writes require the unique index.

    No process cache: databases/index state may change. History is never repaired.
    """
    try:
        if not for_write and "messages" not in await db.list_collection_names():
            return False
        await db.messages.create_index(
            [("conversation_id", ASCENDING), ("sender_id", ASCENDING),
             ("client_message_id", ASCENDING)],
            name=MESSAGE_IDEMPOTENCY_INDEX_NAME, unique=True,
            partialFilterExpression={"client_message_id": {"$exists": True}},
        )
    except Exception as error:
        logger.error("Message writes unavailable: required unique index could not be established")
        if for_write:
            raise CommunicationStorageUnavailable() from error
        return False
    return True
