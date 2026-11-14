"""T34：后台调度与多进程边界验证（真实副本集，两个独立 client 模拟两进程）。

覆盖三条后台调度链路的多进程语义：
- 提醒扫描 reminder_runtime（app/services/followup_reminder_service.py）：
  main.py 启动的应用内循环，多 worker 部署时每进程各跑一份。本文件验证
  两个进程（两条独立 Mongo 连接）同时扫描同一到期窗口时投递是否重复、
  扫描中断后的续扫位置、同一 due 窗口重复扫描（含时钟回拨）的幂等性。
- 备份调度 backup_schedule（app/operations/runtime.py BackupSchedule.run_if_due）：
  main.py 启动的应用内循环。验证两个进程同时到点时的导出执行次数（T37 原子
  领取修复后应恰好一次），以及领取后崩溃的"跳过一次"语义。
- 报告调度 report_scheduler_service：只写结论不写用例——
  ReportSchedulerService.start() 全仓库无任何调用方（routers 仅按请求实例化
  做 CRUD），_scheduler_loop 为死代码（T53 兼容分析后已删除该调度路径，
  见 docs/t53-dead-code-disposal-report-scheduler.md），当前不存在后台报告
  调度循环。（T37 建议：若未来恢复调度，必须先加与备份调度同款的原子领取，
  否则会原样复刻 D1 缺陷——该要求已作为警示注释固化在服务模块头。）

门控：REHAB_TEST_SCHEDULER_URI（mongodb://127.0.0.1:<port>/...?replicaSet=<name>），
未显式提供时回退沿用 REHAB_TEST_PATIENT_MIGRATION_URI（同一本机副本集惯例），
两者都缺省时全部跳过。每个用例使用独立临时库（uuid 后缀）并在 teardown drop，
只触碰 URI 指向实例上自己创建的库。

发现记录（2026-11-14，T34 验证结论；备份调度缺陷已由 T37 修复）：
- 提醒扫描多进程安全：投递去重不依赖单 worker 假设，而是依赖 ledger 集合
  以 reminder_key 为不可变 _id 的唯一约束 + 副本集事务（dispatch_one 的
  DuplicateKeyError 重试路径）。两进程并发扫描同一到期记录时，输家事务
  冲突后重读赢家 ledger 跳过，通知恰好各投一次（本文件场景 1 实测）。
- 提醒扫描崩溃恢复语义：scan() 逐条 dispatch_one，单条失败写 status=failed
  ledger 并继续不饿死其他记录；失败记录下次扫描重试，已成功记录因 ledger
  persisted 不重投；游标窗口为 (now, now+24h] 仅向前——计划时间已过的
  记录永不补投（代码注释明示该取舍，场景 3 实测）。
- 提醒扫描同窗口重复扫描/时钟回拨幂等：ledger persisted 键覆盖整个
  (followup, scheduled_date, slot) 事件，回拨后的窗口内重扫零新增（场景 4）。
- 备份调度多进程缺陷（T34 发现，T37 修复）：BackupSchedule.run_if_due 原为
  check-then-act——先读 last_scheduled_export_at 判断到点，写文件后再无条件
  $set 更新时间戳，没有原子领取。两进程同时到点时都会通过到点判断、都执行
  全量导出（backup_bytes 各调用一次）并各更新一次时间戳。后果：重复导出
  I/O；文件名含秒级时间戳，同秒并发互相覆盖（静默丢一份），跨秒则留下两份
  含患者数据的敏感导出文件。T37 按 T34 建议修复：到点判断后用
  find_one_and_update 条件领取（filter 含到点条件 + legacy last_backup_at
  回退，update: $set last_scheduled_export_at = now，upsert 保持首次初始化），
  领取成功者才执行导出；领取在导出前完成，进程在导出后崩溃最多留下已领取
  标记（下轮跳过一次，无重复导出），与原崩溃窗口（导出已做、标记未写、
  下轮重复导出）相比更安全——宁可漏一次，也不重复落敏感文件。
- 备份调度部署建议：T37 原子领取后多 worker 部署安全（场景 2 实测恰好一次
  导出）；提醒扫描多 worker 已安全（但每进程仍各跑一遍空扫，浪费可接受）。
"""
import asyncio
import os
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

from app.core.exceptions import AppBaseException
from app.operations import runtime as operations_runtime
from app.services.followup_reminder_service import (
    FollowupReminderService, ensure_reminder_storage, DELIVERIES,
)

URI = (os.environ.get("REHAB_TEST_SCHEDULER_URI")
       or os.environ.get("REHAB_TEST_PATIENT_MIGRATION_URI"))


@unittest.skipUnless(URI, "set REHAB_TEST_SCHEDULER_URI to an isolated local replica set")
class BackgroundSchedulingReplicaTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        if not URI.startswith(("mongodb://127.0.0.1:", "mongodb://localhost:")):
            self.fail("only an explicit loopback test URI is accepted")
        # 两个独立连接模拟两个应用进程（各持自己的 client 与事务会话）
        self.proc_a = AsyncIOMotorClient(URI, serverSelectionTimeoutMS=3000)
        self.proc_b = AsyncIOMotorClient(URI, serverSelectionTimeoutMS=3000)
        self.db_a = self.proc_a["rehab_scheduler_" + uuid4().hex]
        self.db_b = self.proc_b[self.db_a.name]
        await ensure_reminder_storage(self.db_a)
        self.now = datetime(2026, 11, 14, 9)
        self.patient, self.doctor = ObjectId(), ObjectId()
        await self.db_a.users.insert_many([
            {"_id": self.patient, "role": "patient", "is_active": True,
             "name": "Patient", "email": "p@example.test", "password_hash": "secret",
             "practitioners": [str(self.doctor)], "updated_at": datetime(2020, 1, 1)},
            {"_id": self.doctor, "role": "doctor", "is_active": True,
             "name": "Clinician", "email": "d@example.test", "password_hash": "secret"},
        ])
        self.push = patch("app.api.websockets.get_connection_manager",
                          return_value=SimpleNamespace(send_notification=AsyncMock()))
        self.push.start()

    async def asyncTearDown(self):
        self.push.stop()
        await self.proc_a.drop_database(self.db_a.name)
        self.proc_a.close()
        self.proc_b.close()

    # ---- 夹具 ----

    async def seed_followup(self, *, hours_ahead=20):
        followup = ObjectId()
        await self.db_a.followup_records.insert_one({
            "_id": followup, "patient_id": str(self.patient),
            "created_by": str(self.doctor), "provider_id": str(self.doctor),
            "follow_up_type": "phone", "status": "scheduled",
            "scheduled_date": self.now + timedelta(hours=hours_ahead),
            "notes": "plan", "mutation_version": 1})
        return followup

    def service(self, db):
        return FollowupReminderService(db, clock=lambda: self.now)

    async def notification_pairs(self):
        rows = await self.db_a.notifications.find({}).to_list(None)
        return sorted((row["related_entity_id"], row["recipient_id"]) for row in rows)

    # ---- 场景 1：双进程提醒扫描并发同一到期窗口，投递不重复 ----

    async def test_two_process_concurrent_scan_delivers_exactly_once(self):
        followups = [await self.seed_followup() for _ in range(3)]
        # 两进程各自 scan()：游标同窗口、逐条并发 dispatch_one
        results = await asyncio.gather(self.service(self.db_a).scan(),
                                       self.service(self.db_b).scan())
        # ledger 唯一 _id + 事务：赢家提交后输家重读跳过，各进程上报各自
        # 实际生成的条数（总和恰为每记录两收件人）
        self.assertEqual(sum(results), 6)
        self.assertEqual(await self.db_a[DELIVERIES].count_documents({"status": "persisted"}), 6)
        expected = sorted((str(f), str(r)) for f in followups
                          for r in (self.patient, self.doctor))
        self.assertEqual(await self.notification_pairs(), expected)
        # 输家路径收敛后不残留 failed 历史或异常 fence 状态
        self.assertEqual(await self.db_a[DELIVERIES].count_documents({"status": "failed"}), 0)

    # ---- 场景 2：双进程备份调度同时到点（T37 原子领取后恰好一次导出） ----

    async def _seed_due_schedule(self):
        await self.db_a.system_settings.insert_one({
            "_id": "system", "backup_frequency": "hourly",
            "last_scheduled_export_at": self.now - timedelta(hours=2)})

    def _fake_runtime_root(self):
        root = os.path.join("/tmp", "rehab-t37-" + uuid4().hex)
        os.makedirs(os.path.join(root, "app", "operations"), exist_ok=True)
        return root, os.path.join(root, "app", "operations", "runtime.py")

    async def test_two_process_backup_schedule_exports_exactly_once(self):
        await self._seed_due_schedule()
        seeded = self.now - timedelta(hours=2)
        calls = []
        original = operations_runtime.backup_bytes

        async def counting_backup_bytes(db):
            calls.append(db.client)
            return await original(db)

        root, fake_file = self._fake_runtime_root()
        try:
            with patch.object(operations_runtime, "backup_bytes", counting_backup_bytes), \
                 patch.object(operations_runtime, "__file__", fake_file):
                # 两进程同时到点：原子领取只有一个赢家，输家立即返回不执行导出
                await asyncio.gather(operations_runtime.BackupSchedule().run_if_due(self.db_a),
                                     operations_runtime.BackupSchedule().run_if_due(self.db_b))
            folder = os.path.join(root, "data", "backups")
            files = os.listdir(folder)
            # 敏感导出文件恰好一份（不再同秒互相覆盖/跨秒留两份）
            self.assertEqual(len(calls), 1)
            self.assertEqual(len(files), 1, files)
            settings = await self.db_a.system_settings.find_one({"_id": "system"})
            self.assertGreater(settings["last_scheduled_export_at"], seeded)
            # 领取标记已推进：窗口内任何一方再跑都不再导出
            with patch.object(operations_runtime, "backup_bytes", counting_backup_bytes), \
                 patch.object(operations_runtime, "__file__", fake_file):
                await asyncio.gather(operations_runtime.BackupSchedule().run_if_due(self.db_a),
                                     operations_runtime.BackupSchedule().run_if_due(self.db_b))
            self.assertEqual(len(calls), 1)
            self.assertEqual(len(os.listdir(folder)), 1)
        finally:
            import shutil
            shutil.rmtree(root, ignore_errors=True)

    async def test_claim_then_crash_skips_next_round_instead_of_reexporting(self):
        # 崩溃语义取舍（T37）：领取先于导出——领取成功后导出崩溃，留下已推进
        # 的领取时间戳，下一轮跳过一次（宁可漏一次，也不重复落敏感文件）。
        await self._seed_due_schedule()
        seeded = self.now - timedelta(hours=2)
        calls = []
        original = operations_runtime.backup_bytes

        async def crashing_backup_bytes(db):
            calls.append(db.client)
            raise RuntimeError("simulated crash after claim, before file written")

        root, fake_file = self._fake_runtime_root()
        try:
            with patch.object(operations_runtime, "backup_bytes", crashing_backup_bytes), \
                 patch.object(operations_runtime, "__file__", fake_file):
                with self.assertRaises(RuntimeError):
                    await operations_runtime.BackupSchedule().run_if_due(self.db_a)
            folder = os.path.join(root, "data", "backups")
            self.assertEqual(os.listdir(folder), [])
            settings = await self.db_a.system_settings.find_one({"_id": "system"})
            self.assertGreater(settings["last_scheduled_export_at"], seeded)
            # 下一轮（同一窗口内）：到点判断被已推进的领取时间戳拦下——跳过
            # 一次，不重复执行全量导出
            async def counting_backup_bytes(db):
                calls.append(db.client)
                return await original(db)

            with patch.object(operations_runtime, "backup_bytes", counting_backup_bytes), \
                 patch.object(operations_runtime, "__file__", fake_file):
                await asyncio.gather(operations_runtime.BackupSchedule().run_if_due(self.db_a),
                                     operations_runtime.BackupSchedule().run_if_due(self.db_b))
            self.assertEqual(len(calls), 1)
            self.assertEqual(os.listdir(folder), [])
            # 时间推进过窗口后调度恢复正常
            await self.db_a.system_settings.update_one(
                {"_id": "system"},
                {"$set": {"last_scheduled_export_at": self.now - timedelta(hours=2)}})
            with patch.object(operations_runtime, "backup_bytes", counting_backup_bytes), \
                 patch.object(operations_runtime, "__file__", fake_file):
                await operations_runtime.BackupSchedule().run_if_due(self.db_a)
            self.assertEqual(len(calls), 2)
            self.assertEqual(len(os.listdir(folder)), 1)
        finally:
            import shutil
            shutil.rmtree(root, ignore_errors=True)

    async def test_backup_schedule_legacy_timestamp_still_gates_and_claims(self):
        # 单 worker 行为回归：无 last_scheduled_export_at 的 legacy 行按
        # last_backup_at 到点判定，领取时间戳写入 last_scheduled_export_at
        await self.db_a.system_settings.insert_one({
            "_id": "system", "backup_frequency": "hourly",
            "last_backup_at": self.now - timedelta(hours=2)})
        calls = []
        original = operations_runtime.backup_bytes

        async def counting_backup_bytes(db):
            calls.append(db.client)
            return await original(db)

        root, fake_file = self._fake_runtime_root()
        try:
            with patch.object(operations_runtime, "backup_bytes", counting_backup_bytes), \
                 patch.object(operations_runtime, "__file__", fake_file):
                await operations_runtime.BackupSchedule().run_if_due(self.db_a)
            self.assertEqual(len(calls), 1)
            settings = await self.db_a.system_settings.find_one({"_id": "system"})
            self.assertGreater(settings["last_scheduled_export_at"],
                               self.now - timedelta(hours=2))
            self.assertEqual(settings["last_backup_at"],
                             self.now - timedelta(hours=2))
        finally:
            import shutil
            shutil.rmtree(root, ignore_errors=True)

    # ---- 场景 2b：legacy 非 date 时间戳形态（T56/B1 修复回归） ----

    async def _run_and_count_exports(self):
        calls = []
        original = operations_runtime.backup_bytes

        async def counting_backup_bytes(db):
            calls.append(db.client)
            return await original(db)

        root, fake_file = self._fake_runtime_root()
        try:
            with patch.object(operations_runtime, "backup_bytes", counting_backup_bytes), \
                 patch.object(operations_runtime, "__file__", fake_file):
                await operations_runtime.BackupSchedule().run_if_due(self.db_a)
            folder = os.path.join(root, "data", "backups")
            files = os.listdir(folder) if os.path.isdir(folder) else []
            return len(calls), files
        finally:
            import shutil
            shutil.rmtree(root, ignore_errors=True)

    async def _assert_legacy_scalar_timestamp_recovers(self, seeded_value):
        """string/int 形态的调度时间戳必须恢复导出并归一化为 date。

        修复前：Python 预判放行（非 datetime 视同到点），但 Mongo 领取 filter
        的 $lte 接 date 永不匹配字符串/数字 → 领取落空 → upsert 撞唯一 _id →
        DuplicateKeyError 静默 return → 定时备份永久停摆且无日志。
        """
        await self.db_a.system_settings.insert_one({
            "_id": "system", "backup_frequency": "hourly",
            "last_scheduled_export_at": seeded_value})
        calls, files = await self._run_and_count_exports()
        # 修复断言：本轮恢复导出（修复前 0 次），文件恰好一份
        self.assertEqual(calls, 1)
        self.assertEqual(len(files), 1)
        settings = await self.db_a.system_settings.find_one({"_id": "system"})
        # 领取时间戳已写回且形态归一化为 date（覆盖原字符串/整型值）
        self.assertIsInstance(settings["last_scheduled_export_at"], datetime)
        # date 类型行为不变：已推进的 date 时间戳在窗口内拦住下一轮导出
        calls, files = await self._run_and_count_exports()
        self.assertEqual(calls, 0)
        self.assertEqual(files, [])

    async def test_legacy_string_timestamp_recovers_export_and_normalizes(self):
        await self._assert_legacy_scalar_timestamp_recovers("2026-01-01T00:00:00Z")

    async def test_legacy_int_timestamp_recovers_export_and_normalizes(self):
        await self._assert_legacy_scalar_timestamp_recovers(1760000000)

    async def test_legacy_int_backup_at_fallback_recovers_export(self):
        # 调度时间戳缺失、legacy last_backup_at 为整型形态：同样到点领取归一化，
        # 且 legacy 字段本身不被改写
        await self.db_a.system_settings.insert_one({
            "_id": "system", "backup_frequency": "hourly", "last_backup_at": 0})
        calls, files = await self._run_and_count_exports()
        self.assertEqual(calls, 1)
        self.assertEqual(len(files), 1)
        settings = await self.db_a.system_settings.find_one({"_id": "system"})
        self.assertIsInstance(settings["last_scheduled_export_at"], datetime)
        self.assertEqual(settings["last_backup_at"], 0)

    # ---- 场景 3：扫描中断后的续扫位置 ----

    async def test_scan_interrupted_resumes_failed_and_keeps_succeeded(self):
        first, second = await self.seed_followup(), await self.seed_followup(hours_ahead=18)
        service = self.service(self.db_a)
        original = service.dispatch_one

        async def crash_on_first(followup_id):
            if followup_id == str(first):
                raise RuntimeError("simulated process crash mid-scan")
            return await original(followup_id)

        service.dispatch_one = crash_on_first
        with self.assertRaises(AppBaseException) as caught:
            await service.scan()
        self.assertEqual(caught.exception.error_code, "REMINDER_SCAN_FAILED")
        # 崩溃记录留下可重试的 failed 历史（不覆盖可能已提交的赢家）
        failed = await self.db_a[DELIVERIES].count_documents(
            {"status": "failed", "reason": "PERSISTENCE_FAILED",
             "followup_id": str(first)})
        self.assertEqual(failed, 2)
        # 未崩溃记录未被饿死：第二条件计划已投递
        self.assertEqual(await self.notification_pairs(),
                         [(str(second), str(self.patient)), (str(second), str(self.doctor))])
        # 续扫：失败记录重试成功，成功记录不重投
        service.dispatch_one = original
        self.assertEqual(await service.scan(), 2)
        expected = sorted((str(f), str(r)) for f in (first, second)
                          for r in (self.patient, self.doctor))
        self.assertEqual(await self.notification_pairs(), expected)
        self.assertEqual(await self.db_a[DELIVERIES].count_documents({"status": "failed"}), 0)

    async def test_scan_never_catches_up_records_whose_plan_has_passed(self):
        overdue = await self.seed_followup(hours_ahead=-1)
        self.assertEqual(await self.service(self.db_a).scan(), 0)
        self.assertEqual(await self.db_a.notifications.count_documents({}), 0)
        self.assertEqual(await self.db_a[DELIVERIES].count_documents({}), 0)
        # 记录原样保留，未被触碰（无补投、无栅栏写入）
        doc = await self.db_a.followup_records.find_one({"_id": overdue})
        self.assertIsNotNone(doc)
        self.assertNotIn("_reminder_fence", doc)

    # ---- 场景 4：同一 due 窗口重复扫描与时钟回拨的幂等性 ----

    async def test_repeated_window_and_clock_rollback_never_redeliver(self):
        await self.seed_followup()
        service = self.service(self.db_a)
        self.assertEqual(await service.scan(), 2)
        # 同一窗口再扫（含独立第二进程视角）
        self.assertEqual(await self.service(self.db_b).scan(), 0)
        # 时钟回拨 30 分钟（仍在 24h 窗口内）：事件键含 scheduled_date，
        # 回拨不改变键，ledger persisted 兜底，不产生第二条通知
        self.now -= timedelta(minutes=30)
        self.assertEqual(await service.scan(), 0)
        # 回拨后窗口内重扫不产生第二条通知
        self.assertEqual(await self.db_a.notifications.count_documents({}), 2)
        self.assertEqual(await self.db_a[DELIVERIES].count_documents(
            {"status": "persisted"}), 2)


if __name__ == "__main__":
    unittest.main()
