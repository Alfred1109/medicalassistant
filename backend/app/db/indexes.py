"""
索引基建：应用启动期统一声明通信域集合的唯一/辅助索引。

现有代码没有启动期建索引的统一惯例（health_alert_service 的 initialize()
从未被任何启动路径调用），本模块按最小基建落地：startup 事件里 connect_to_mongodb()
成功后调用 ensure_communication_indexes(db)。索引声明幂等（create_index 对已存在
的同名同参索引为 no-op），失败不阻断启动——此时幂等去重回退到应用层先查后插。
"""
import logging
from typing import Any, Dict

from pymongo import ASCENDING
from pymongo.errors import OperationFailure

logger = logging.getLogger(__name__)

# (conversation_id, sender_id, client_message_id) partial unique index：
# 仅对携带 client_message_id 的文档生效，支撑消息幂等键的 DB 层兜底
# （应用层先查后插之外，并发窗口内的重复投递由 DuplicateKeyError 拦截）。
# 注意：partialFilterExpression 仅支持 $exists: true，缺失字段的文档不进入索引。
MESSAGE_IDEMPOTENCY_INDEX_NAME = "uniq_conversation_sender_client_message_id"


async def ensure_communication_indexes(db: Any) -> None:
    """为通信域集合声明索引（启动期调用，幂等）。"""
    try:
        await db.messages.create_index(
            [
                ("conversation_id", ASCENDING),
                ("sender_id", ASCENDING),
                ("client_message_id", ASCENDING),
            ],
            name=MESSAGE_IDEMPOTENCY_INDEX_NAME,
            unique=True,
            partialFilterExpression={"client_message_id": {"$exists": True}},
        )
        logger.info("通信集合索引已就绪: %s", MESSAGE_IDEMPOTENCY_INDEX_NAME)
    except OperationFailure as e:
        # 典型场景：存量数据已含重复 client_message_id，唯一索引建不出来。
        # 不阻断启动，幂等去重退化为应用层先查后插。
        logger.warning("通信集合索引创建失败，幂等去重退化为应用层查重: %s", e)
