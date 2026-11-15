"""MongoDB transaction execution shared by business domains.

Domains retain their error codes and messages; driver retries and uncertain
commit outcomes have one implementation. No domain falls back to sequential
writes when transactions are unavailable.
"""
from pymongo.errors import DuplicateKeyError, PyMongoError
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


async def run_transaction_with_dedup_retry(db, callback, *, error_code, error_message,
                                           max_attempts=3):
    """Execute a transaction, transparently retrying concurrent duplicate-key aborts.

    并发首写撞唯一索引时事务以 DuplicateKeyError 中止（run_transaction 将其
    保留在 AppBaseException.__cause__）。该冲突属瞬时竞争：回调重跑后由先查
    后插/重读胜者收敛，与四个业务域（rehab_publication / rehab_feedback /
    followup_reminder / communication）的既有重试模板逐字同构——批次 1 只
    提供本助手与单测锁定语义，既有调用点的迁移属 C4 后续批次（相关服务文件
    在途禁改）。

    - DuplicateKeyError 中止：静默重试，至多 max_attempts 次（默认 3，与
      既有模板的 `for attempt in range(3)` 一致）；最后一次仍撞键则原样上抛。
    - 其余业务错误（含回调内 AppBaseException）与非重复键的驱动错误：一次
      都不重试，原样上抛。
    - error_code / error_message 参数化：各域保留自己的公共错误码与文案。
    """
    for attempt in range(max_attempts):
        try:
            return await run_transaction(db, callback,
                                         error_code=error_code,
                                         error_message=error_message)
        except AppBaseException as error:
            if not isinstance(error.__cause__, DuplicateKeyError) or attempt == max_attempts - 1:
                raise
