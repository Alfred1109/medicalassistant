"""MongoDB transaction execution shared by business domains.

Domains retain their error codes and messages; driver retries and uncertain
commit outcomes have one implementation. No domain falls back to sequential
writes when transactions are unavailable.
"""
from pymongo.errors import PyMongoError
from pymongo.read_concern import ReadConcern
from pymongo.write_concern import WriteConcern

from app.core.exceptions import AppBaseException


async def run_transaction(db, callback, *, error_code, error_message):
    """Execute an atomic callback and preserve the driver's commit ambiguity."""
    if not hasattr(db, "client"):
        raise AppBaseException("数据库未提供事务会话", status_code=503,
                               error_code=error_code)
    try:
        async with await db.client.start_session() as session:
            return await session.with_transaction(
                callback, read_concern=ReadConcern("snapshot"),
                write_concern=WriteConcern("majority"))
    except AppBaseException:
        raise
    except PyMongoError as exc:
        raise AppBaseException(
            error_message,
            status_code=503, error_code=error_code,
            details={"commit_result_unknown": bool(
                getattr(exc, "has_error_label", lambda _: False)("UnknownTransactionCommitResult"))}) from exc


async def run_followup_transaction(db, callback):
    """Compatibility entry point with the follow-up domain's public errors."""
    return await run_transaction(db, callback,
        error_code="FOLLOWUP_TRANSACTION_UNAVAILABLE",
        error_message="随访事务未能确认提交，请使用相同请求重试；数据库必须支持副本集事务")
