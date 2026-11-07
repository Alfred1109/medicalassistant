import unittest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from jose import jwt

from app.core import auth, dependencies
from app.core.config import settings
from app.db.mongodb import get_database
from app.main import app
from app.schemas.user import UserResponse
from app.services.user_service import UserService


class AuthenticationContractTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.user = UserResponse(
            id="507f1f77bcf86cd799439011", email="actor@example.com",
            name="Test actor", role="doctor", is_active=True,
            createdAt=datetime.utcnow(), updatedAt=datetime.utcnow(),
        )

        async def fake_database():
            yield MagicMock()

        app.dependency_overrides[get_database] = fake_database
        self.lookup = patch.object(UserService, "get_user_by_id", new=AsyncMock(return_value=self.user))
        self.lookup.start()
        self.client = httpx.AsyncClient(app=app, base_url="http://test")

    async def asyncTearDown(self):
        await self.client.aclose()
        self.lookup.stop()
        app.dependency_overrides.clear()

    def token(self, **claims):
        payload = {"sub": self.user.id, "exp": datetime.utcnow() + timedelta(minutes=5)}
        payload.update(claims)
        return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

    async def request(self, token):
        return await self.client.get("/api/users/me", headers={"Authorization": f"Bearer {token}"})

    async def test_both_dependency_modules_share_one_authenticator(self):
        self.assertIs(dependencies.get_current_user, auth.get_current_user)
        response = await self.request(self.token())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], self.user.id)

    async def test_typed_access_token_works_and_refresh_token_is_rejected(self):
        self.assertEqual((await self.request(self.token(token_type="access"))).status_code, 200)
        self.assertEqual((await self.request(self.token(token_type="refresh"))).status_code, 401)

    async def test_invalid_expired_and_missing_expiry_are_rejected(self):
        missing_expiry = jwt.encode({"sub": self.user.id}, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
        for token in ("invalid", missing_expiry, self.token(exp=datetime.utcnow() - timedelta(seconds=1)),
                      self.token(sub=""), self.token(token_type=None),
                      *(self.token(exp=value) for value in (None, [], {}, True, "9999999999", 10**400))):
            with self.subTest(token_kind=token[:8]):
                self.assertEqual((await self.request(token)).status_code, 401)

    async def test_disabled_account_is_rejected(self):
        UserService.get_user_by_id.return_value = self.user.model_copy(update={"is_active": False})
        self.assertEqual((await self.request(self.token())).status_code, 403)

    async def test_database_failure_is_not_reported_as_invalid_token(self):
        UserService.get_user_by_id.side_effect = RuntimeError("database unavailable")
        response = await self.request(self.token())
        self.assertEqual(response.status_code, 500)


class UserLookupTests(unittest.IsolatedAsyncioTestCase):
    async def test_database_failure_is_not_conflated_with_missing_user(self):
        database = MagicMock()
        database.users.find_one = AsyncMock(side_effect=RuntimeError("database unavailable"))
        service = UserService(database)
        with self.assertRaisesRegex(RuntimeError, "database unavailable"):
            await service.get_user_by_id("507f1f77bcf86cd799439011")

    async def test_malformed_identifier_returns_no_user(self):
        service = UserService(MagicMock())
        self.assertIsNone(await service.get_user_by_id("not-an-object-id"))


class RefreshTokenTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.user_id = "507f1f77bcf86cd799439011"
        self.database = MagicMock()
        self.database.users.find_one = AsyncMock()
        self.service = UserService(self.database)
        self.service.get_user_by_id = AsyncMock(return_value=MagicMock(is_active=True))
        self.service.create_token_with_refresh = AsyncMock(return_value="issued")

    def token(self, **claims):
        payload = {"sub": self.user_id, "token_type": "refresh",
                   "exp": datetime.utcnow() + timedelta(minutes=5)}
        payload.update(claims)
        return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

    async def test_invalid_and_untyped_tokens_fail_without_internal_error(self):
        no_expiry = jwt.encode({"sub": self.user_id, "token_type": "refresh"},
                               settings.SECRET_KEY, algorithm=settings.ALGORITHM)
        for token in ("invalid", no_expiry, self.token(token_type="access"), self.token(sub="invalid"),
                      *(self.token(exp=value) for value in (None, [], {}, True, "9999999999", 10**400))):
            with self.subTest(kind=token[:8]):
                with self.assertRaises(ValueError):
                    await self.service.refresh_access_token(token)

    async def test_disabled_user_cannot_refresh(self):
        self.service.get_user_by_id.return_value = MagicMock(is_active=False)
        with self.assertRaises(ValueError):
            await self.service.refresh_access_token(self.token())
        self.database.users.find_one.assert_not_awaited()

    async def test_token_and_expiry_must_match_same_stored_entry(self):
        token = self.token()
        self.database.users.find_one.return_value = {"_id": self.user_id}
        self.assertEqual(await self.service.refresh_access_token(token), "issued")
        query = self.database.users.find_one.await_args.args[0]
        self.assertEqual(query["refresh_tokens"]["$elemMatch"]["token"], token)
        self.assertIn("$gt", query["refresh_tokens"]["$elemMatch"]["expires_at"])
        self.assertEqual(query["is_active"], {"$ne": False})

    async def test_database_failure_is_not_invalid_token(self):
        self.service.get_user_by_id.side_effect = RuntimeError("database unavailable")
        with self.assertRaisesRegex(RuntimeError, "database unavailable"):
            await self.service.refresh_access_token(self.token())


class WebSocketAuthenticationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.user_id = "507f1f77bcf86cd799439011"
        self.database = MagicMock()
        self.database.users.find_one = AsyncMock(return_value={"_id": self.user_id, "is_active": True})

    def token(self, **claims):
        payload = {"sub": self.user_id, "exp": datetime.utcnow() + timedelta(minutes=5)}
        payload.update(claims)
        return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

    async def authenticate(self, token):
        websocket = MagicMock()
        websocket.query_params = {"token": token}
        websocket.cookies = {}
        return await auth.get_current_user_ws(websocket, self.database)

    async def authenticate_via_cookie(self, token):
        websocket = MagicMock()
        websocket.query_params = {}
        websocket.cookies = {settings.TOKEN_COOKIE_NAME: token} if token else {}
        return await auth.get_current_user_ws(websocket, self.database)

    async def test_valid_access_uses_same_subject_as_http(self):
        self.assertIsNotNone(await self.authenticate(self.token(token_type="access")))
        self.database.users.find_one.assert_awaited_once()

    async def test_refresh_missing_expiry_and_invalid_subject_are_rejected(self):
        no_expiry = jwt.encode({"sub": self.user_id}, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
        for token in (self.token(token_type="refresh"), self.token(token_type=None), no_expiry,
                      self.token(exp=datetime.utcnow() - timedelta(seconds=1)),
                      self.token(sub="invalid"),
                      *(self.token(exp=value) for value in (None, [], {}, True, "9999999999", 10**400))):
            self.assertIsNone(await self.authenticate(token))
        self.database.users.find_one.assert_not_awaited()

    async def test_disabled_user_is_rejected(self):
        self.database.users.find_one.return_value = {"_id": self.user_id, "is_active": False}
        self.assertIsNone(await self.authenticate(self.token()))

    async def test_cookie_fallback_authenticates_when_query_param_absent(self):
        self.assertIsNotNone(await self.authenticate_via_cookie(self.token(token_type="access")))
        self.database.users.find_one.assert_awaited_once()

    async def test_cookie_fallback_without_token_returns_none(self):
        self.assertIsNone(await self.authenticate_via_cookie(None))
        self.database.users.find_one.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
