"""Bounded business export retains patient data and claims no recoverability."""
from copy import deepcopy
from datetime import datetime, timezone
import json
import unittest
from unittest.mock import AsyncMock, patch

from bson import ObjectId
from app.operations.data_export import EXPORT_COLLECTIONS, data_export_bytes
from app.operations.runtime import BackupSchedule, build_backup, public_settings


class Collection:
    def __init__(self, rows=()):
        self.rows = list(rows)

    def find(self, query):
        async def cursor():
            for row in self.rows:
                yield deepcopy(row)
        return cursor()


class Database:
    def __init__(self, rows=None, settings=None):
        self.rows = rows or {}
        self.setting_row = deepcopy(settings or {})
        self.system_settings = AsyncMock()
        self.system_settings.find_one.side_effect = self.read_settings
        self.system_settings.update_one.side_effect = self.write_settings

    async def read_settings(self, query):
        return deepcopy(self.setting_row)

    async def write_settings(self, query, update, **options):
        self.setting_row.update(update["$set"])

    def __getitem__(self, name):
        return Collection(self.rows.get(name, []))


class BusinessExportTests(unittest.IsolatedAsyncioTestCase):
    async def test_manifest_distinguishes_limit_from_actual_truncation(self):
        db = Database({"users": [{"_id": ObjectId(), "name": "Synthetic patient", "hashed_password": "secret",
            "nested": {"access_token": "token", "value": "kept"}}] * 2001,
            "tags": [{"name": "tag"}] * 2000})
        value = json.loads(await data_export_bytes(db))
        manifest = value["manifest"]
        self.assertFalse(manifest["restorable"])
        self.assertTrue(manifest["contains_patient_information"])
        self.assertEqual(manifest["collection_scope"], list(EXPORT_COLLECTIONS))
        self.assertEqual(manifest["truncated_collections"], ["users"])
        self.assertEqual(value["collections"]["users"]["count"], 2000)
        self.assertFalse(value["collections"]["tags"]["truncated"])
        row = value["collections"]["users"]["rows"][0]
        self.assertIsInstance(row["_id"], str)
        self.assertEqual(row["name"], "Synthetic patient")
        self.assertEqual(row["nested"], {"value": "kept"})
        self.assertNotIn("hashed_password", row)

    async def test_manual_download_preserves_compatibility_and_scheduled_time(self):
        last = datetime.now(timezone.utc)
        db = Database(settings={"last_backup_at": last, "last_scheduled_export_at": last})
        response = await build_backup(db)
        self.assertEqual(response.headers["content-disposition"], "attachment; filename=rehab-backup.json")
        self.assertEqual(response.headers["x-database-restorable"], "false")
        self.assertEqual(db.setting_row["last_backup_at"], last)
        self.assertEqual(db.setting_row["last_scheduled_export_at"], last)
        self.assertIn("last_data_export_at", db.setting_row)
        self.assertIn("collections", json.loads(response.body))

    async def test_scheduler_reads_legacy_time_but_manual_download_cannot_postpone_it(self):
        now = datetime.now(timezone.utc)
        for settings in ({"last_backup_at": now}, {"last_scheduled_export_at": now}):
            db = Database(settings=settings)
            with patch("app.operations.runtime.backup_bytes", new_callable=AsyncMock) as export:
                await BackupSchedule().run_if_due(db)
                export.assert_not_called()
        value = public_settings({"last_backup_at": now})
        self.assertEqual(value["last_backup_at"], now)
        self.assertIsNone(value["last_scheduled_export_at"])
