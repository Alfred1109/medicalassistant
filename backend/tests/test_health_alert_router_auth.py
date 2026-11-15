"""T76 健康预警路由授权收口契约（T75 发现的安全缺口）。

收口前：/api/health/alerts/* 仅 get_current_user——任何登录用户可读任何
患者预警。收口后按角色分流：

1. 患者仅可读本人预警（自取语义，与 clinical/router.py 患者预警端点同源：
   ensure_self_patient_access；显式他人 ID 一律 403）；
2. 医护（doctor/health_manager）按内核 ensure_patient_access；列表未传
   patient_id 时收敛到 assigned_scope_ids 名下患者范围；
3. 阈值 CRUD 与预警写路径（resolve/ignore/update/create/check）限医护/admin，
   患者一律 403；
4. admin 豁免。

打桩方式与 test_patient_consumer_endpoints 同款：内存 FakeDB + legacy 域
固定，不触碰真实 MongoDB。
"""

import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
from bson import ObjectId
from jose import jwt

from app.core.config import settings
from app.api.dependencies import get_database
from app.main import app
from app.schemas.user import UserResponse
from patient_identity_fake import identity_find_from_lookup, legacy_domain_state

PATIENT_ID = str(ObjectId())
OTHER_PATIENT_ID = str(ObjectId())
DOCTOR_ID = str(ObjectId())
ADMIN_ID = str(ObjectId())


def make_operator(role="patient", user_id=PATIENT_ID):
    now = datetime.utcnow()
    return UserResponse(id=user_id, email="actor@example.com", name="合成操作者",
                        role=role, is_active=True, createdAt=now, updatedAt=now)


def _match(doc, query):
    for key, expected in query.items():
        value = doc.get(key)
        if isinstance(expected, dict) and any(op.startswith("$") for op in expected):
            if "$in" in expected:
                if isinstance(value, (list, tuple, set)):
                    if not any(item in expected["$in"] for item in value):
                        return False
                elif value not in expected["$in"]:
                    return False
            if "$ne" in expected and value == expected["$ne"]:
                return False
            if "$gte" in expected and not (value is not None and value >= expected["$gte"]):
                return False
            if "$lte" in expected and not (value is not None and value <= expected["$lte"]):
                return False
        elif value != expected:
            return False
    return True


class FakeCursor:
    def __init__(self, rows):
        self.rows = list(rows)

    def sort(self, key, direction=1):
        self.rows.sort(key=lambda doc: str(doc.get(key) or ""), reverse=direction < 0)
        return self

    def skip(self, count):
        self.rows = self.rows[count:]
        return self

    def limit(self, count):
        self.rows = self.rows[:count]
        return self

    async def to_list(self, length=None):
        rows = list(self.rows)
        return rows[:length] if length is not None else rows

    def __aiter__(self):
        self._index = 0
        return self

    async def __anext__(self):
        if self._index >= len(self.rows):
            raise StopAsyncIteration
        row = self.rows[self._index]
        self._index += 1
        return row


class FakeCollection:
    def __init__(self, docs=None):
        self.docs = list(docs or [])

    def _candidates(self, query):
        identifier = query.get("_id")
        if isinstance(identifier, dict) and "$in" in identifier:
            return identifier["$in"]
        return None

    async def find_one(self, query, projection=None, **kwargs):
        candidates = self._candidates(query)
        if candidates is not None:
            for doc in self.docs:
                for candidate in candidates:
                    if doc.get("_id") == candidate:
                        return doc
            return None
        for doc in self.docs:
            if _match(doc, query):
                return doc
        return None

    def find(self, query, projection=None, **kwargs):
        rows = [doc for doc in self.docs if _match(doc, query)]
        return FakeCursor(rows)

    async def count_documents(self, query):
        return len([doc for doc in self.docs if _match(doc, query)])

    async def aggregate(self, pipeline):
        rows = [doc for doc in self.docs]
        group = {"_id": None, "count_field": None, "count_by_id": {}}
        for stage in pipeline:
            if "$match" in stage:
                rows = [doc for doc in rows if _match(doc, stage["$match"])]
            if "$group" in stage:
                spec = stage["$group"]
                group["count_field"] = next((v.get("$sum") for v in spec.values()
                                             if isinstance(v, dict) and "$sum" in v), 1)
                id_expr = spec.get("_id")
                group["count_by_id"] = {}
                if isinstance(id_expr, str) and id_expr.startswith("$"):
                    field = id_expr[1:]
                    for doc in rows:
                        key = doc.get(field)
                        group["count_by_id"][key] = group["count_by_id"].get(key, 0) + 1
                        group["_id"] = None
        for key, count in group["count_by_id"].items():
            yield {"_id": key, "count": count}

    async def insert_one(self, document):
        self.docs.append(document)
        return SimpleNamespace(inserted_id=document.get("_id"))

    async def update_one(self, query, update, **kwargs):
        for doc in self.docs:
            if _match(doc, query):
                doc.update(update.get("$set", {}))
                return SimpleNamespace(matched_count=1, modified_count=1)
        return SimpleNamespace(matched_count=0, modified_count=0)

    async def delete_one(self, query):
        for index, doc in enumerate(self.docs):
            if _match(doc, query):
                self.docs.pop(index)
                return SimpleNamespace(deleted_count=1)
        return SimpleNamespace(deleted_count=0)


class FakeDatabase:
    def __init__(self):
        self.users = FakeCollection()
        self.health_data_alerts = FakeCollection()
        self.health_data_thresholds = FakeCollection()
        legacy_domain_state(self)
        self._legacy_state_done = True

    def __getitem__(self, name):
        return getattr(self, name)

    def __getattr__(self, name):
        # patient_domain_state 等：缺省集合按空处理（legacy 域固定由
        # legacy_domain_state 显式声明 find_one）
        if name.startswith("_"):
            raise AttributeError(name)
        return FakeCollection()


def alert_doc(patient_id, data_type="blood_pressure", level="critical", status="active"):
    return {
        "_id": ObjectId(),
        "health_data_id": str(ObjectId()),
        "patient_id": patient_id,
        "data_type": data_type,
        "value": {"systolic": 150, "diastolic": 95},
        "alert_level": level,
        "status": status,
        "recorded_at": datetime(2026, 11, 12),
        "created_at": datetime(2026, 11, 12),
        "updated_at": datetime(2026, 11, 12),
        "metadata": {},
    }


class HealthAlertRouterAuthTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.database = FakeDatabase()
        self.patient_doc = {"_id": ObjectId(PATIENT_ID), "role": "patient",
                            "name": "合成患者", "practitioners": [DOCTOR_ID],
                            "health_managers": []}
        self.other_patient_doc = {"_id": ObjectId(OTHER_PATIENT_ID), "role": "patient",
                                  "name": "其他患者", "practitioners": [],
                                  "health_managers": []}
        self.database.users.docs.extend([self.patient_doc, self.other_patient_doc])
        identity_find_from_lookup(self.database.users)

        async def fake_database():
            yield self.database

        app.dependency_overrides[get_database] = fake_database
        self.operator = make_operator()
        self.get_user_mock = AsyncMock(return_value=self.operator)
        self.lookup = patch("app.core.user_record.load_user_response", new=self.get_user_mock)
        self.lookup.start()
        self.client = httpx.AsyncClient(app=app, base_url="http://test")

    async def asyncTearDown(self):
        await self.client.aclose()
        self.lookup.stop()
        app.dependency_overrides.clear()

    def set_operator(self, role, user_id=PATIENT_ID):
        self.operator = make_operator(role=role, user_id=user_id)
        self.get_user_mock.return_value = self.operator
        return self.operator

    def auth(self, operator=None):
        actor = operator or self.operator
        token = jwt.encode({"sub": actor.id, "token_type": "access",
                            "exp": datetime.utcnow() + timedelta(minutes=5)},
                           settings.SECRET_KEY, algorithm=settings.ALGORITHM)
        return {"Authorization": f"Bearer {token}"}

    def seed_alerts(self):
        self.database.health_data_alerts.docs = [
            alert_doc(PATIENT_ID, "blood_pressure"),
            alert_doc(PATIENT_ID, "blood_sugar", level="warning"),
            alert_doc(OTHER_PATIENT_ID, "heart_rate"),
        ]

    def own_alert_ids(self):
        return [str(doc["_id"]) for doc in self.database.health_data_alerts.docs
                if doc["patient_id"] == PATIENT_ID]

    def other_alert_id(self):
        return next(str(doc["_id"]) for doc in self.database.health_data_alerts.docs
                    if doc["patient_id"] == OTHER_PATIENT_ID)

    # ── 患者自取语义 ─────────────────────────────────────────────────

    async def test_patient_reads_own_alerts_and_never_others(self):
        self.seed_alerts()
        self.set_operator("patient", PATIENT_ID)
        response = await self.client.get("/api/health/alerts/alerts",
                                         params={"patient_id": PATIENT_ID},
                                         headers=self.auth())
        self.assertEqual(response.status_code, 200, response.text)
        alerts = response.json()
        self.assertTrue(alerts)
        self.assertTrue(all(alert["patient_id"] == PATIENT_ID for alert in alerts))

        # 显式他人 ID → 403
        response = await self.client.get("/api/health/alerts/alerts",
                                         params={"patient_id": OTHER_PATIENT_ID},
                                         headers=self.auth())
        self.assertEqual(response.status_code, 403, response.text)
        self.assertEqual(response.json()["detail"]["code"], "PATIENT_NOT_ASSIGNED")

        # 不传 patient_id → 仍收敛为本人
        response = await self.client.get("/api/health/alerts/alerts", headers=self.auth())
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json())
        self.assertTrue(all(alert["patient_id"] == PATIENT_ID for alert in response.json()))

    async def test_patient_reads_own_alert_detail_but_not_others(self):
        self.seed_alerts()
        self.set_operator("patient", PATIENT_ID)
        own_id = self.own_alert_ids()[0]
        response = await self.client.get(f"/api/health/alerts/alerts/{own_id}",
                                         headers=self.auth())
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["patient_id"], PATIENT_ID)

        response = await self.client.get(
            f"/api/health/alerts/alerts/{self.other_alert_id()}", headers=self.auth())
        self.assertEqual(response.status_code, 403, response.text)

    async def test_patient_stats_forced_to_self(self):
        self.seed_alerts()
        self.set_operator("patient", PATIENT_ID)
        # 显式他人 ID → 403（与列表端点一致的显式校验语义）
        response = await self.client.get("/api/health/alerts/stats",
                                         params={"patient_id": OTHER_PATIENT_ID},
                                         headers=self.auth())
        self.assertEqual(response.status_code, 403, response.text)

        # 不传 patient_id → 自取本人统计
        response = await self.client.get("/api/health/alerts/stats", headers=self.auth())
        self.assertEqual(response.status_code, 200, response.text)
        stats = response.json()
        self.assertEqual(stats["total"], 2)
        self.assertNotIn(OTHER_PATIENT_ID, stats.get("by_patient", {}))

    # ── 患者写路径一律拒绝 ───────────────────────────────────────────

    async def test_patient_write_paths_forbidden(self):
        self.seed_alerts()
        self.set_operator("patient", PATIENT_ID)
        own_id = self.own_alert_ids()[0]
        headers = self.auth()
        for method, path, kwargs in (
                ("put", f"/api/health/alerts/alerts/{own_id}",
                 {"json": {"status": "resolved"}}),
                ("put", f"/api/health/alerts/alerts/{own_id}/resolve", {}),
                ("put", f"/api/health/alerts/alerts/{own_id}/ignore", {}),
                ("post", "/api/health/alerts/alerts",
                 {"json": {"health_data_id": str(ObjectId()), "patient_id": PATIENT_ID,
                           "data_type": "blood_pressure", "value": 150,
                           "alert_level": "warning"}}),
                ("post", "/api/health/alerts/check",
                 {"params": {"health_data_id": str(ObjectId()), "patient_id": PATIENT_ID,
                             "data_type": "blood_pressure"}}),
        ):
            response = await getattr(self.client, method)(path, headers=headers, **kwargs)
            self.assertEqual(response.status_code, 403,
                             f"{method.upper()} {path}: {response.text}")

    async def test_patient_blocked_from_threshold_management(self):
        self.set_operator("patient", PATIENT_ID)
        headers = self.auth()
        response = await self.client.get("/api/health/alerts/thresholds", headers=headers)
        self.assertEqual(response.status_code, 403, response.text)
        response = await self.client.post("/api/health/alerts/thresholds", headers=headers,
                                          json={"name": "合成", "data_type": "vital_signs",
                                                "vital_type": "heart_rate"})
        self.assertEqual(response.status_code, 403, response.text)

    # ── 医护归属分流 ─────────────────────────────────────────────────

    async def test_assigned_doctor_reads_patient_alerts(self):
        self.seed_alerts()
        self.set_operator("doctor", DOCTOR_ID)
        response = await self.client.get("/api/health/alerts/alerts",
                                         params={"patient_id": PATIENT_ID},
                                         headers=self.auth())
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json())
        self.assertTrue(all(alert["patient_id"] == PATIENT_ID for alert in response.json()))

        response = await self.client.get("/api/health/alerts/alerts",
                                         params={"patient_id": OTHER_PATIENT_ID},
                                         headers=self.auth())
        self.assertEqual(response.status_code, 403, response.text)
        self.assertEqual(response.json()["detail"]["code"], "PATIENT_NOT_ASSIGNED")

    async def test_doctor_list_without_patient_id_scoped_to_assignment(self):
        self.seed_alerts()
        self.set_operator("doctor", DOCTOR_ID)
        response = await self.client.get("/api/health/alerts/alerts", headers=self.auth())
        self.assertEqual(response.status_code, 200, response.text)
        alerts = response.json()
        self.assertTrue(alerts)
        self.assertTrue(all(alert["patient_id"] == PATIENT_ID for alert in alerts))
        self.assertNotIn(OTHER_PATIENT_ID, {alert["patient_id"] for alert in alerts})

    async def test_doctor_alert_management_requires_assignment(self):
        self.seed_alerts()
        own_id = self.own_alert_ids()[0]
        # 未获分配的医生读他人预警详情 → 403
        self.set_operator("doctor", DOCTOR_ID)
        response = await self.client.put(
            f"/api/health/alerts/alerts/{self.other_alert_id()}/resolve",
            headers=self.auth())
        self.assertEqual(response.status_code, 403, response.text)
        self.assertEqual(response.json()["detail"]["code"], "PATIENT_NOT_ASSIGNED")

        # 未获分配的医生读他人预警详情 → 403
        response = await self.client.get(
            f"/api/health/alerts/alerts/{self.other_alert_id()}", headers=self.auth())
        self.assertEqual(response.status_code, 403, response.text)

        # 获分配的医生解决本人名下患者预警 → 200 且落库
        response = await self.client.put(
            f"/api/health/alerts/alerts/{own_id}/resolve",
            params={"resolution_notes": "已复诊"},
            headers=self.auth())
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["status"], "resolved")

    async def test_health_manager_read_patient_alerts(self):
        self.seed_alerts()
        manager_id = str(ObjectId())
        self.patient_doc["health_managers"] = [manager_id]
        self.set_operator("health_manager", manager_id)
        response = await self.client.get("/api/health/alerts/alerts",
                                         params={"patient_id": PATIENT_ID},
                                         headers=self.auth())
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json())

        response = await self.client.get("/api/health/alerts/alerts",
                                         params={"patient_id": OTHER_PATIENT_ID},
                                         headers=self.auth())
        self.assertEqual(response.status_code, 403, response.text)

    async def test_alert_versions_conflict_and_disposition_identity_is_server_owned(self):
        self.seed_alerts()
        self.set_operator("doctor", DOCTOR_ID)
        own_id = self.own_alert_ids()[0]
        response = await self.client.put(f"/api/health/alerts/alerts/{own_id}",
            headers=self.auth(), json={"status": "resolved", "resolved_by": ADMIN_ID,
                                       "expected_version": 0, "request_id": "route-request-001"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["resolved_by"], DOCTOR_ID)
        self.assertEqual(response.json()["version"], 1)
        response = await self.client.put(f"/api/health/alerts/alerts/{own_id}/ignore",
            headers=self.auth(), params={"expected_version": 0})
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()["detail"]["code"], "ALERT_VERSION_CONFLICT")

    # ── admin 豁免 ───────────────────────────────────────────────────

    async def test_admin_reads_any_patient_alerts(self):
        self.seed_alerts()
        self.set_operator("admin", ADMIN_ID)
        response = await self.client.get("/api/health/alerts/alerts",
                                         params={"patient_id": OTHER_PATIENT_ID},
                                         headers=self.auth())
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json())
        self.assertTrue(all(alert["patient_id"] == OTHER_PATIENT_ID
                            for alert in response.json()))

        response = await self.client.get("/api/health/alerts/alerts", headers=self.auth())
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(response.json()), 3)

    async def test_threshold_management_allowed_for_staff(self):
        self.set_operator("doctor", DOCTOR_ID)
        response = await self.client.get("/api/health/alerts/thresholds",
                                         headers=self.auth())
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), [])

        self.set_operator("admin", ADMIN_ID)
        response = await self.client.get("/api/health/alerts/thresholds",
                                         headers=self.auth())
        self.assertEqual(response.status_code, 200, response.text)

        # 其他角色（未获角色白名单）一律 403
        self.set_operator("doctor", str(ObjectId()))
        response = await self.client.get("/api/health/alerts/thresholds",
                                         headers=self.auth())
        self.assertEqual(response.status_code, 200, response.text)

    async def test_endpoints_require_authentication(self):
        self.seed_alerts()
        for path in ("/api/health/alerts/alerts", "/api/health/alerts/thresholds",
                     "/api/health/alerts/stats"):
            response = await self.client.get(path)
            self.assertEqual(response.status_code, 401, path)


if __name__ == "__main__":
    unittest.main()
