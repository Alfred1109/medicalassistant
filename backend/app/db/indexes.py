"""
索引基建：应用启动期统一声明通信域集合的唯一/辅助索引。

现有代码没有启动期建索引的统一惯例（health_alert_service 的 initialize()
从未被任何启动路径调用），本模块按最小基建落地：startup 事件里 connect_to_mongodb()
成功后调用 ensure_communication_indexes(db)。索引声明幂等（create_index 对已存在
的同名同参索引为 no-op），失败不阻断启动——此时幂等去重回退到应用层先查后插。

集合创建收敛：普通启动不隐式创建任何集合（messages 集合不存在时跳过索引声明）；
首个消息落库会隐式建集合，落库路径随后调用本模块惰性补建索引。
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
    """为通信域集合声明索引（启动期调用，幂等）。

    普通启动不产生未声明的集合写入（启动边界契约
    test_demo_auth_boundary.py::test_normal_startup_does_not_seed_any_accounts）：
    create_index 对不存在的集合会隐式创建集合（createCollection），因此仅在
    messages 集合已存在时才声明索引；空库场景跳过，索引由首个消息落库后的
    惰性初始化补建（见 CommunicationService.send_message），幂等去重能力不受影响。
    """
    try:
        existing = await db.list_collection_names()
    except Exception as e:
        # 存在性检查失败不阻断启动（与索引创建失败同策略）。
        logger.warning("通信集合存在性检查失败，跳过索引声明: %s", e)
        return
    if "messages" not in existing:
        logger.info(
            "messages 集合尚不存在：普通启动不隐式建集合，索引由首个消息落库路径惰性补建"
        )
        return
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
