"""T19：栅栏载体模块（app/core/fences.py）在隔离副本集上的并发与事务专项测试。

对照 docs/patient-domain-cutover-plan.md §3.3/R5 的验收要求：隔离副本集覆盖
「账号变 + 实体不变」「实体变 + 账号不变」「双变」三种交错场景、事务整体回滚、
并发首插竞态与 FenceError 的 AppBaseException 错误契约。

门控：REHAB_TEST_FENCES_URI（mongodb://127.0.0.1:<port>/...?replicaSet=<name>），
未显式提供时回退沿用 REHAB_TEST_PATIENT_MIGRATION_URI（同一本机副本集惯例），
两者都缺省时全部跳过。每个用例使用独立临时库（uuid 后缀）并在 teardown drop，
只触碰 URI 指向实例上自己创建的库；并发侧写经独立 client（rival）发起，
模拟另一连接上的账号停用/患者归属变更。

发现记录（不改实现，供 T14 后续处理）：
- dual_bump 会把第一跳的 FenceInvalid 降级包装为 FenceMismatch（409），错误
  分类漂移（如患者栅栏字段被写坏应报 503 FENCE_INVALID，经 dual_bump 变 409）。
- AccountFenceStore.bump 的 DuplicateKeyError 重试循环只在事务外有效：事务内
  唯一键冲突会中止事务，同 session 重试不再可用，事务内并发首插依赖
  with_transaction 的写冲突重试兜底。
"""
import asyncio
import os
import unittest
from uuid import uuid4

from motor.motor_asyncio import AsyncIOMotorClient

from app.core.exceptions import AppBaseException
from app.core.fences import (
    ACCOUNT_FENCES,
    AccountFenceStore,
    FenceInvalid,
    FenceMismatch,
    PatientFenceStore,
    create_account_fence_indexes,
    dual_bump,
    patient_fence_field,
)
from app.db.transactions import run_transaction

URI = (os.environ.get("REHAB_TEST_FENCES_URI")
       or os.environ.get("REHAB_TEST_PATIENT_MIGRATION_URI"))
PATIENTS = "clinical_patients"
FENCE = "access"


@unittest.skipUnless(URI, "set REHAB_TEST_FENCES_URI to an isolated local replica set")
class FencesReplicaSetTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        if not URI.startswith(("mongodb://127.0.0.1:", "mongodb://localhost:")):
            self.fail("only an explicit loopback test URI is accepted")
        self.client = AsyncIOMotorClient(URI, serverSelectionTimeoutMS=3000)
        self.db = self.client["rehab_fences_" + uuid4().hex]
        # 并发侧用独立连接，模拟另一调用方在事务打开窗口内的条件写
        self.rival = AsyncIOMotorClient(URI, serverSelectionTimeoutMS=3000)
        self.rival_db = self.rival[self.db.name]
        self.accounts = AccountFenceStore(self.db)
        self.patients = PatientFenceStore(self.db)
        self.account_id = "fence-account-" + uuid4().hex[:12]
        self.patient_id = "fence-patient-" + uuid4().hex[:12]
        # 并发首插竞态依赖唯一索引（部署侧脚本惯例，此处测试环境显式声明）
        await create_account_fence_indexes(self.db)
        await self.db[PATIENTS].insert_one({
            "_id": self.patient_id, "patient_id": self.patient_id,
            "status": "active", "practitioners": ["doctor-f1"],
            "health_managers": ["manager-f1"]})

    async def asyncTearDown(self):
        await self.client.drop_database(self.db.name)
        self.client.close()
        self.rival.close()

    # ---- 夹具 ----

    async def seed_account_fence(self, count):
        await self.db[ACCOUNT_FENCES].insert_one(
            {"account_id": self.account_id, "fence_name": FENCE, "count": count})

    async def seed_patient_fence(self, count):
        await self.db[PATIENTS].update_one(
            {"patient_id": self.patient_id},
            {"$set": {patient_fence_field(FENCE): count}})

    async def in_transaction(self, operation):
        """把单次栅栏操作放进 run_transaction（snapshot 读、majority 写）。"""
        async def callback(session):
            return await operation(session)
        return await run_transaction(self.db, callback,
                                     error_code="FENCES_TEST_TXN_UNAVAILABLE",
                                     error_message="栅栏测试事务未能确认提交")

    async def interleave(self, operation, rival_action):
        """在事务回调内、栅栏操作执行前打开并发窗口执行 rival_action。

        回调先做一次快照锚点读（固定事务读时间戳），再等并发窗口放行；
        rival_action 完成提交后才放行，保证交错顺序确定。若首趟事务因写冲突
        被中止，with_transaction 重试时并发窗口已放行、直接重走栅栏判定。
        """
        started, release = asyncio.Event(), asyncio.Event()

        async def callback(session):
            await self.db[PATIENTS].find_one({"patient_id": self.patient_id},
                                             session=session)
            started.set()
            await asyncio.wait_for(release.wait(), 10)
            return await operation(session)

        task = asyncio.create_task(self.in_transaction(callback))
        try:
            await asyncio.wait_for(started.wait(), 10)
            await rival_action()
        finally:
            release.set()
        return await task

    async def rival_account_revoke(self):
        """另一连接模拟账号停用：users 标记 + 账号栅栏条件递增（撤权栅栏化）。"""
        await self.rival_db.users.update_one(
            {"_id": self.account_id}, {"$set": {"is_active": False}}, upsert=True)
        result = await self.rival_db[ACCOUNT_FENCES].update_one(
            {"account_id": self.account_id, "fence_name": FENCE, "count": 3},
            {"$inc": {"count": 1}})
        self.assertEqual(result.matched_count, 1)

    async def rival_patient_reassign(self):
        """另一连接模拟患者归属变更：practitioners 改写 + 患者栅栏条件递增。"""
        result = await self.rival_db[PATIENTS].update_one(
            {"patient_id": self.patient_id, patient_fence_field(FENCE): 2},
            {"$inc": {patient_fence_field(FENCE): 1},
             "$set": {"practitioners": ["doctor-rival"]}})
        self.assertEqual(result.matched_count, 1)

    async def account_count(self):
        row = await self.db[ACCOUNT_FENCES].find_one(
            {"account_id": self.account_id, "fence_name": FENCE})
        return None if row is None else row["count"]

    async def patient_fence_value(self):
        doc = await self.db[PATIENTS].find_one({"patient_id": self.patient_id})
        return doc.get(patient_fence_field(FENCE))

    # ---- 场景 1：基础语义在真 Mongo（事务内）复验 ----

    async def test_account_bump_first_insert_and_increment_in_transaction(self):
        async def callback(session):
            first = await self.accounts.bump(self.account_id, FENCE, session=session)
            second = await self.accounts.bump(self.account_id, FENCE, session=session)
            other = await self.accounts.bump(self.account_id, "reminder", session=session)
            return first, second, other

        self.assertEqual(await self.in_transaction(callback), (1, 2, 1))
        rows = await self.db[ACCOUNT_FENCES].find(
            {"account_id": self.account_id}).to_list(None)
        self.assertEqual(
            sorted((row["fence_name"], row["count"]) for row in rows),
            [("access", 2), ("reminder", 1)])
        # upsert 首插文档只带定位键与计数，不污染其他字段
        self.assertTrue(all(set(row) == {"_id", "account_id", "fence_name", "count"}
                            for row in rows))

    async def test_account_check_cas_pass_and_mismatch_rejects_without_write(self):
        await self.seed_account_fence(3)
        self.assertEqual(await self.in_transaction(
            lambda session: self.accounts.check(self.account_id, FENCE, 3, session=session)), 4)
        with self.assertRaises(FenceMismatch) as raised:
            await self.in_transaction(lambda session: self.accounts.check(
                self.account_id, FENCE, 3, session=session))
        self.assertEqual(raised.exception.error_code, "FENCE_MISMATCH")
        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(raised.exception.details["carrier"], "account")
        self.assertEqual(await self.account_count(), 4)

    async def test_account_check_expected_zero_first_insert_semantics(self):
        self.assertEqual(await self.in_transaction(
            lambda session: self.accounts.check(self.account_id, FENCE, 0, session=session)), 1)
        with self.assertRaises(FenceMismatch):
            # 计数器已出现后，expected=0 必然失配
            await self.in_transaction(lambda session: self.accounts.check(
                self.account_id, FENCE, 0, session=session))
        self.assertEqual(await self.account_count(), 1)

    async def test_patient_bump_and_missing_document_rejects(self):
        self.assertEqual(await self.in_transaction(
            lambda session: self.patients.bump(self.patient_id, FENCE, session=session)), 1)
        self.assertEqual(await self.in_transaction(
            lambda session: self.patients.bump(self.patient_id, FENCE, session=session)), 2)
        with self.assertRaises(FenceMismatch) as raised:
            await self.in_transaction(lambda session: self.patients.bump(
                "fence-missing-" + uuid4().hex[:8], FENCE, session=session))
        self.assertEqual(raised.exception.details["carrier"], "patient")
        with self.assertRaises(FenceMismatch):
            # 患者载体与账号载体不同：文档缺失时 expected=0 也拒绝（无 upsert）
            await self.in_transaction(lambda session: self.patients.check(
                "fence-missing-" + uuid4().hex[:8], FENCE, 0, session=session))
        self.assertEqual(await self.patient_fence_value(), 2)

    async def test_patient_extra_query_snapshot_pass_reject_and_reassignment(self):
        extra = {"status": "active", "practitioners": ["doctor-f1"]}
        # 快照命中通过
        self.assertEqual(await self.in_transaction(lambda session: self.patients.bump(
            self.patient_id, FENCE, session=session, extra_query=extra)), 1)
        # 快照失配拒绝且不写入
        with self.assertRaises(FenceMismatch):
            await self.in_transaction(lambda session: self.patients.check(
                self.patient_id, FENCE, 1, session=session,
                extra_query={**extra, "practitioners": ["doctor-other"]}))
        self.assertEqual(await self.patient_fence_value(), 1)
        # 归属真实变更后旧快照条件不再命中
        await self.db[PATIENTS].update_one(
            {"patient_id": self.patient_id},
            {"$set": {"practitioners": ["doctor-rival"]}})
        with self.assertRaises(FenceMismatch):
            await self.in_transaction(lambda session: self.patients.bump(
                self.patient_id, FENCE, session=session, extra_query=extra))
        self.assertEqual(await self.patient_fence_value(), 1)
        # 变更后的新快照命中通过
        self.assertEqual(await self.in_transaction(lambda session: self.patients.check(
            self.patient_id, FENCE, 1, session=session,
            extra_query={"practitioners": ["doctor-rival"]})), 2)

    # ---- 场景 2：三种交错（check CAS 模式）+ bump 模式语义 ----

    async def test_interleave_account_changed_rejects_at_account_hop(self):
        """账号变 + 实体不变：并发撤权先递增账号栅栏，dual_bump 账号跳 CAS 失配拒绝。"""
        await self.seed_account_fence(3)
        await self.seed_patient_fence(2)

        async def operation(session):
            return await dual_bump(
                (self.accounts, self.account_id, FENCE, 3),
                (self.patients, self.patient_id, FENCE, 2), session=session)

        with self.assertRaises(FenceMismatch) as raised:
            await self.interleave(operation, self.rival_account_revoke)
        self.assertEqual(raised.exception.details["hop"], "account")
        # 拒绝后无残留：账号栅栏只剩并发撤权那次递增，患者栅栏未被触碰
        self.assertEqual(await self.account_count(), 4)
        self.assertEqual(await self.patient_fence_value(), 2)

    async def test_interleave_entity_changed_rejects_at_patient_hop(self):
        """实体变 + 账号不变：患者归属变更先递增患者栅栏，患者跳失配且账号跳随事务回滚。"""
        await self.seed_account_fence(3)
        await self.seed_patient_fence(2)

        async def operation(session):
            return await dual_bump(
                (self.accounts, self.account_id, FENCE, 3),
                (self.patients, self.patient_id, FENCE, 2), session=session)

        with self.assertRaises(FenceMismatch) as raised:
            await self.interleave(operation, self.rival_patient_reassign)
        self.assertEqual(raised.exception.details["hop"], "patient")
        # 先成功的账号跳随事务整体回滚，归属变更与栅栏递增保持并发侧结果
        self.assertEqual(await self.account_count(), 3)
        self.assertEqual(await self.patient_fence_value(), 3)
        doc = await self.db[PATIENTS].find_one({"patient_id": self.patient_id})
        self.assertEqual(doc["practitioners"], ["doctor-rival"])

    async def test_interleave_both_changed_rejects_at_account_hop(self):
        """双变：账号与患者栅栏均被并发递增，账号跳先失配即拒绝，患者跳未执行。"""
        await self.seed_account_fence(3)
        await self.seed_patient_fence(2)

        async def operation(session):
            return await dual_bump(
                (self.accounts, self.account_id, FENCE, 3),
                (self.patients, self.patient_id, FENCE, 2), session=session)

        async def revoke_both():
            await self.rival_account_revoke()
            await self.rival_patient_reassign()

        with self.assertRaises(FenceMismatch) as raised:
            await self.interleave(operation, revoke_both)
        self.assertEqual(raised.exception.details["hop"], "account")
        self.assertEqual(await self.account_count(), 4)
        self.assertEqual(await self.patient_fence_value(), 3)

    async def test_interleave_bump_mode_passes_under_concurrent_account_bump(self):
        """bump（无条件）模式语义：并发撤权不拒绝——调用方必须在同事务内自行复核授权。

        与 §3.3「同事务内复核」一致：bump 只承担栅栏化，不复核快照；最终计数
        同时反映并发撤权与本次递增。
        """
        await self.seed_account_fence(3)
        await self.seed_patient_fence(2)

        async def operation(session):
            return await dual_bump(
                (self.accounts, self.account_id, FENCE),
                (self.patients, self.patient_id, FENCE), session=session)

        result = await self.interleave(operation, self.rival_account_revoke)
        self.assertEqual(result, (5, 3))
        self.assertEqual(await self.account_count(), 5)
        self.assertEqual(await self.patient_fence_value(), 3)
        user = await self.db.users.find_one({"_id": self.account_id})
        self.assertFalse(user["is_active"])

    # ---- 场景 3：事务回滚无残留 ----

    async def test_callback_exception_rolls_back_existing_counters(self):
        """回调内注入异常：两个载体的递增随事务整体回滚。"""
        await self.seed_account_fence(2)
        await self.seed_patient_fence(5)

        async def callback(session):
            await self.accounts.bump(self.account_id, FENCE, session=session)
            await self.patients.bump(self.patient_id, FENCE, session=session)
            raise RuntimeError("injected failure after both fence bumps")

        with self.assertRaises(RuntimeError):
            await self.in_transaction(callback)
        self.assertEqual(await self.account_count(), 2)
        self.assertEqual(await self.patient_fence_value(), 5)

    async def test_first_insert_rolls_back_without_residue(self):
        """首插形态回滚：account_fences 不留计数器文档，患者文档不留栅栏字段。"""
        async def callback(session):
            await self.accounts.bump(self.account_id, FENCE, session=session)
            await self.patients.bump(self.patient_id, FENCE, session=session)
            raise ValueError("injected failure on first insert")

        with self.assertRaises(ValueError):
            await self.in_transaction(callback)
        self.assertEqual(await self.db[ACCOUNT_FENCES].count_documents({}), 0)
        self.assertIsNone(await self.patient_fence_value())

    async def test_patient_hop_failure_rolls_back_account_hop(self):
        """患者跳 CAS 失配：先成功的账号跳随事务回滚（无并发窗口的确定性版本）。"""
        await self.seed_account_fence(2)
        await self.seed_patient_fence(5)

        with self.assertRaises(FenceMismatch) as raised:
            await self.in_transaction(lambda session: dual_bump(
                (self.accounts, self.account_id, FENCE, 2),
                (self.patients, self.patient_id, FENCE, 7), session=session))
        self.assertEqual(raised.exception.details["hop"], "patient")
        self.assertEqual(await self.account_count(), 2)
        self.assertEqual(await self.patient_fence_value(), 5)

    # ---- 场景 4：并发首插竞态 ----

    async def test_concurrent_first_insert_race_yields_single_counter(self):
        """事务外并发 upsert：唯一索引兜底，DuplicateKeyError 重试路径收敛为单文档。

        8 个协程同时起跳，首插碰撞近似必然发生；断言本身与碰撞与否无关
        （恰好一个计数器、最终计数等于成功递增次数、各返回值互不相同）。
        """
        results = await asyncio.gather(*[
            self.accounts.bump(self.account_id, FENCE) for _ in range(8)])
        self.assertEqual(sorted(results), list(range(1, 9)))
        rows = await self.db[ACCOUNT_FENCES].find(
            {"account_id": self.account_id}).to_list(None)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["count"], 8)

    async def test_concurrent_transactions_dual_bump_serialize_and_commit(self):
        """事务内并发 dual_bump：同文档写冲突由 with_transaction 重试收敛，双双提交。"""
        async def one(_):
            async def callback(session):
                return await dual_bump(
                    (self.accounts, self.account_id, FENCE),
                    (self.patients, self.patient_id, FENCE), session=session)
            return await self.in_transaction(callback)

        results = await asyncio.gather(*(one(i) for i in range(4)))
        # 写冲突迫使事务串行化：每个事务拿到的 (账号, 患者) 计数对一致递增
        self.assertEqual(sorted(results), [(1, 1), (2, 2), (3, 3), (4, 4)])
        self.assertEqual(await self.account_count(), 4)
        self.assertEqual(await self.patient_fence_value(), 4)

    # ---- 场景 5：FenceError 的 AppBaseException 错误契约 ----

    async def test_fence_error_contract_matches_global_handler_fields(self):
        """FENCE_MISMATCH/FENCE_INVALID 可被 main.py 的 AppBaseException 全局处理器识别。

        处理器（app/main.py app_exception_handler）按 exc.status_code 出响应、
        以 exc.error_code/message/details 组织 content，此处对齐该契约断言。
        """
        for exc, code, status in ((FenceInvalid("栅栏名称无效"), "FENCE_INVALID", 503),
                                  (FenceMismatch(), "FENCE_MISMATCH", 409)):
            self.assertIsInstance(exc, AppBaseException)
            self.assertEqual(exc.error_code, code)
            self.assertEqual(exc.status_code, status)
            payload = exc.to_dict()
            self.assertEqual(payload["error"], code)
            self.assertEqual(payload["message"], exc.message)
            # to_dict 仅在 details 非空时输出该键；全局处理器则始终携带
            # "details" 键（exc.details 为 {} 时也输出），两者分别对齐
            if exc.details:
                self.assertEqual(payload["details"], exc.details)
            http = exc.to_http_exception()
            self.assertEqual(http.status_code, status)
            self.assertEqual(http.detail["error"], code)


if __name__ == "__main__":
    unittest.main()
