"""Real JOSE validation and isolated Mongo atomicity; never use a production URI."""
import asyncio
import base64
import hashlib
import os
import time
import unittest
from contextlib import contextmanager, ExitStack
from unittest.mock import AsyncMock, patch
from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4
from types import SimpleNamespace

import httpx
from cryptography.fernet import Fernet
from bson import ObjectId
from fastapi import FastAPI
from joserfc import jwt
from joserfc.jwk import RSAKey
from motor.motor_asyncio import AsyncIOMotorClient

from app.integrations.identity.config import OidcSettings
from app.integrations.identity.bindings import manage_binding
from app.integrations.identity.router import router, oidc_client
from app.integrations.identity.service import OidcClient, OidcFailure, OidcUnavailable, digest, ensure_identity_indexes


URI = os.environ.get("REHAB_TEST_OIDC_MONGO_URI")


class OidcConfigurationTests(unittest.TestCase):
    def test_default_is_disabled_and_http_cannot_be_enabled(self):
        self.assertFalse(OidcSettings(_env_file=None).enabled)
        for key in ("issuer", "public_base_url"):
            config = dict(enabled=True, issuer="https://identity.test", public_base_url="https://care.test/medical",
                          client_id="care", client_secret="secret")
            config[key] = "http://127.0.0.1:12345"
            with self.assertRaises(ValueError):
                OidcSettings(_env_file=None, **config)


@unittest.skipUnless(URI, "set isolated local REHAB_TEST_OIDC_MONGO_URI")
class OidcClientTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.assertTrue(URI.startswith(("mongodb://127.0.0.1:", "mongodb://localhost:")))
        self.mongo = AsyncIOMotorClient(URI, serverSelectionTimeoutMS=3000)
        self.db = self.mongo["rehab_oidc_test_" + uuid4().hex]
        await ensure_identity_indexes(self.db)
        self.config = OidcSettings(_env_file=None, enabled=True, issuer="https://identity.test",
            public_base_url="https://care.test/medical", client_id="care", client_secret="secret",
            session_encryption_key=Fernet.generate_key().decode())
        self.key = RSAKey.generate_key(2048, parameters={"kid": "test"}, private=True)
        self.jwks_key = self.key
        self.overrides = {}
        self.metadata_overrides = {}
        self.codes = {}
        self.token_calls = 0
        self.source_active = True
        self.source_outage = False
        self.service = OidcClient(self.db, self.config, transport=httpx.MockTransport(self.provider))

    async def asyncTearDown(self):
        await self.mongo.drop_database(self.db.name)
        self.mongo.close()

    async def provider(self, request):
        if request.url.path == "/.well-known/openid-configuration":
            data = dict(issuer=self.config.issuer, authorization_endpoint=self.config.issuer + "/oidc/authorize",
                token_endpoint=self.config.issuer + "/oidc/token", jwks_uri=self.config.issuer + "/oidc/jwks",
                introspection_endpoint=self.config.issuer + "/oidc/introspect",
                revocation_endpoint=self.config.issuer + "/oidc/revoke",
                response_types_supported=["code"], code_challenge_methods_supported=["S256"],
                id_token_signing_alg_values_supported=["RS256"],
                token_endpoint_auth_methods_supported=["client_secret_basic"])
            return httpx.Response(200, json=dict(data, **self.metadata_overrides))
        if request.url.path == "/oidc/jwks":
            return httpx.Response(200, json={"keys": [self.jwks_key.as_dict(private=False)]})
        if request.url.path == "/oidc/token":
            self.token_calls += 1
            self.assertEqual(request.headers["authorization"], "Basic " + base64.b64encode(b"care:secret").decode())
            values = parse_qs(request.content.decode())
            data = self.codes.pop(values["code"][0], None)
            if not data:
                return httpx.Response(400, json={"error": "invalid_grant"})
            challenge = base64.urlsafe_b64encode(hashlib.sha256(values["code_verifier"][0].encode()).digest()).rstrip(b"=").decode()
            self.assertEqual(challenge, data["challenge"])
            self.assertEqual(values["redirect_uri"], [self.config.callback_uri])
            claims = dict(iss=self.config.issuer, sub="opaque-stable-subject", aud="care",
                          iat=int(time.time()), exp=int(time.time()) + 300, nonce=data["nonce"])
            claims.update(self.overrides)
            token = jwt.encode({"alg": "RS256", "kid": "test"}, claims, self.key)
            return httpx.Response(200, json={"access_token": "source-token-never-stored", "token_type": "Bearer",
                                             "id_token": token, "expires_in": 3600})
        if request.url.path == "/oidc/introspect":
            if self.source_outage:
                return httpx.Response(503)
            self.assertEqual(request.headers["authorization"], "Basic " + base64.b64encode(b"care:secret").decode())
            self.assertEqual(parse_qs(request.content.decode())["token"], ["source-token-never-stored"])
            return httpx.Response(200, json={"active": self.source_active, "sub": "opaque-stable-subject",
                "client_id": "care", "iss": self.config.issuer, "exp": int(time.time()) + 3600})
        if request.url.path == "/oidc/revoke":
            self.assertEqual(request.headers["authorization"], "Basic " + base64.b64encode(b"care:secret").decode())
            self.assertEqual(parse_qs(request.content.decode())["token"], ["source-token-never-stored"])
            self.source_active = False
            return httpx.Response(200, json={})
        return httpx.Response(404)

    async def begin(self):
        target, browser = await self.service.start()
        query = parse_qs(urlsplit(target).query)
        self.assertEqual(query["code_challenge_method"], ["S256"])
        self.assertEqual(query["scope"], ["openid"])
        state = query["state"][0]
        code = uuid4().hex
        self.codes[code] = {"nonce": query["nonce"][0], "challenge": query["code_challenge"][0]}
        return state, code, browser

    @contextmanager
    def unified_application(self):
        from app.main import app
        from app.db.mongodb import get_database
        self.config.authentication_mode = "oidc"
        previous = dict(app.dependency_overrides)
        async def database():
            yield self.db
        app.dependency_overrides[get_database] = database
        app.dependency_overrides[oidc_client] = lambda: self.service
        try:
            with ExitStack() as stack:
                for module in ("access", "router"):
                    stack.enter_context(patch("app.integrations.identity." + module + ".oidc_settings", self.config))
                stack.enter_context(patch("app.core.auth.oidc_settings", self.config))
                stack.enter_context(patch("app.core.auth.OidcClient", return_value=self.service))
                stack.enter_context(patch("app.integrations.identity.access.OidcClient", return_value=self.service))
                stack.enter_context(patch("app.db.mongodb.get_db", new=AsyncMock(return_value=self.db)))
                yield app
        finally:
            app.dependency_overrides.clear()
            app.dependency_overrides.update(previous)

    async def bound_session(self, role="doctor"):
        sid, csrf, _ = await self.service.callback(*(await self.begin()))
        actor_id = ObjectId()
        await self.db.users.insert_one(dict(_id=actor_id, name="Reviewed actor", email="reviewed@example.com",
            role=role, is_active=True, created_at=datetime.utcnow(), updated_at=datetime.utcnow()))
        await manage_binding(self.db, issuer=self.config.issuer, subject="opaque-stable-subject",
            actor_id=str(actor_id), reviewer="administrator", evidence_reference="review/789", apply=True, approved_role=role)
        return sid, csrf, actor_id

    async def test_success_creates_identity_only_session_without_tokens(self):
        sid, csrf, expiry = await self.service.callback(*(await self.begin()))
        self.assertGreater(expiry, 0)
        self.assertGreater(expiry, 3500)
        stored = await self.db.oidc_application_sessions.find_one({"_id": digest(sid)})
        self.assertEqual(set(stored), {"_id", "issuer", "subject", "csrf_hash", "expires_at", "source_token_encrypted"})
        self.assertNotIn("source-token-never-stored", repr(stored))
        self.assertNotIn(sid, repr(stored))
        result = await self.service.session(sid)
        self.assertEqual(result["clinical_permissions"], [])
        self.assertFalse(result["clinical_access"])
        self.assertIsNone(result["actor_id"])
        await self.service.logout(sid, csrf)
        self.assertFalse(self.source_active)
        self.assertIsNone(await self.service.session(sid))

    async def test_state_cookie_and_transaction_expiry_are_required(self):
        state, code, browser = await self.begin()
        for args in (("bad-state", code, browser), (state, code, "wrong-browser"), (state, code, None)):
            with self.assertRaises(OidcFailure):
                await self.service.callback(*args)
        self.assertEqual(self.token_calls, 0)
        await self.db.oidc_login_transactions.update_one({"_id": digest(state)}, {"$set": {"expires_at": datetime.utcnow() - timedelta(seconds=1)}})
        with self.assertRaises(OidcFailure):
            await self.service.callback(state, code, browser)

    async def test_concurrent_callbacks_exchange_exactly_once(self):
        args = await self.begin()
        results = await asyncio.gather(*(self.service.callback(*args) for _ in range(8)), return_exceptions=True)
        self.assertEqual(sum(isinstance(item, tuple) for item in results), 1)
        self.assertEqual(self.token_calls, 1)
        self.assertEqual(await self.db.oidc_application_sessions.count_documents({}), 1)

    async def test_invalid_identity_claims_fail_without_session(self):
        for claim in ({"iss": "https://attacker.test"}, {"aud": "other"}, {"nonce": "wrong"},
                      {"exp": int(time.time()) - 60}, {"iat": int(time.time()) + 300},
                      {"azp": "other"}, {"sub": ""}, {"iat": True}, {"nonce": None}):
            with self.subTest(claim=claim):
                self.overrides = claim
                with self.assertRaises(Exception):
                    await self.service.callback(*(await self.begin()))
                self.assertEqual(await self.db.oidc_application_sessions.count_documents({}), 0)

    async def test_untrusted_signing_key_cannot_establish_session(self):
        self.jwks_key = RSAKey.generate_key(2048, parameters={"kid": "test"}, private=True)
        with self.assertRaises(Exception):
            await self.service.callback(*(await self.begin()))
        self.assertEqual(await self.db.oidc_application_sessions.count_documents({}), 0)

    async def test_metadata_issuer_transport_and_client_auth_constraints(self):
        for override in ({"issuer": "https://attacker.test"}, {"token_endpoint": "http://identity.test/token"},
                         {"jwks_uri": "https://attacker.test/jwks"}, {"code_challenge_methods_supported": ["plain"]},
                         {"id_token_signing_alg_values_supported": ["HS256"]},
                         {"token_endpoint_auth_methods_supported": ["none"]}):
            with self.subTest(override=override):
                self.metadata_overrides = override
                with self.assertRaises(OidcFailure):
                    await self.service.start()

    async def test_binding_is_explicit_reviewed_and_never_inherits_roles(self):
        sid, _, _ = await self.service.callback(*(await self.begin()))
        actor_id = ObjectId()
        await self.db.users.insert_one({"_id": actor_id, "is_active": True, "role": "admin", "permissions": ["*"]})
        binding = dict(_id=digest(self.config.issuer + "\0opaque-stable-subject"), issuer=self.config.issuer,
                       subject="opaque-stable-subject", actor_id=str(actor_id), enabled=True)
        await self.db.oidc_principal_bindings.insert_one(binding)
        self.assertIsNone((await self.service.session(sid))["actor_id"])
        await self.db.oidc_principal_bindings.update_one({"_id": binding["_id"]}, {"$set": {"verified_by": "reviewer", "verified_at": datetime.utcnow(), "evidence_reference": "review/123", "approved_role": "admin"}})
        result = await self.service.session(sid)
        self.assertEqual(result["actor_id"], str(actor_id))
        self.assertEqual(result["clinical_permissions"], [])
        self.assertNotIn("role", result)
        await self.db.users.update_one({"_id": actor_id}, {"$set": {"is_active": False}})
        self.assertIsNone(await self.service.session(sid))

    async def test_logout_requires_matching_server_csrf(self):
        sid, _, _ = await self.service.callback(*(await self.begin()))
        with self.assertRaises(OidcFailure):
            await self.service.logout(sid, "forged")
        self.assertIsNotNone(await self.service.session(sid))

    async def test_expired_sessions_are_rejected_without_waiting_for_ttl_sweep(self):
        sid, _, _ = await self.service.callback(*(await self.begin()))
        await self.db.oidc_application_sessions.update_one({"_id": digest(sid)}, {"$set": {"expires_at": datetime.utcnow() - timedelta(seconds=1)}})
        self.assertIsNone(await self.service.session(sid))

    async def test_identity_cookie_cannot_authorize_existing_patient_api(self):
        from app.main import app
        from app.db.mongodb import get_database
        sid, _, _ = await self.service.callback(*(await self.begin()))
        async def database():
            yield self.db
        app.dependency_overrides[get_database] = database
        try:
            async with httpx.AsyncClient(app=app, base_url="https://care.test", cookies={"__Host-rehab_session": sid}) as browser:
                result = await browser.get("/api/users/me")
                self.assertEqual(result.status_code, 401)
        finally:
            app.dependency_overrides.clear()

    async def test_administrator_binding_is_read_only_by_default_and_audited(self):
        actor_id = str(ObjectId())
        await self.db.users.insert_one({"_id": ObjectId(actor_id), "is_active": True, "role": "doctor"})
        values = dict(issuer=self.config.issuer, subject="verified-source", actor_id=actor_id,
                      reviewer="verified-admin", evidence_reference="review/456", approved_role="doctor")
        await manage_binding(self.db, **values)
        self.assertEqual(await self.db.oidc_principal_bindings.count_documents({}), 0)
        await manage_binding(self.db, **values, apply=True)
        record = await self.db.oidc_principal_bindings.find_one({})
        self.assertEqual(record["audit"][0]["reviewer"], "verified-admin")
        self.assertNotIn("role", record)
        with self.assertRaises(ValueError):
            await manage_binding(self.db, **values, apply=True)
        await manage_binding(self.db, **values, action="disable", apply=True)
        record = await self.db.oidc_principal_bindings.find_one({})
        self.assertFalse(record["enabled"])
        self.assertEqual(len(record["audit"]), 2)
        with self.assertRaises(ValueError):
            await manage_binding(self.db, **values, apply=True)

    async def test_admin_binding_rejects_unverified_missing_actor_and_alias(self):
        actor_id = str(ObjectId())
        values = dict(issuer=self.config.issuer, subject="verified-source", actor_id=actor_id,
                      reviewer="verified-admin", evidence_reference="review/456", apply=True, approved_role="doctor")
        with self.assertRaises(ValueError):
            await manage_binding(self.db, **values)
        await self.db.users.insert_one({"_id": ObjectId(actor_id), "is_active": True, "role": "doctor"})
        with self.assertRaises(ValueError):
            await manage_binding(self.db, **dict(values, reviewer=""))
        await manage_binding(self.db, **values)
        with self.assertRaises(ValueError):
            await manage_binding(self.db, **dict(values, subject="another-source"))

    async def test_online_source_revoke_and_outage_fail_closed(self):
        sid, _, _ = await self.service.callback(*(await self.begin()))
        self.source_outage = True
        with self.assertRaises(OidcUnavailable):
            await self.service.session(sid)
        self.source_outage = False
        self.source_active = False
        self.assertIsNone(await self.service.session(sid))
        self.source_active = True
        self.assertIsNone(await self.service.session(sid))

    async def test_unified_business_auth_csrf_local_bypass_and_source_state(self):
        sid, csrf, actor_id = await self.bound_session()
        with self.unified_application() as app:
            async with httpx.AsyncClient(app=app, base_url="https://care.test", cookies={"__Host-rehab_session": sid}) as browser:
                result = await browser.get("/api/users/me")
                self.assertEqual(result.status_code, 200)
                self.assertEqual(result.json()["id"], str(actor_id))
                self.assertEqual(result.json()["role"], "doctor")
                result = await browser.get("/api/auth/session")
                self.assertTrue(result.json()["clinical_access"])
                self.assertEqual(result.json()["user"]["id"], str(actor_id))
                # Even a cryptographically valid old JWT cannot bypass the central source.
                from jose import jwt as legacy_jwt
                from app.core.config import settings
                old = legacy_jwt.encode({"sub": str(actor_id), "exp": int(time.time()) + 300}, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
                self.assertEqual((await browser.get("/api/users/me", headers={"authorization": "Bearer " + old})).status_code, 401)
                for path in ("login", "login/refresh", "refresh-token", "register"):
                    self.assertEqual((await browser.post("/api/users/" + path, json={})).status_code, 403)
                self.assertEqual((await browser.put("/api/users/me", json={"name": "forged"})).status_code, 403)
                good = {"origin": "https://care.test", "x-csrf-token": csrf}
                result = await browser.put("/api/users/me", json={"name": "Approved display"}, headers=good)
                self.assertEqual(result.status_code, 200)
                self.assertEqual((await self.db.users.find_one({"_id": actor_id}))["name"], "Approved display")
                self.source_outage = True
                self.assertEqual((await browser.get("/api/users/me")).status_code, 503)
                self.assertEqual((await browser.put("/api/users/me", json={"name": "must not write"}, headers=good)).status_code, 503)
                self.source_outage = False
                self.source_active = False
                self.assertEqual((await browser.get("/api/users/me")).status_code, 401)
                self.assertEqual((await self.db.users.find_one({"_id": actor_id}))["name"], "Approved display")

    async def test_reviewed_role_does_not_bypass_patient_scope_or_survive_role_change(self):
        sid, _, actor_id = await self.bound_session()
        assigned, unrelated = ObjectId(), ObjectId()
        await self.db.users.insert_many([
            {"_id": assigned, "role": "patient", "practitioners": [str(actor_id)]},
            {"_id": unrelated, "role": "patient", "practitioners": []}])
        with self.unified_application() as app:
            async with httpx.AsyncClient(app=app, base_url="https://care.test", cookies={"__Host-rehab_session": sid}) as browser:
                self.assertEqual((await browser.get("/api/health-records", params={"patient_id": str(assigned)})).status_code, 200)
                self.assertEqual((await browser.get("/api/health-records", params={"patient_id": str(unrelated)})).status_code, 403)
                self.assertEqual((await browser.get("/api/users/")).status_code, 403)
                self.assertIsNotNone(await self.db.audit_logs.find_one({"user_id": str(actor_id), "resource_type": "permission"}))
                # Application permissions remain local; a role change requires new explicit review.
                await self.db.users.update_one({"_id": actor_id}, {"$set": {"role": "admin"}})
                self.assertEqual((await browser.get("/api/users/me")).status_code, 401)
                await manage_binding(self.db, issuer=self.config.issuer, subject="opaque-stable-subject",
                    actor_id=str(actor_id), reviewer="administrator", evidence_reference="review/new-role",
                    action="review-role", apply=True, approved_role="admin")
                self.assertEqual((await browser.get("/api/users/me")).status_code, 401)
                fresh_sid, _, _ = await self.service.callback(*(await self.begin()))
                browser.cookies.clear()
                browser.cookies.set("__Host-rehab_session", fresh_sid, domain="care.test", path="/")
                self.assertEqual((await browser.get("/api/users/me")).status_code, 200)

    async def test_unified_communication_uses_real_user_response_contract(self):
        sid, _, actor_id = await self.bound_session()
        conversation = ObjectId()
        await self.db.conversations.insert_one(dict(_id=conversation, participant1_id=str(actor_id),
            participant2_id=str(ObjectId()), type="chat", status="active", created_at=datetime.utcnow()))
        with self.unified_application() as app:
            async with httpx.AsyncClient(app=app, base_url="https://care.test", cookies={"__Host-rehab_session": sid}) as browser:
                result = await browser.get("/api/communications/conversations")
                self.assertEqual(result.status_code, 200)
                self.assertEqual(result.json()[0]["id"], str(conversation))

    async def test_unified_notification_uses_patient_response_and_preserves_recipient_scope(self):
        sid, csrf, actor_id = await self.bound_session(role="patient")
        own, other = ObjectId(), ObjectId()
        await self.db.notifications.insert_many([
            {"_id": own, "recipient_id": str(actor_id), "read": False},
            {"_id": other, "recipient_id": str(ObjectId()), "read": False}])
        with self.unified_application() as app:
            async with httpx.AsyncClient(app=app, base_url="https://care.test", cookies={"__Host-rehab_session": sid}) as browser:
                result = await browser.get("/api/notifications/unread/count")
                self.assertEqual(result.status_code, 200)
                self.assertEqual(result.json(), 1)
                headers = {"origin": "https://care.test", "x-csrf-token": csrf}
                self.assertEqual((await browser.put(f"/api/notifications/{other}/read", headers=headers)).status_code, 404)
                self.assertFalse((await self.db.notifications.find_one({"_id": other}))["read"])
                self.assertEqual((await browser.put(f"/api/notifications/{own}/read", headers=headers)).status_code, 200)
                self.assertEqual((await browser.get("/api/notifications/unread/count")).json(), 0)

    async def test_unified_admin_users_route_audits_with_real_motor_database(self):
        sid, _, actor_id = await self.bound_session(role="admin")
        with self.unified_application() as app:
            async with httpx.AsyncClient(app=app, base_url="https://care.test", cookies={"__Host-rehab_session": sid}) as browser:
                result = await browser.get("/api/users/")
                self.assertEqual(result.status_code, 200)
                self.assertEqual(result.json()[0]["id"], str(actor_id))
                from app.schemas.user import UserResponse
                from app.core.permissions import PermissionChecker, Permission
                self.assertTrue(await PermissionChecker.check_permission_with_audit(
                    UserResponse.model_validate(result.json()[0]), Permission.SYSTEM_ADMIN, db=self.db))
        self.assertIsNotNone(await self.db.audit_logs.find_one({"user_id": str(actor_id), "resource_type": "permission"}))

    async def test_proxy_prefix_preserves_local_auth_gate_callback_and_audit_identity(self):
        sid, _, actor_id = await self.bound_session(role="patient")
        auditor = SimpleNamespace(create_log=AsyncMock(return_value={}))
        with self.unified_application() as app, patch.object(app, "root_path", "/medical"), \
                patch("app.db.mongodb.db.is_connected", return_value=True), \
                patch("app.core.permission_audit.AuditLogService", return_value=auditor):
            async with httpx.AsyncClient(app=app, base_url="https://care.test", cookies={"__Host-rehab_session": sid}) as browser:
                result = await browser.post("/api/users/login", json={})
                self.assertEqual(result.status_code, 403)
                self.assertEqual(result.json()["code"], "LOCAL_AUTH_DISABLED")
                result = await browser.get("/api/users/me")
                self.assertEqual(result.status_code, 200)
                self.assertEqual(auditor.create_log.call_args.kwargs["log_data"].user_id, str(actor_id))
                result = await browser.get("/api/auth/oidc/callback?error=access_denied",
                                           headers={"origin": "https://identity.test"})
                self.assertEqual(result.status_code, 303)
                self.assertEqual(result.headers["location"], "https://care.test/medical/auth/oidc/complete?error=OIDC_VALIDATION_FAILED")

    async def test_websocket_cookie_origin_and_outbound_revocation_checks(self):
        from starlette.websockets import WebSocket
        from app.core.auth import get_current_user_ws
        from app.api.websockets import ConnectionManager, receive_authorized
        from fastapi import WebSocketDisconnect
        sid, _, actor_id = await self.bound_session()
        def connection(origin="https://care.test", query=b""):
            return WebSocket({"type": "websocket", "path": "/ws/notifications", "query_string": query,
                "headers": [(b"origin", origin.encode()), (b"cookie", ("__Host-rehab_session=" + sid).encode())]},
                receive=AsyncMock(), send=AsyncMock())
        with self.unified_application():
            live = connection()
            self.assertEqual(str((await get_current_user_ws(live, self.db))["_id"]), str(actor_id))
            self.assertIsNone(await get_current_user_ws(connection("https://evil.test"), self.db))
            self.assertIsNone(await get_current_user_ws(connection(query=b"token=old"), self.db))
            async def validator():
                return bool(await get_current_user_ws(live, self.db))
            socket = SimpleNamespace(scope={"identity_validator": validator}, send_json=AsyncMock(), close=AsyncMock(),
                                     receive_text=AsyncMock(return_value="must not reach business handler"))
            manager = ConnectionManager()
            manager.active_connections[str(actor_id)] = {"c1": socket}
            self.source_active = False
            with self.assertRaises(WebSocketDisconnect):
                await receive_authorized(socket)
            await manager.send_personal_message({"sensitive": "not delivered"}, str(actor_id))
            socket.send_json.assert_not_awaited()
            self.assertNotIn(str(actor_id), manager.active_connections)

    async def test_idle_websocket_rechecks_without_inbound_frames(self):
        from app.api.websockets import receive_authorized
        from fastapi import WebSocketDisconnect
        sid, _, _ = await self.bound_session()
        self.source_active = False
        async def allowed():
            _, actor = await self.service.actor_for_session(sid)
            return actor is not None
        async def idle():
            await asyncio.Event().wait()
        socket = SimpleNamespace(scope={"identity_validator": allowed}, close=AsyncMock(), receive_text=idle)
        with patch("app.api.websockets.IDENTITY_RECHECK_SECONDS", 0.02):
            with self.assertRaises(WebSocketDisconnect):
                await asyncio.wait_for(receive_authorized(socket), timeout=1)
        socket.close.assert_awaited_once_with(code=4401)
    async def test_cookie_routes_are_secure_and_csrf_protected(self):
        app = FastAPI()
        app.include_router(router, prefix="/api")
        app.dependency_overrides[oidc_client] = lambda: self.service
        from unittest.mock import patch
        with patch("app.integrations.identity.router.oidc_settings", self.config):
            async with httpx.AsyncClient(app=app, base_url="https://care.test") as browser:
                result = await browser.get("/api/auth/oidc/start")
                self.assertEqual(result.status_code, 303)
                self.assertIn("Secure", result.headers["set-cookie"])
                self.assertIn("HttpOnly", result.headers["set-cookie"])
                self.assertNotIn("Domain=", result.headers["set-cookie"])
                state, code, secret = await self.begin()
                browser.cookies.set("__Host-rehab_oidc", secret, domain="care.test", path="/")
                result = await browser.get("/api/auth/oidc/callback", params={"state": state, "code": code})
                self.assertEqual(result.status_code, 303)
                self.assertEqual(result.headers["location"], self.config.session_uri)
                self.assertEqual((await browser.get("/api/auth/session")).status_code, 200)
                self.assertEqual((await browser.post("/api/auth/logout", headers={"origin": "https://evil.test"})).status_code, 403)
                csrf = browser.cookies.get("__Host-rehab_csrf")
                result = await browser.post("/api/auth/logout", headers={"origin": "https://care.test", "x-csrf-token": csrf})
                self.assertEqual(result.status_code, 204)
                self.assertEqual((await browser.get("/api/auth/session")).status_code, 401)
