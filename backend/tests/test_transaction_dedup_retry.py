"""run_transaction_with_dedup_retry 助手语义锁定（redundancy review 批次 1）。

四个业务域（rehab_publication / rehab_feedback / followup_reminder /
communication）各自维护一份 `for attempt in range(3)` + DuplicateKeyError
__cause__ 判别的重试模板；本测试锁定收敛后助手的等价语义，为 C4 后续批次
迁移既有调用点提供行为基准（迁移前不改动任何既有调用点）。全部内存打桩，
不触碰真实数据库。
"""
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

from pymongo.errors import DuplicateKeyError, OperationFailure

from app.core.exceptions import AppBaseException
from app.db.transactions import run_transaction_with_dedup_retry

ERROR_CODE = "TEST_TRANSACTION_UNAVAILABLE"
ERROR_MESSAGE = "测试事务未能确认提交"


def _session_with(outcomes):
    """打桩事务会话：with_transaction 逐次消费 outcomes（异常即中止事务），
    且真实调用回调（与驱动语义一致——每次尝试都会重跑 callback）。"""
    session = AsyncMock()
    session.__aenter__.return_value = session
    callback_calls = []
    pending = list(outcomes)

    async def fake_with_transaction(callback, **kwargs):
        callback_calls.append(callback)
        outcome = pending.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    session.with_transaction.side_effect = fake_with_transaction
    db = SimpleNamespace(client=SimpleNamespace(start_session=AsyncMock(return_value=session)))
    return db, session, callback_calls


class TransactionDedupRetryTests(unittest.IsolatedAsyncioTestCase):
    async def test_duplicate_key_abort_is_retried_until_success(self):
        # 第一次撞唯一索引（DuplicateKeyError 经 run_transaction 保留在
        # __cause__），第二次成功：静默重试后返回回调结果
        db, session, callback_calls = _session_with(
            [DuplicateKeyError("dup"), "callback-result"])
        callback = AsyncMock(return_value=None)
        result = await run_transaction_with_dedup_retry(
            db, callback, error_code=ERROR_CODE, error_message=ERROR_MESSAGE)
        self.assertEqual(result, "callback-result")
        self.assertEqual(session.with_transaction.await_count, 2)
        self.assertEqual(len(callback_calls), 2)

    async def test_duplicate_key_exhausts_attempts_then_raises(self):
        # 连续 3 次（默认 max_attempts）撞键：最后一次原样上抛，不再重试
        db, session, _calls = _session_with([DuplicateKeyError("dup")] * 3)
        with self.assertRaises(AppBaseException) as caught:
            await run_transaction_with_dedup_retry(
                db, AsyncMock(), error_code=ERROR_CODE, error_message=ERROR_MESSAGE)
        self.assertEqual(session.with_transaction.await_count, 3)
        self.assertEqual(caught.exception.error_code, ERROR_CODE)
        self.assertEqual(caught.exception.status_code, 503)
        self.assertIsInstance(caught.exception.__cause__, DuplicateKeyError)

    async def test_explicit_max_attempts_bound(self):
        # max_attempts 参数化：2 次撞键 + max_attempts=2 → 第二次即上抛
        db, session, _calls = _session_with([DuplicateKeyError("dup")] * 2)
        with self.assertRaises(AppBaseException):
            await run_transaction_with_dedup_retry(
                db, AsyncMock(), error_code=ERROR_CODE, error_message=ERROR_MESSAGE,
                max_attempts=2)
        self.assertEqual(session.with_transaction.await_count, 2)

    async def test_non_duplicate_driver_error_is_never_retried(self):
        # 非重复键的驱动错误：一次都不重试，原样上抛（__cause__ 非重复键）
        driver_error = OperationFailure("boom")
        db, session, _calls = _session_with([driver_error])
        with self.assertRaises(AppBaseException) as caught:
            await run_transaction_with_dedup_retry(
                db, AsyncMock(), error_code=ERROR_CODE, error_message=ERROR_MESSAGE)
        self.assertEqual(session.with_transaction.await_count, 1)
        self.assertEqual(caught.exception.error_code, ERROR_CODE)
        self.assertIs(caught.exception.__cause__, driver_error)

    async def test_business_conflict_from_callback_is_never_retried(self):
        # 回调内业务错误（AppBaseException）逐字透传，不与重复键混淆重试
        conflict = AppBaseException("review changed", status_code=409,
                                    error_code="REVIEW_CHANGED")
        db, session, _calls = _session_with([conflict])
        with self.assertRaises(AppBaseException) as caught:
            await run_transaction_with_dedup_retry(
                db, AsyncMock(), error_code=ERROR_CODE, error_message=ERROR_MESSAGE)
        self.assertIs(caught.exception, conflict)
        self.assertEqual(session.with_transaction.await_count, 1)

    async def test_missing_transaction_client_never_runs_callback(self):
        # 无事务客户端：与 run_transaction 同语义 503，回调不执行
        callback = AsyncMock()
        with self.assertRaises(AppBaseException) as caught:
            await run_transaction_with_dedup_retry(
                SimpleNamespace(), callback,
                error_code=ERROR_CODE, error_message=ERROR_MESSAGE)
        self.assertEqual(caught.exception.status_code, 503)
        callback.assert_not_called()


if __name__ == "__main__":
    unittest.main()
