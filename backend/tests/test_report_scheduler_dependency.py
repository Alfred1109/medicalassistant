"""Report CRUD uses the request database without starting background work."""
from copy import deepcopy
from datetime import datetime
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from bson import ObjectId
from fastapi import FastAPI
import httpx

from app.api.routers.report_scheduler_router import router, get_current_user
from app.db.mongodb import get_database
from app.services.report_scheduler_service import report_scheduler_service


class Collection:
    def __init__(self, rows=None):
        self.rows = rows or {}

    async def insert_one(self, document):
        key = ObjectId()
        self.rows[key] = {**deepcopy(document), "_id": key}
        return SimpleNamespace(inserted_id=key)

    async def find_one(self, query, projection=None):
        return deepcopy(self.rows.get(query["_id"]))

    async def update_one(self, query, update):
        row = self.rows.get(query["_id"])
        if row:
            row.update(deepcopy(update["$set"]))
        return SimpleNamespace(modified_count=int(row is not None))

    async def delete_one(self, query):
        return SimpleNamespace(deleted_count=int(self.rows.pop(query["_id"], None) is not None))


class ReportSchedulerDependencyTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.app = FastAPI()
        self.app.include_router(router)
        self.actor = SimpleNamespace(id=str(ObjectId()), role="doctor")
        self.db = SimpleNamespace(report_schedules=Collection(),
                                  users=UsersCollection(self.actor.id))
        self.app.dependency_overrides[get_database] = lambda: self.db
        self.app.dependency_overrides[get_current_user] = lambda: self.actor
        self.http = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://synthetic")
        self.patch = patch("app.services.report_scheduler_service.get_db", side_effect=AssertionError("global db used"))
        self.patch.start()
        self.addCleanup(self.patch.stop)

    async def asyncTearDown(self):
        await self.http.aclose()

    async def create(self):
        result = await self.http.post("/report-schedules", json={"name": "test", "reportId": "overview",
            "frequency": "once", "recipients": [self.actor.id], "format": "html", "enabled": False,
            "nextRunTime": datetime.utcnow().isoformat()})
        self.assertEqual(result.status_code, 200, result.text)
        return result.json()["id"]

    async def test_request_database_supports_crud_without_global_scheduler(self):
        # T53 后无 start/is_running/_scheduler_task：断言单例从未被 CRUD 触碰
        # （全局 get_db 打桩在 asyncSetUp，一旦被调用立即 AssertionError）
        self.assertIsNone(report_scheduler_service.db)
        key = await self.create()
        read = await self.http.get("/report-schedules/" + key)
        self.assertEqual(read.status_code, 200, read.text)
        self.assertEqual(read.json()["createdBy"], self.actor.id)
        change = await self.http.put("/report-schedules/" + key, json={"name": "changed"})
        self.assertEqual(change.status_code, 200, change.text)
        self.assertEqual((await self.http.get("/report-schedules/" + key)).json()["name"], "changed")
        self.assertEqual((await self.http.delete("/report-schedules/" + key)).status_code, 200)
        self.assertEqual((await self.http.get("/report-schedules/" + key)).status_code, 404)
        self.assertIsNone(report_scheduler_service.db)

    async def test_catalog_matches_only_real_supported_analytics(self):
        response = await self.http.get("/report-schedules/catalog")
        self.assertEqual(response.status_code, 200, response.text)
        items = response.json()["items"]
        by_id = {row["id"]: row for row in items}
        self.assertIn("overview", by_id)
        self.assertIn("trend:patient", by_id)
        self.assertEqual(by_id["overview"]["timeRanges"], [])
        self.assertEqual(by_id["distribution:region"]["timeRanges"], [])
        self.assertEqual(by_id["trend:patient"]["formats"], ["html"])
        self.assertNotIn("trend:arbitrary", by_id)

    async def test_another_request_database_and_actor_do_not_inherit_state(self):
        key = await self.create()
        self.actor = SimpleNamespace(id=str(ObjectId()), role="doctor")
        self.assertEqual((await self.http.get("/report-schedules/" + key)).status_code, 403)
        original = self.db
        self.db = SimpleNamespace(report_schedules=Collection(), users=UsersCollection(self.actor.id))
        self.assertEqual((await self.http.get("/report-schedules/" + key)).status_code, 404)
        self.assertEqual(len(original.report_schedules.rows), 1)


class UsersCollection:
    def __init__(self, account_id):
        self.account_id = ObjectId(account_id)

    async def find_one(self, query, projection=None):
        return {"_id": self.account_id} if query.get("_id") == self.account_id else None

    def find(self, query, projection=None):
        return UserCursor(self.account_id if self.account_id in query["_id"]["$in"] else None)


class UserCursor:
    def __init__(self, account_id):
        self.account_id = account_id

    async def to_list(self, length=None):
        return [{"_id": self.account_id}] if self.account_id else []
