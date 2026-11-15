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


# 患者归属域的普通辅助索引：仅加速既有查询（devices.patient_id 此前无任何
# 索引）。全部为非唯一普通索引，不依赖任何未知现有数据的取值假设，也不参与
# 迁移唯一性校验。
# clinical_patient_name_query（clinical_patients.name）不在此声明：该索引
# 单一属主为 patients/repository.create_patient_indexes（canonical 迁移/
# 维护脚本路径），避免双声明收敛前的重复维护点。
PATIENT_SCOPE_INDEXES = (
    ("devices", [("patient_id", ASCENDING)], "device_patient_query"),
)


async def ensure_patient_scope_indexes(db: Any) -> bool:
    """声明患者归属域普通辅助索引；集合不存在时跳过（不隐式建集合）。

    与 ensure_communication_indexes 同一惯例：索引声明幂等，失败只记录日志
    不阻断历史读取。clinical_patients 的全部索引（唯一索引与姓名查询索引
    clinical_patient_name_query）单一属主为
    patients/repository.create_patient_indexes；本函数仅负责 devices 等无
    迁移脚本属主的集合补齐查询索引。
    """
    try:
        names = await db.list_collection_names()
        for collection, keys, name in PATIENT_SCOPE_INDEXES:
            if collection not in names:
                continue
            await db[collection].create_index(keys, name=name)
    except Exception as error:
        logger.error("Patient scope indexes could not be established: %s", error)
        return False
    return True
