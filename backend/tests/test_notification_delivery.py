"""Wave 2-A：通知生产链路统一 + 预警触达闭环。

覆盖：
- 随访提醒经 NotificationService.create_notification 产出（模块内不再存在
  手搓 notifications.insert_one / 手推 WebSocket 的绕过路径）
- 健康预警创建后为责任医护产生通知（统一经 NotificationService）
- ICF 指标越界触发的预警同样产生医护通知
- 无责任医护（未分配 / 患者不存在）时预警仍创建成功且不报错
- 同一业务预警重复触发不重复产生通知

用隔离副本集（每次一个独立库名），不触碰其它并行任务的测试库。
"""
import asyncio
import os
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

from app.models.health_data_threshold import HealthDataThreshold
from app.schemas.health_data_threshold import AlertCreate
from app.services import followup_reminder_service, icf_service
from app.services.followup_reminder_service import (
    FollowupReminderService, ensure_reminder_storage)
from app.services.health_alert_service import HealthAlertService
from app.services.notification_service import NotificationService

# 独立变量优先；未提供时回退本机隔离副本集（与 test_followup_reminders.py
# 同款回退写法）。
URI = (os.environ.get("REHAB_TEST_NOTIFICATION_MONGO_URI")
       or os.environ.get("REHAB_TEST_REMINDER_MONGO_URI")
       or os.environ.get("REHAB_TEST_PATIENT_E2E_URI")
       or "mongodb://127.0.0.1:37021/?replicaSet=rehab_rs&directConnection=true")


async def _drain_tasks():
    """让 create_notification 里的推送协程跑完，避免悬空任务。"""
    for _ in range(3):
        await asyncio.sleep(0)


class MongoCase(unittest.IsolatedAsyncioTestCase):
    """每次一个独立库名，用完即删。"""

    async def asyncSetUp(self):
        try:
            self.mongo = AsyncIOMotorClient(URI, serverSelectionTimeoutMS=3000)
            await self.mongo.admin.command("ping")
        except Exception as error:  # noqa: BLE001 —— 本机无副本集时跳过
            self.skipTest(f"隔离副本集不可用：{error}")
        self.db = self.mongo["rehab_notification_delivery_" + uuid4().hex]

    async def asyncTearDown(self):
        await self.mongo.drop_database(self.db.name)
        self.mongo.close()


class StaffFixture(MongoCase):
    """患者 + 一名责任医生 + 一名责任健康管理师。"""

    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.patient, self.doctor, self.manager = ObjectId(), ObjectId(), ObjectId()
        await self.db.users.insert_many([
            {"_id": self.patient, "role": "patient", "is_active": True,
             "name": "患者甲", "practitioners": [str(self.doctor)],
             "health_managers": [str(self.manager)]},
            {"_id": self.doctor, "role": "doctor", "is_active": True, "name": "医生乙"},
            {"_id": self.manager, "role": "health_manager", "is_active": True,
             "name": "护士丙"},
        ])
        self.service = HealthAlertService(self.db)

    def alert_payload(self, **overrides):
        payload = {"health_data_id": "hd-1", "patient_id": str(self.patient),
                   "data_type": "vital_sign", "vital_type": "heart_rate",
                   "value": 180, "unit": "bpm", "alert_level": "critical",
                   "recorded_at": datetime(2026, 11, 15, 8, 0)}
        payload.update(overrides)
        return AlertCreate(**payload)

    async def notifications(self):
        return await self.db.notifications.find({}).to_list(length=None)


class AlertDeliveryTests(StaffFixture):
    async def test_alert_creation_notifies_responsible_staff(self):
        alert = await self.service.create_alert(self.alert_payload())
        rows = await self.notifications()
        self.assertEqual(len(rows), 2)
        self.assertEqual({row["recipient_id"] for row in rows},
                         {str(self.doctor), str(self.manager)})
        for row in rows:
            self.assertEqual(row["notification_type"], "health_alert")
            self.assertEqual(row["related_entity_type"], "health_alert")
            self.assertEqual(row["related_entity_id"], alert.id)
            self.assertEqual(row["sender_id"], "system:health-alerts")
            self.assertEqual(row["sender_role"], "system")
            self.assertFalse(row["read"])
            # 文案：预警类型 + 关键数值与单位 + 发生时间 + 患者显示名
            self.assertIn("患者甲", row["content"])
            self.assertIn("心率", row["content"])
            self.assertIn("180", row["content"])
            self.assertIn("bpm", row["content"])
            self.assertIn("2026-11-15", row["content"])
        await _drain_tasks()

    async def test_alert_level_maps_to_notification_priority(self):
        await self.service.create_alert(self.alert_payload(alert_level="warning"))
        rows = await self.notifications()
        self.assertTrue(rows)
        self.assertEqual({row["priority"] for row in rows}, {"high"})
        await self.service.create_alert(self.alert_payload(health_data_id="hd-2"))
        rows = await self.notifications()
        self.assertEqual({row["priority"] for row in rows}, {"high", "urgent"})
        await _drain_tasks()

    async def test_alert_without_assigned_staff_still_succeeds(self):
        await self.db.users.update_one({"_id": self.patient},
                                       {"$set": {"practitioners": [], "health_managers": []}})
        alert = await self.service.create_alert(self.alert_payload())
        self.assertTrue(alert.id)
        self.assertEqual(await self.db.health_data_alerts.count_documents({}), 1)
        self.assertEqual(await self.db.notifications.count_documents({}), 0)
        await _drain_tasks()

    async def test_alert_for_unknown_patient_does_not_block_creation(self):
        alert = await self.service.create_alert(
            self.alert_payload(patient_id=str(ObjectId())))
        self.assertTrue(alert.id)
        self.assertEqual(await self.db.health_data_alerts.count_documents({}), 1)
        self.assertEqual(await self.db.notifications.count_documents({}), 0)
        await _drain_tasks()

    async def test_inactive_staff_is_not_notified(self):
        await self.db.users.update_one({"_id": self.manager},
                                       {"$set": {"is_active": False}})
        await self.service.create_alert(self.alert_payload())
        rows = await self.notifications()
        self.assertEqual([row["recipient_id"] for row in rows], [str(self.doctor)])
        await _drain_tasks()

    async def test_repeated_threshold_hit_does_not_notify_twice(self):
        await self.db.health_data_thresholds.insert_one(
            HealthDataThreshold.create_heart_rate_threshold(
                name="心率阈值", normal_range={"min": 60, "max": 100},
                warning_range={"min": 45, "max": 120},
                critical_range={"min": 0, "max": 1000}).to_mongo())
        first = await self.service.check_health_data(
            health_data_id="hd-1", patient_id=str(self.patient), data_type="vital_sign",
            vital_type="heart_rate", value=180)
        self.assertEqual(first["status"], "warning")
        self.assertTrue(first["alert_id"])
        self.assertEqual(await self.db.notifications.count_documents({}), 2)

        # 同一份健康数据重复命中：预警文档各留一份，医护只通知一次
        second = await self.service.check_health_data(
            health_data_id="hd-1", patient_id=str(self.patient), data_type="vital_sign",
            vital_type="heart_rate", value=180)
        self.assertEqual(second["status"], "warning")
        self.assertEqual(await self.db.health_data_alerts.count_documents({}), 2)
        self.assertEqual(await self.db.notifications.count_documents({}), 2)

        # 另一份健康数据是新的越界事实，重新通知
        await self.service.check_health_data(
            health_data_id="hd-2", patient_id=str(self.patient), data_type="vital_sign",
            vital_type="heart_rate", value=180)
        self.assertEqual(await self.db.health_data_alerts.count_documents({}), 3)
        self.assertEqual(await self.db.notifications.count_documents({}), 4)

        # 同一份数据升级到危急级别也是新的越界事实，重新通知
        await self.service.create_alert(self.alert_payload(
            health_data_id="hd-1", alert_level="critical"))
        self.assertEqual(await self.db.notifications.count_documents({}), 6)
        await _drain_tasks()

    async def test_same_alert_id_is_not_notified_twice(self):
        alert = await self.service.create_alert(self.alert_payload())
        # 同一预警文档再次触达（重复处理）不得重复通知
        await self.service._notify_responsible_staff(
            await self.db.health_data_alerts.find_one({"_id": ObjectId(alert.id)}))
        self.assertEqual(await self.db.notifications.count_documents({}), 2)
        await _drain_tasks()


class IcfAlertDeliveryTests(StaffFixture):
    async def test_icf_metric_alert_notifies_staff(self):
        async def followups(_db, _patient_id):
            return [{"status": "scheduled"}]
        with patch.object(icf_service, "_load_followups", followups):
            result = await icf_service.evaluate_metrics_and_alert(
                self.db, SimpleNamespace(id=self.doctor, role="doctor"),
                str(self.patient))
        self.assertTrue(result["triggered"])
        rows = await self.notifications()
        self.assertEqual(len(rows), 2)
        for row in rows:
            self.assertEqual(row["notification_type"], "health_alert")
            self.assertEqual(row["related_entity_type"], "health_alert")
            self.assertIn("患者甲", row["content"])
            self.assertIn("随访完成率", row["content"])
        await _drain_tasks()

        # 同一指标已有未处理预警 → 不重复创建，也不重复通知
        with patch.object(icf_service, "_load_followups", followups):
            again = await icf_service.evaluate_metrics_and_alert(
                self.db, SimpleNamespace(id=self.doctor, role="doctor"),
                str(self.patient))
        self.assertEqual(again["triggered"], [])
        self.assertEqual(await self.db.health_data_alerts.count_documents({}), 1)
        self.assertEqual(await self.db.notifications.count_documents({}), 2)
        await _drain_tasks()


class ReminderDeliveryTests(MongoCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        await ensure_reminder_storage(self.db)
        self.patient, self.doctor = ObjectId(), ObjectId()
        await self.db.users.insert_many([
            {"_id": self.patient, "role": "patient", "is_active": True,
             "name": "患者甲", "practitioners": [str(self.doctor)]},
            {"_id": self.doctor, "role": "doctor", "is_active": True, "name": "医生乙"},
        ])
        self.now = datetime(2026, 11, 15, 8)
        self.followup = ObjectId()
        await self.db.followup_records.insert_one({
            "_id": self.followup, "patient_id": str(self.patient),
            "created_by": str(self.doctor), "provider_id": str(self.doctor),
            "follow_up_type": "phone", "status": "scheduled",
            "scheduled_date": self.now + timedelta(hours=24),
            "notes": "", "mutation_version": 1})
        self.service = FollowupReminderService(self.db, clock=lambda: self.now)

    async def test_reminder_notification_is_produced_by_notification_service(self):
        calls = []
        original = NotificationService.create_notification

        async def spy(*args, **kwargs):
            calls.append((args, kwargs))
            return await original(*args, **kwargs)

        with patch.object(NotificationService, "create_notification", new=spy):
            result = await self.service.dispatch_one(str(self.followup))
        self.assertEqual(result["generated"], 2)
        self.assertEqual(len(calls), 2)
        for _, kwargs in calls:
            self.assertEqual(kwargs["notification_type"], "followup")
            self.assertEqual(kwargs["sender_id"], "system:followup-reminders")
            self.assertEqual(kwargs["sender_role"], "system")
            self.assertEqual(kwargs["priority"], "normal")
            self.assertEqual(kwargs["related_entity_type"], "followup")
            self.assertEqual(kwargs["related_entity_id"], str(self.followup))
            self.assertIsNotNone(kwargs.get("session"))

        rows = await self.db.notifications.find({}).to_list(length=None)
        self.assertEqual(len(rows), 2)
        self.assertEqual({row["recipient_id"] for row in rows},
                         {str(self.patient), str(self.doctor)})
        for row in rows:
            self.assertEqual(row["notification_type"], "followup")
            self.assertEqual(row["related_entity_type"], "followup")
            self.assertEqual(row["related_entity_id"], str(self.followup))
            self.assertFalse(row["read"])
        await _drain_tasks()

    async def test_reminder_repeat_check_does_not_notify_twice(self):
        await self.service.dispatch_one(str(self.followup))
        self.assertEqual(await self.db.notifications.count_documents({}), 2)
        result = await self.service.dispatch_one(str(self.followup))
        self.assertEqual(result["generated"], 0)
        self.assertEqual(await self.db.notifications.count_documents({}), 2)
        await _drain_tasks()

    def test_reminder_module_has_no_bypassed_notification_path(self):
        source = Path(followup_reminder_service.__file__).read_text(encoding="utf-8")
        self.assertNotIn("notifications.insert_one", source)
        self.assertNotIn("from app.api.websockets import", source)
        self.assertIn("NotificationService.create_notification", source)
        self.assertIn("NotificationService.deliver_notification", source)


if __name__ == "__main__":
    unittest.main()
