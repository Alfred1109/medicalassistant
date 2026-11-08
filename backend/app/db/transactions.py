"""随访及其表单集成共享的 MongoDB 事务边界。"""
from pymongo.errors import PyMongoError
from pymongo.read_concern import ReadConcern
from pymongo.write_concern import WriteConcern

from app.core.exceptions import AppBaseException


async def run_followup_transaction(db, callback):
    """事务提交重试由驱动处理；不支持事务时拒绝，绝不顺序写入降级。"""
    if not hasattr(db, "client"):
        raise AppBaseException("数据库未提供事务会话", status_code=503,
                               error_code="FOLLOWUP_TRANSACTION_UNAVAILABLE")
    try:
        async with await db.client.start_session() as session:
            return await session.with_transaction(
                callback, read_concern=ReadConcern("snapshot"),
                write_concern=WriteConcern("majority"))
    except AppBaseException:
        raise
    except PyMongoError as exc:
        raise AppBaseException(
            "随访事务未能确认提交，请使用相同请求重试；数据库必须支持副本集事务",
            status_code=503, error_code="FOLLOWUP_TRANSACTION_UNAVAILABLE",
            details={"commit_result_unknown": bool(
                getattr(exc, "has_error_label", lambda _: False)("UnknownTransactionCommitResult"))}) from exc
