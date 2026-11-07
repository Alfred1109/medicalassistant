"""AUTH01 契约：通用自助资料接口（PUT /api/users/me）不可修改密码、账号状态及授权；
通用用户管理端点的权限检查真实生效。

固化（2026-11-07）：
- ``SelfUserUpdate``（backend/app/schemas/user.py）只声明 ``name`` 且 ``extra=forbid``，
  PUT /me 对密码/状态/授权字段的拒绝完全依赖该 schema 的单点约束；
- 通用用户管理端点（PUT /users/{id}、POST /users/permissions 等）通过
  ``Depends(require_permission(...))`` 声明权限：未认证 401、普通用户 403、
  管理员 200（require_permission 已修复为依赖工厂，授权真实生效）。

若未来 schema 放开字段或权限检查回归，本文件中的用例应失败并暴露该风险。
"""

import unittest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from bson.objectid import ObjectId
from jose import jwt

from app.core.config import settings
from app.db.mongodb import get_database
from app.main import app
from app.schemas.user import SelfUserUpdate, UserResponse, UserUpdate
from app.services.user_service import UserService


class SelfProfileContractTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.user = UserResponse(
            id="507f1f77bcf86cd799439011", email="actor@example.com",
            name="Original name", role="patient", is_active=True,
            createdAt=datetime.utcnow(), updatedAt=datetime.utcnow(),
        )
        self.other_user_id = "5f1f77bcf86cd7994390999"

        async def fake_database():
            yield MagicMock()

        app.dependency_overrides[get_database] = fake_database
        self.get_user_by_id_mock = AsyncMock(return_value=self.user)
        self.lookup = patch.object(UserService, "get_user_by_id", new=self.get_user_by_id_mock)
        self.lookup.start()
        # 任何触达密码哈希逻辑的路径都应使测试失败，作为"密码不变"的显式证据
        self.hash_guard = patch.object(
            UserService, "_get_password_hash",
            side_effect=AssertionError("self-service endpoint attempted to touch password hash"),
        )
        self.hash_guard.start()
        self.update_user = patch.object(UserService, "update_user", new=AsyncMock(return_value=self.user))
        self.update_user.start()
        self.client = httpx.AsyncClient(app=app, base_url="http://test")

    async def asyncTearDown(self):
        await self.client.aclose()
        self.lookup.stop()
        self.hash_guard.stop()
        self.update_user.stop()
        app.dependency_overrides.clear()

    def token(self, **claims):
        payload = {
            "sub": self.user.id,
            "exp": datetime.utcnow() + timedelta(minutes=5),
            "token_type": "access",
        }
        payload.update(claims)
        return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

    def auth_headers(self, **claims):
        return {"Authorization": f"Bearer {self.token(**claims)}"}

    async def test_schema_level_extra_fields_are_forbidden(self):
        # 单点防线：SelfUserUpdate 必须 extra=forbid，否则下面的 HTTP 契约失去依托
        with self.assertRaises(ValueError):
            SelfUserUpdate.model_validate({"name": "x", "password": "new-secret"})

    async def test_put_me_rejects_password_and_leaves_hash_untouched(self):
        response = await self.client.put(
            "/api/users/me", headers=self.auth_headers(), json={"name": "x", "password": "new-secret"}
        )
        self.assertEqual(response.status_code, 422)
        UserService.update_user.assert_not_awaited()

    async def test_put_me_rejects_account_state_and_authorization_fields(self):
        for field, value in (
            ("is_active", False),
            ("role", "admin"),
            ("permissions", ["user:update", "system:admin"]),
            ("email", "attacker@example.com"),
        ):
            with self.subTest(field=field):
                response = await self.client.put(
                    "/api/users/me", headers=self.auth_headers(), json={"name": "x", field: value}
                )
                self.assertEqual(response.status_code, 422, response.text)
        UserService.update_user.assert_not_awaited()

    async def test_put_me_accepts_name_and_updates_only_allowed_fields(self):
        updated = self.user.model_copy(update={"name": "New display name"})
        UserService.update_user.return_value = updated

        response = await self.client.put(
            "/api/users/me", headers=self.auth_headers(), json={"name": "New display name"}
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["name"], "New display name")
        self.assertEqual(response.json()["role"], "patient")
        UserService.update_user.assert_awaited_once()
        target_id, update_data = UserService.update_user.await_args.args
        self.assertEqual(target_id, self.user.id)
        # 只有 name 真正提交给服务层
        self.assertEqual(update_data.model_dump(exclude_unset=True), {"name": "New display name"})
        self.assertIsNone(update_data.password)
        self.assertIsNone(update_data.role)
        self.assertIsNone(update_data.permissions)
        self.assertIsNone(update_data.is_active)

    async def test_me_requires_authentication(self):
        for method, path, kwargs in (
            ("get", "/api/users/me", {}),
            ("put", "/api/users/me", {"json": {"name": "x"}}),
        ):
            with self.subTest(method=method):
                response = await getattr(self.client, method)(path, **kwargs)
                self.assertEqual(response.status_code, 401, response.text)
        UserService.update_user.assert_not_awaited()

    async def test_self_service_cannot_update_another_user(self):
        # PUT /users/{id} 需要 user:update 权限（admin 专属）：普通用户 403，
        # 请求不得触达服务层。
        response = await self.client.put(
            f"/api/users/{self.other_user_id}", headers=self.auth_headers(),
            json={"role": "admin", "is_active": False, "password": "x"},
        )
        self.assertEqual(response.status_code, 403, response.text)
        UserService.update_user.assert_not_awaited()

    async def test_self_service_cannot_assign_permissions_to_anyone(self):
        # POST /users/permissions 需要 user:update 权限：普通用户 403，不触达服务层。
        with patch.object(UserService, "update_user_permissions", new=AsyncMock()) as mock:
            response = await self.client.post(
                "/api/users/permissions", headers=self.auth_headers(),
                json={"user_id": self.other_user_id, "permissions": ["system:admin"]},
            )
            self.assertEqual(response.status_code, 403, response.text)
            mock.assert_not_awaited()

    async def test_self_service_cannot_activate_accounts(self):
        # POST /users/activate/{id} 需要 user:update 权限：普通用户 403。
        with patch.object(UserService, "activate_user", new=AsyncMock()) as mock:
            response = await self.client.post(
                f"/api/users/activate/{self.other_user_id}", headers=self.auth_headers()
            )
            self.assertEqual(response.status_code, 403, response.text)
            mock.assert_not_awaited()

    async def test_user_management_requires_authentication(self):
        # 未认证访问用户管理端点：401（而非 422/403）
        for method, path, kwargs in (
            ("get", f"/api/users/{self.other_user_id}", {}),
            ("get", "/api/users/", {}),
            ("post", "/api/users/create", {"json": {
                "email": "new@example.com", "password": "secret123", "name": "New User",
            }}),
            ("put", f"/api/users/{self.other_user_id}", {"json": {"name": "x"}}),
            ("delete", f"/api/users/{self.other_user_id}", {}),
            ("post", "/api/users/permissions", {"json": {
                "user_id": self.other_user_id, "permissions": ["system:admin"],
            }}),
            ("post", f"/api/users/activate/{self.other_user_id}", {}),
        ):
            with self.subTest(method=method):
                response = await getattr(self.client, method)(path, **kwargs)
                self.assertEqual(response.status_code, 401, response.text)
        UserService.update_user.assert_not_awaited()

    async def test_patient_is_forbidden_on_user_management_endpoints(self):
        # 普通用户（patient）访问全部用户管理端点：403（而非 422），
        # 且所有服务层调用都不得发生。
        service_mocks = {
            name: patch.object(UserService, name, new=AsyncMock())
            for name in ("list_users", "create_user", "deactivate_user",
                         "update_user_permissions", "activate_user")
        }
        for p in service_mocks.values():
            p.start()
        try:
            for method, path, kwargs in (
                ("get", f"/api/users/{self.other_user_id}", {}),
                ("get", "/api/users/", {}),
                ("post", "/api/users/create", {"json": {
                    "email": "new@example.com", "password": "secret123", "name": "New User",
                }}),
                ("put", f"/api/users/{self.other_user_id}", {"json": {"name": "x"}}),
                ("delete", f"/api/users/{self.other_user_id}", {}),
                ("post", "/api/users/permissions", {"json": {
                    "user_id": self.other_user_id, "permissions": ["system:admin"],
                }}),
                ("post", f"/api/users/activate/{self.other_user_id}", {}),
            ):
                kwargs.setdefault("headers", self.auth_headers())
                with self.subTest(method=method):
                    response = await getattr(self.client, method)(path, **kwargs)
                    self.assertEqual(response.status_code, 403, response.text)
            for name, mock in (
                ("update_user", UserService.update_user),
                ("list_users", UserService.list_users),
                ("create_user", UserService.create_user),
                ("deactivate_user", UserService.deactivate_user),
                ("update_user_permissions", UserService.update_user_permissions),
                ("activate_user", UserService.activate_user),
            ):
                mock.assert_not_awaited()
        finally:
            for p in service_mocks.values():
                p.stop()

    async def test_admin_can_read_and_update_users(self):
        # 管理员：user:update/user:read 权限检查通过，端点真实可用（200，非 422）
        admin = self.user.model_copy(update={"role": "admin"})
        UserService.get_user_by_id.return_value = admin

        # GET /users/{id}
        response = await self.client.get(
            f"/api/users/{self.other_user_id}", headers=self.auth_headers()
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["id"], self.user.id)

        # PUT /users/{id}
        updated = self.user.model_copy(update={"name": "Admin updated"})
        UserService.update_user.return_value = updated
        response = await self.client.put(
            f"/api/users/{self.other_user_id}", headers=self.auth_headers(),
            json={"name": "Admin updated"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["name"], "Admin updated")

    async def test_admin_can_list_users(self):
        admin = self.user.model_copy(update={"role": "admin"})
        UserService.get_user_by_id.return_value = admin
        with patch.object(UserService, "list_users", new=AsyncMock(return_value=[admin])):
            response = await self.client.get("/api/users/", headers=self.auth_headers())
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()[0]["id"], self.user.id)

    async def test_admin_can_create_and_deactivate_users(self):
        admin = self.user.model_copy(update={"role": "admin"})
        UserService.get_user_by_id.return_value = admin

        # POST /users/create（user:create 权限）。路由声明 200（/register 才是 201）。
        created = admin.model_copy(update={"email": "new@example.com", "name": "New User"})
        with patch.object(UserService, "create_user", new=AsyncMock(return_value=created)):
            response = await self.client.post(
                "/api/users/create", headers=self.auth_headers(),
                json={"email": "new@example.com", "password": "secret123", "name": "New User"},
            )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["email"], "new@example.com")

        # DELETE /users/{id}（user:update 权限，实际是停用）
        with patch.object(UserService, "deactivate_user", new=AsyncMock(return_value=True)):
            response = await self.client.delete(
                f"/api/users/{self.other_user_id}", headers=self.auth_headers()
            )
        self.assertEqual(response.status_code, 204, response.text)

    async def test_admin_can_update_permissions_and_operator_id_is_passed(self):
        # POST /users/permissions 走通（不再 500）：operator_id 必须来自当前管理员
        admin = self.user.model_copy(update={"role": "admin"})
        UserService.get_user_by_id.return_value = admin
        target = self.user.model_copy(update={"id": self.other_user_id, "role": "patient"})
        update_perms_mock = AsyncMock(return_value=target)
        with patch.object(UserService, "update_user_permissions", new=update_perms_mock):
            response = await self.client.post(
                "/api/users/permissions", headers=self.auth_headers(),
                json={"user_id": self.other_user_id, "permissions": ["user:read"]},
            )
        self.assertEqual(response.status_code, 200, response.text)
        update_perms_mock.assert_awaited_once()
        target_id, permissions = update_perms_mock.await_args.args
        self.assertEqual(target_id, self.other_user_id)
        self.assertEqual(permissions, ["user:read"])
        self.assertEqual(update_perms_mock.await_args.kwargs.get("operator_id"), admin.id)

    async def test_admin_can_activate_accounts(self):
        admin = self.user.model_copy(update={"role": "admin"})
        UserService.get_user_by_id.return_value = admin
        with patch.object(UserService, "activate_user", new=AsyncMock(return_value=True)):
            response = await self.client.post(
                f"/api/users/activate/{self.other_user_id}", headers=self.auth_headers()
            )
        self.assertEqual(response.status_code, 200, response.text)


MALFORMED_ID = "not-an-objectid"
VALID_ID = "507f1f77bcf86cd799439011"


class MalformedUserIdGuardContractTests(unittest.IsolatedAsyncioTestCase):
    """畸形 user_id 防护契约：写路径与读路径 get_user_by_id 语义一致。

    get_user_by_id（backend/app/services/user_service.py）把 bson errors.InvalidId
    转换为"用户不存在"（返回 None，路由层 404）。所有以字符串 user_id 查询的
    写方法（update_user / deactivate_user / activate_user / update_user_permissions /
    assign_practitioner / remove_practitioner，以及权限判定 has_permission）必须
    保持同一语义：畸形 ObjectId 视为用户不存在，返回 None/False → 路由层 404，
    绝不因 ObjectId() 构造异常而 500，也不得触达数据库写入。
    """

    async def asyncSetUp(self):
        self.admin_oid = ObjectId(VALID_ID)
        now = datetime.utcnow()
        # get_current_user / require_permission 会真实查库解析 actor，
        # 返回一个管理员文档；目标 ID 畸形时防护应短路，不触达任何写入。
        self.admin_doc = {
            "_id": self.admin_oid,
            "email": "admin@example.com",
            "name": "Admin",
            "role": "admin",
            "permissions": [],
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        }
        self.db = MagicMock()
        self.db.users.find_one = AsyncMock(return_value=self.admin_doc)
        self.db.users.update_one = AsyncMock()

        async def fake_database():
            yield self.db

        app.dependency_overrides[get_database] = fake_database
        self.client = httpx.AsyncClient(app=app, base_url="http://test")

    async def asyncTearDown(self):
        await self.client.aclose()
        app.dependency_overrides.clear()

    def auth_headers(self):
        payload = {
            "sub": str(self.admin_oid),
            "exp": datetime.utcnow() + timedelta(minutes=5),
            "token_type": "access",
        }
        return {"Authorization": f"Bearer {jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)}"}

    async def test_malformed_ids_on_user_write_endpoints_return_404_not_500(self):
        # 管理员身份下，畸形 ID 的写请求一律 404（与读路径 GET /users/{id} 一致）
        for method, path, kwargs in (
            ("put", f"/api/users/{MALFORMED_ID}", {"json": {"name": "x"}}),
            ("delete", f"/api/users/{MALFORMED_ID}", {}),
            ("post", f"/api/users/activate/{MALFORMED_ID}", {}),
            ("post", "/api/users/permissions", {"json": {
                "user_id": MALFORMED_ID, "permissions": ["user:read"],
            }}),
        ):
            with self.subTest(method=method, path=path):
                response = await getattr(self.client, method)(path, headers=self.auth_headers(), **kwargs)
                self.assertEqual(response.status_code, 404, response.text)
        # 防护必须短路：任何畸形 ID 都不得触达数据库写入
        self.db.users.update_one.assert_not_awaited()

    async def test_malformed_ids_on_practitioner_endpoints_return_404_not_500(self):
        # 患者 ID 或医疗人员 ID 任一畸形：分配/移除均 404（practitioner_id 为查询参数）
        response = await self.client.post(
            f"/api/users/patients/{MALFORMED_ID}/practitioners",
            params={"practitioner_id": VALID_ID},
            headers=self.auth_headers(),
        )
        self.assertEqual(response.status_code, 404, response.text)

        response = await self.client.post(
            f"/api/users/patients/{VALID_ID}/practitioners",
            params={"practitioner_id": MALFORMED_ID},
            headers=self.auth_headers(),
        )
        self.assertEqual(response.status_code, 404, response.text)

        response = await self.client.delete(
            f"/api/users/patients/{VALID_ID}/practitioners/{MALFORMED_ID}",
            headers=self.auth_headers(),
        )
        self.assertEqual(response.status_code, 404, response.text)

        response = await self.client.delete(
            f"/api/users/patients/{MALFORMED_ID}/practitioners/{VALID_ID}",
            headers=self.auth_headers(),
        )
        self.assertEqual(response.status_code, 404, response.text)
        self.db.users.update_one.assert_not_awaited()

    async def test_service_layer_guards_short_circuit_before_db_access(self):
        # 服务层直测：畸形 ID 返回与"用户不存在"一致的 None/False，且零数据库访问
        service = UserService(self.db)
        self.assertIsNone(await service.update_user(MALFORMED_ID, UserUpdate()))
        self.assertFalse(await service.deactivate_user(MALFORMED_ID))
        self.assertFalse(await service.activate_user(MALFORMED_ID))
        self.assertIsNone(await service.update_user_permissions(
            MALFORMED_ID, ["user:read"], operator_id=str(self.admin_oid),
        ))
        self.assertFalse(await service.has_permission(MALFORMED_ID, "user:read"))
        self.assertIsNone(await service.assign_practitioner(MALFORMED_ID, str(self.admin_oid)))
        self.assertIsNone(await service.assign_practitioner(str(self.admin_oid), MALFORMED_ID))
        self.assertIsNone(await service.remove_practitioner(str(self.admin_oid), MALFORMED_ID))
        self.assertIsNone(await service.remove_practitioner(MALFORMED_ID, str(self.admin_oid)))
        self.db.users.update_one.assert_not_awaited()
        self.db.users.find_one.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
