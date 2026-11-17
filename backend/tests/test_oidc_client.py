"""Real JOSE validation and isolated Mongo atomicity; never use a production URI."""
import asyncio
import base64
import hashlib
import os
import time
import unittest
from contextlib import contextmanager, ExitStack
from unittest.mock import AsyncMock, patch
from datetime import datetime, timedelta, timezone
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
from app.integrations.identity.router import router, oidc_client, public_api_url
from app.integrations.identity.access import mini_bearer_route, mini_proof_route
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

    def test_mini_credentials_are_scoped_to_explicit_routes_and_methods(self):
        self.assertTrue(mini_proof_route("POST", "/api/auth/mini/transactions"))
        self.assertTrue(mini_proof_route("POST", "/api/auth/mini/transactions/abc_123/poll"))
        self.assertFalse(mini_proof_route("POST", "/api/auth/mini/transactions/abc_123/approve"))
        self.assertFalse(mini_proof_route("GET", "/api/auth/mini/transactions"))
        self.assertTrue(mini_bearer_route("GET", "/api/users/me"))
        self.assertTrue(mini_bearer_route("POST", "/api/devices/0123456789abcdef01234567/veepoo/readings"))
        self.assertTrue(mini_bearer_route("GET", "/api/devices/0123456789abcdef01234567/data"))
        self.assertTrue(mini_bearer_route("GET", "/api/rehabilitation/publications/my-plans"))
        self.assertTrue(mini_bearer_route("POST", "/api/rehabilitation/plans/0123456789abcdef01234567/patient-feedback"))
        self.assertTrue(mini_bearer_route("POST", "/api/rehabilitation/plans/0123456789abcdef01234567/patient-feedback/media"))
        self.assertTrue(mini_bearer_route("GET", "/api/rehabilitation/plans/0123456789abcdef01234567/patient-feedback/media/0123456789abcdef0123456789abcdef"))
        self.assertTrue(mini_bearer_route("POST", "/api/rehabilitation/plans/0123456789abcdef01234567/patient-feedback/1123456789abcdef01234567/supplements"))
        self.assertTrue(mini_bearer_route("GET", "/api/rehabilitation/plans/0123456789abcdef01234567/training-cycles"))
        self.assertFalse(mini_bearer_route("POST", "/api/rehabilitation/plans/0123456789abcdef01234567/training-cycles/1123456789abcdef01234567/acceptance"))
        self.assertFalse(mini_bearer_route("POST", "/api/rehabilitation/plans/0123456789abcdef01234567/patient-feedback/not-an-id/supplements"))
        self.assertFalse(mini_bearer_route("DELETE", "/api/rehabilitation/plans/0123456789abcdef01234567/patient-feedback/media"))
        self.assertFalse(mini_bearer_route("GET", "/api/rehabilitation/plans/0123456789abcdef01234567/patient-feedback/media/not-an-id"))
        self.assertTrue(mini_bearer_route("POST", "/api/health-records/followups/0123456789abcdef01234567/review"))
        self.assertTrue(mini_bearer_route("POST", "/api/communications/conversations/0123456789abcdef01234567/messages"))
        self.assertFalse(mini_bearer_route("POST", "/api/rehabilitation/plans/0123456789abcdef01234567/approve"))
        self.assertFalse(mini_bearer_route("DELETE", "/api/communications/messages/0123456789abcdef01234567"))
        self.assertFalse(mini_bearer_route("DELETE", "/api/devices/0123456789abcdef01234567/unbind"))
        self.assertFalse(mini_bearer_route("POST", "/api/users/me"))

    def test_public_mini_urls_keep_configured_root_path(self):
        config = SimpleNamespace(public_base_url="https://care.test/medical")
        with patch("app.integrations.identity.router.oidc_settings", config):
            self.assertEqual(public_api_url("auth/mini/transactions/abc/approve"),
                             "https://care.test/medical/api/auth/mini/transactions/abc/approve")


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

    async def begin(self, mini_transaction_id=None):
        if mini_transaction_id:
            await self.db.oidc_mini_login_transactions.update_one(
                {"_id": digest(mini_transaction_id), "status": "pending"},
                {"$set": {"status": "oidc_started"}})
        target, browser = await self.service.start(mini_transaction_id=mini_transaction_id)
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
        actor_id = ObjectId()
        await self.db.users.insert_one(dict(_id=actor_id, name="Reviewed actor", email="reviewed@example.com",
            role=role, is_active=True, created_at=datetime.utcnow(), updated_at=datetime.utcnow()))
        await manage_binding(self.db, issuer=self.config.issuer, subject="opaque-stable-subject",
            actor_id=str(actor_id), reviewer="administrator", evidence_reference="review/789", apply=True, approved_role=role)
        sid, csrf, _ = await self.service.callback(*(await self.begin()))
        return sid, csrf, actor_id

    async def test_success_creates_identity_only_session_without_tokens(self):
        sid, csrf, expiry = await self.service.callback(*(await self.begin()))
        self.assertGreater(expiry, 0)
        self.assertGreater(expiry, 3500)
        stored = await self.db.oidc_application_sessions.find_one({"_id": digest(sid)})
        self.assertEqual(set(stored), {"_id", "issuer", "subject", "csrf_hash", "expires_at", "source_token_encrypted", "binding_revision"})
        self.assertNotIn("source-token-never-stored", repr(stored))
        self.assertNotIn(sid, repr(stored))
        result = await self.service.session(sid)
        self.assertEqual(result["clinical_permissions"], [])
        self.assertFalse(result["clinical_access"])
        self.assertIsNone(result["actor_id"])
        await self.service.logout(sid, csrf)
        self.assertFalse(self.source_active)
        self.assertIsNone(await self.service.session(sid))

    async def test_mini_handoff_requires_browser_and_mini_confirmation_and_is_single_use(self):
        _, _, actor_id = await self.bound_session()
        verifier = base64.urlsafe_b64encode(os.urandom(32)).rstrip(b"=").decode()
        challenge = self.service.mini_challenge(verifier)
        transaction_id = await self.service.create_mini_transaction(challenge)
        self.assertIsNone(await self.service.mini_transaction(transaction_id, "A" * 43))

        state, code, browser = await self.begin(transaction_id)
        callback_sid, _, _, linked_id = await self.service.callback(
            state, code, browser, include_transaction=True)
        self.assertEqual(linked_id, transaction_id)
        record, actor = await self.service.actor_for_session(callback_sid)
        self.assertEqual(str(actor["_id"]), str(actor_id))
        self.assertTrue(await self.service.set_mini_login_result(
            transaction_id, record["_id"], approved_binding=True))
        pending, status = await self.service.mini_transaction_status(transaction_id, verifier)
        self.assertEqual(status, "awaiting_confirmation")
        with self.assertRaises(OidcFailure):
            await self.service.exchange_mini_transaction(transaction_id, verifier)

        approved_actor = await self.service.approve_mini_transaction(transaction_id, callback_sid)
        self.assertEqual(str(approved_actor["_id"]), str(actor_id))
        token, expires_in, exchanged_actor = await self.service.exchange_mini_transaction(transaction_id, verifier)
        self.assertGreater(expires_in, 0)
        self.assertEqual(str(exchanged_actor["_id"]), str(actor_id))
        self.assertNotIn(token, repr(await self.db.oidc_mini_sessions.find_one({"_id": digest(token)})))
        with self.assertRaises(OidcFailure):
            await self.service.exchange_mini_transaction(transaction_id, verifier)
        mini_session, mini_actor = await self.service.actor_for_mini_session(token)
        self.assertIsNotNone(mini_session)
        self.assertEqual(str(mini_actor["_id"]), str(actor_id))

        self.source_active = False
        self.assertEqual(await self.service.actor_for_mini_session(token), (None, None))
        self.assertFalse(await self.service.revoke_mini_session(token))

    async def test_mini_handoff_requires_reviewed_binding_and_wrong_browser(self):
        verifier = base64.urlsafe_b64encode(os.urandom(32)).rstrip(b"=").decode()
        transaction_id = await self.service.create_mini_transaction(self.service.mini_challenge(verifier))
        state, code, browser = await self.begin(transaction_id)
        sid, _, _, linked_id = await self.service.callback(state, code, browser, include_transaction=True)
        record, actor = await self.service.actor_for_session(sid)
        self.assertIsNone(actor)
        self.assertEqual(linked_id, transaction_id)
        self.assertTrue(await self.service.set_mini_login_result(transaction_id, record["_id"], approved_binding=False))
        transaction, status = await self.service.mini_transaction_status(transaction_id, verifier)
        self.assertEqual(status, "denied")
        with self.assertRaises(OidcFailure):
            await self.service.exchange_mini_transaction(transaction_id, verifier)

    async def test_mini_transaction_expiry_and_verifier_possession(self):
        verifier = base64.urlsafe_b64encode(os.urandom(32)).rstrip(b"=").decode()
        transaction_id = await self.service.create_mini_transaction(self.service.mini_challenge(verifier))
        transaction = await self.db.oidc_mini_login_transactions.find_one({"_id": digest(transaction_id)})
        await self.db.oidc_mini_login_transactions.update_one(
            {"_id": transaction["_id"]}, {"$set": {"expires_at": datetime.utcnow() - timedelta(seconds=1)}})
        stored, status = await self.service.mini_transaction_status(transaction_id, verifier)
        self.assertEqual(status, "expired")
        self.assertIsNone(await self.service.mini_transaction(transaction_id, "Z" * 43))

    async def test_state_cookie_and_transaction_expiry_are_required(self):
        state, code, browser = await self.begin()
        for args in (("bad-state", code, browser), (state, code, "wrong-browser"), (state, code, None)):
            with self.assertRaises(OidcFailure):
                await self.service.callback(*args)
        self.assertEqual(self.token_calls, 0)
        await self.db.oidc_login_transactions.update_one({"_id": digest(state)}, {"$set": {"expires_at": datetime.utcnow() - timedelta(seconds=1)}})
        with self.assertRaises(OidcFailure):
            await self.service.callback(state, code, browser)

    async def test_operations_lifetime_bounds_server_session_and_cookie(self):
        await self.db.system_settings.insert_one({"_id": "system", "session_timeout_minutes": 15})
        before = datetime.utcnow()
        state, code, secret = await self.begin()
        with self.unified_application() as app:
            async with httpx.AsyncClient(app=app, base_url="https://care.test",
                    cookies={"__Host-rehab_oidc": secret}) as browser:
                response = await browser.get("/api/auth/oidc/callback", params={"state": state, "code": code})
                self.assertEqual(response.status_code, 303)
                sid = browser.cookies.get("__Host-rehab_session")
                self.assertIsNotNone(sid)
                stored = await self.db.oidc_application_sessions.find_one({"_id": digest(sid)})
                server_seconds = (stored["expires_at"] - before).total_seconds()
                self.assertGreater(server_seconds, 890)
                self.assertLess(server_seconds, 905)
                from http.cookies import SimpleCookie
                issued = SimpleCookie()
                for value in response.headers.get_list("set-cookie"):
                    issued.load(value)
                cookie_seconds = int(issued["__Host-rehab_session"]["max-age"])
                self.assertLessEqual(cookie_seconds, 900)
                self.assertLess(abs(server_seconds - cookie_seconds), 5)

    async def test_operations_lifetime_does_not_extend_shorter_oidc_limit(self):
        await self.db.system_settings.insert_one({"_id": "system", "session_timeout_minutes": 15})
        self.config.session_seconds = 60
        before = datetime.utcnow()
        sid, _, seconds = await self.service.callback(*(await self.begin()))
        stored = await self.db.oidc_application_sessions.find_one({"_id": digest(sid)})
        self.assertLessEqual(seconds, 60)
        self.assertLess((stored["expires_at"] - before).total_seconds(), 65)

    async def test_unavailable_operations_policy_creates_no_session_or_cookie(self):
        state, code, secret = await self.begin()
        with self.unified_application() as app, patch(
                "app.operations.runtime.session_timeout_minutes", new=AsyncMock(side_effect=RuntimeError("policy unavailable"))):
            async with httpx.AsyncClient(app=app, base_url="https://care.test",
                    cookies={"__Host-rehab_oidc": secret}) as browser:
                response = await browser.get("/api/auth/oidc/callback", params={"state": state, "code": code})
                self.assertIn("OIDC_VALIDATION_FAILED", response.headers["location"])
                self.assertIsNone(browser.cookies.get("__Host-rehab_session"))
                self.assertIsNone(browser.cookies.get("__Host-rehab_csrf"))
        self.assertEqual(await self.db.oidc_application_sessions.count_documents({}), 0)

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

    async def test_fill_delegation_is_server_only_and_actor_bound(self):
        sid, _, actor_id = await self.bound_session()
        actor = SimpleNamespace(id=str(actor_id), role='doctor')
        delegation = await self.service.fill_delegation(sid, actor)
        self.assertEqual(delegation.token, 'source-token-never-stored')
        self.assertNotIn(delegation.token, repr(delegation))
        with self.assertRaises(OidcFailure):
            await self.service.fill_delegation(sid, SimpleNamespace(id=str(ObjectId()), role='doctor'))
        self.source_active = False
        with self.assertRaises(OidcFailure):
            await delegation.revalidate()

    async def test_fill_delegation_locks_require_live_session_binding_and_actor(self):
        sid, _, actor_id = await self.bound_session()
        delegation = await self.service.fill_delegation(sid, SimpleNamespace(id=str(actor_id), role='doctor'))
        # None uses real Mongo conditional writes without requiring a transaction
        # here; transaction races are exercised in fill-task tests.
        await delegation.lock(self.db, None)
        await self.db.oidc_application_sessions.delete_one({'_id': digest(sid)})
        with self.assertRaises(OidcFailure):
            await delegation.lock(self.db, None)

    async def test_mini_fill_delegation_reuses_live_reviewed_source_session(self):
        _, _, actor_id = await self.bound_session()
        actor = SimpleNamespace(id=str(actor_id), role="doctor")
        verifier = base64.urlsafe_b64encode(os.urandom(32)).rstrip(b"=").decode()
        transaction_id = await self.service.create_mini_transaction(self.service.mini_challenge(verifier))
        state, code, browser = await self.begin(transaction_id)
        mini_sid, _, _, _ = await self.service.callback(state, code, browser, include_transaction=True)
        record, mini_actor = await self.service.actor_for_session(mini_sid)
        self.assertEqual(str(mini_actor["_id"]), str(actor_id))
        self.assertTrue(await self.service.set_mini_login_result(transaction_id, record["_id"], approved_binding=True))
        await self.service.approve_mini_transaction(transaction_id, mini_sid)
        token, _, _ = await self.service.exchange_mini_transaction(transaction_id, verifier)

        delegation = await self.service.fill_delegation_for_mini_session(token, actor)
        self.assertEqual(delegation.session_hash, digest(mini_sid))
        self.assertEqual(delegation.token, "source-token-never-stored")
        self.assertNotIn(delegation.token, repr(delegation))
        await delegation.revalidate()
        await delegation.lock(self.db, None)
        self.assertEqual((await self.db.oidc_mini_sessions.find_one({"_id": digest(token)}))["fill_use_revision"], 1)

        from app.integrations.forms.mini_bridge import issue_launch_bridge, consume_launch_bridge
        patient_id = str(ObjectId())
        await self.db.users.update_one({"_id": actor_id}, {"$set": {"is_active": True}})
        await self.db.users.insert_one({"_id": ObjectId(patient_id), "role": "patient",
                                        "is_active": True, "practitioners": [str(actor_id)]})
        link_id, binding_id = ObjectId(), ObjectId()
        reference = {"project_id": 1, "center_id": 2, "subject_id": 3,
                     "source": {"system": "questionnaire", "environment": "test"}}
        version_ref = {"form_id": 4, "family_id": 4, "version": 1,
                       "version_state": "current", "definition_sha256": "a" * 64}
        review = {"verified_by": "test-reviewer", "verified_at": datetime.utcnow(),
                  "evidence_reference": "review/test", "source_origin": "https://identity.test"}
        await self.db.external_patient_links.insert_one({"_id": link_id, "local_patient_id": patient_id,
            "status": "verified", "reference": reference, "references": [reference], **review})
        await self.db.external_form_bindings.insert_one({"_id": binding_id, "status": "active",
            "project_id": 1, "form_id": 4, "version": 1, "version_ref": version_ref,
            "purpose": "followup", "source": reference["source"], **review})
        task_id = ObjectId()
        task = {
            "_id": task_id, "patient_id": patient_id, "status": "session_created", "allowed_origin": "https://care.example",
            "operator": {"user_id": str(actor_id)}, "session": {"session_uuid": "session_123"},
            "remote_refs": {"project_id": 1, "center_id": 2, "subject_id": 3, "questionnaire_id": 4},
            "reviewed_context": {"patient_link_id": str(link_id), "form_binding_id": str(binding_id),
                                 "reference": reference, "version_ref": version_ref, "purpose": "followup"},
            "identity_context": {"issuer": delegation.record["issuer"], "subject": delegation.record["subject"],
                                 "session_hash": delegation.record["_id"],
                                 "binding_revision": delegation.record["binding_revision"]},
        }
        await self.db.integration_fill_tasks.insert_one(task)
        launch = {
            "taskId": str(task_id), "mode": "launch", "action": "https://identity.test/integration/embed/session_123",
            "sessionUuid": "session_123", "expiresAt": (datetime.now(timezone.utc) + timedelta(minutes=2)).isoformat(),
            "allowedOrigin": "https://care.example", "token": "one-use-form-token",
        }
        ticket = await issue_launch_bridge(self.db, launch, task, delegation, self.config)
        self.assertNotIn("one-use-form-token", ticket)
        self.assertEqual((await consume_launch_bridge(self.db, ticket, "wrong-browser-cookie", self.service, self.config)).status_code, 403)
        response = await consume_launch_bridge(self.db, ticket, mini_sid, self.service, self.config)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'method="post"', response.body)
        self.assertIn(b"one-use-form-token", response.body)
        self.assertEqual((await consume_launch_bridge(self.db, ticket, mini_sid, self.service, self.config)).status_code, 410)

        revoked_assignment_ticket = await issue_launch_bridge(self.db, launch, task, delegation, self.config)
        await self.db.users.update_one({"_id": ObjectId(patient_id)}, {"$set": {"practitioners": []}})
        denied_assignment = await consume_launch_bridge(self.db, revoked_assignment_ticket, mini_sid, self.service, self.config)
        self.assertEqual(denied_assignment.status_code, 403)
        self.assertNotIn(b"one-use-form-token", denied_assignment.body)

        await self.db.users.update_one({"_id": ObjectId(patient_id)}, {"$set": {"practitioners": [str(actor_id)]}})
        revoked_binding_ticket = await issue_launch_bridge(self.db, launch, task, delegation, self.config)
        await self.db.external_form_bindings.update_one({"_id": binding_id}, {"$set": {"status": "revoked"}})
        denied_binding = await consume_launch_bridge(self.db, revoked_binding_ticket, mini_sid, self.service, self.config)
        self.assertEqual(denied_binding.status_code, 409)
        self.assertNotIn(b"one-use-form-token", denied_binding.body)

        with self.assertRaises(OidcFailure):
            await self.service.fill_delegation_for_mini_session(token, SimpleNamespace(id=str(ObjectId()), role="doctor"))
        await self.service.revoke_mini_session(token)
        with self.assertRaises(OidcFailure):
            await delegation.revalidate()

    async def test_forms_router_selects_mini_delegation_only_for_authenticated_mini_transport(self):
        from app.integrations.forms.router import current_fill_delegation
        self.config.authentication_mode = "oidc"
        actor = SimpleNamespace(id=str(ObjectId()), role="doctor")
        delegation = object()
        client = SimpleNamespace(
            fill_delegation_for_mini_session=AsyncMock(return_value=delegation),
            fill_delegation=AsyncMock(return_value=delegation),
        )
        with patch("app.integrations.identity.config.oidc_settings", self.config), \
                patch("app.integrations.identity.access.oidc_settings", self.config), \
                patch("app.integrations.identity.service.OidcClient", return_value=client):
            mini_request = SimpleNamespace(
                state=SimpleNamespace(identity_transport="mini_bearer"),
                headers={"authorization": "Bearer mini-session-token"}, cookies={},
            )
            result = await current_fill_delegation(mini_request, self.db, actor)
            self.assertIs(result, delegation)
            client.fill_delegation_for_mini_session.assert_awaited_once_with("mini-session-token", actor)
            client.fill_delegation.assert_not_awaited()

            browser_request = SimpleNamespace(
                state=SimpleNamespace(identity_transport=None), headers={},
                cookies={"__Host-rehab_session": "browser-session-cookie"},
            )
            result = await current_fill_delegation(browser_request, self.db, actor)
            self.assertIs(result, delegation)
            client.fill_delegation.assert_awaited_once_with("browser-session-cookie", actor)

    async def test_binding_is_explicit_reviewed_and_never_inherits_roles(self):
        pending_sid, _, _ = await self.service.callback(*(await self.begin()))
        actor_id = ObjectId()
        await self.db.users.insert_one({"_id": actor_id, "is_active": True, "role": "admin", "permissions": ["*"]})
        binding = dict(_id=digest(self.config.issuer + "\0opaque-stable-subject"), issuer=self.config.issuer,
                       subject="opaque-stable-subject", actor_id=str(actor_id), enabled=True)
        await self.db.oidc_principal_bindings.insert_one(binding)
        self.assertIsNone(await self.service.session(pending_sid))
        sid, _, _ = await self.service.callback(*(await self.begin()))
        self.assertIsNone(await self.service.session(sid))
        await manage_binding(self.db, issuer=self.config.issuer, subject="opaque-stable-subject",
            actor_id=str(actor_id), reviewer="reviewer", evidence_reference="review/123",
            approved_role="admin", action="review-role", apply=True)
        sid, _, _ = await self.service.callback(*(await self.begin()))
        result = await self.service.session(sid)
        self.assertEqual(result["actor_id"], str(actor_id))
        self.assertEqual(result["clinical_permissions"], [])
        self.assertNotIn("role", result)
        await self.db.users.update_one({"_id": actor_id}, {"$set": {"is_active": False}})
        self.assertIsNone(await self.service.session(sid))

    async def test_role_review_invalidates_unobserved_old_sessions(self):
        sid, _, actor_id = await self.bound_session()
        original = await self.db.oidc_principal_bindings.find_one({})
        await self.db.users.update_one({"_id": actor_id}, {"$set": {"role": "admin"}})
        await manage_binding(self.db, issuer=self.config.issuer, subject="opaque-stable-subject",
            actor_id=str(actor_id), reviewer="reviewer", evidence_reference="review/new-role",
            approved_role="admin", action="review-role", apply=True)
        updated = await self.db.oidc_principal_bindings.find_one({})
        self.assertNotEqual(original["authorization_revision"], updated["authorization_revision"])
        self.assertIsNone(await self.service.session(sid))
        fresh_sid, _, _ = await self.service.callback(*(await self.begin()))
        self.assertEqual((await self.service.session(fresh_sid))["actor_id"], str(actor_id))

    async def test_historical_session_and_first_binding_require_reauthentication(self):
        sid, _, actor_id = await self.bound_session()
        await self.db.oidc_application_sessions.update_one({"_id": digest(sid)}, {"$unset": {"binding_revision": ""}})
        self.assertIsNone(await self.service.session(sid))
        await self.db.oidc_principal_bindings.delete_many({})
        pending_sid, _, _ = await self.service.callback(*(await self.begin()))
        self.assertEqual((await self.service.session(pending_sid))["identity_state"], "pending_binding")
        await manage_binding(self.db, issuer=self.config.issuer, subject="opaque-stable-subject",
            actor_id=str(actor_id), reviewer="reviewer", evidence_reference="review/first",
            approved_role="doctor", apply=True)
        self.assertIsNone(await self.service.session(pending_sid))

    async def test_disable_and_concurrent_review_reject_old_authorization(self):
        sid, _, actor_id = await self.bound_session()
        collection = self.db.oidc_principal_bindings
        original_update = collection.update_one
        async def concurrent_update(_collection, query, update, *args, **kwargs):
            await original_update({"_id": query["_id"]}, {"$set": {"authorization_revision": "f" * 64}})
            return await original_update(query, update, *args, **kwargs)
        with patch.object(type(collection), "update_one", new=concurrent_update):
            with self.assertRaisesRegex(ValueError, "changed concurrently"):
                await manage_binding(self.db, issuer=self.config.issuer, subject="opaque-stable-subject",
                    actor_id=str(actor_id), reviewer="reviewer", evidence_reference="review/concurrent",
                    approved_role="doctor", action="review-role", apply=True)
        self.assertIsNone(await self.service.session(sid))
        sid, _, _ = await self.service.callback(*(await self.begin()))
        await manage_binding(self.db, issuer=self.config.issuer, subject="opaque-stable-subject",
            actor_id=str(actor_id), reviewer="reviewer", evidence_reference="review/disable",
            action="disable", apply=True)
        self.assertIsNone(await self.service.session(sid))

    async def test_review_during_actor_lookup_rejects_the_old_session(self):
        sid, _, actor_id = await self.bound_session()
        collection_type = type(self.db.users)
        original_find = collection_type.find_one
        reviewed = False
        async def find_with_review(collection, query, *args, **kwargs):
            nonlocal reviewed
            result = await original_find(collection, query, *args, **kwargs)
            if collection.name == "users" and not reviewed:
                reviewed = True
                await manage_binding(self.db, issuer=self.config.issuer, subject="opaque-stable-subject",
                    actor_id=str(actor_id), reviewer="reviewer", evidence_reference="review/during-request",
                    approved_role="doctor", action="review-role", apply=True)
            return result
        with patch.object(collection_type, "find_one", new=find_with_review):
            self.assertIsNone(await self.service.session(sid))
        self.assertTrue(reviewed)

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

    async def test_mini_handoff_http_chain_root_path_csrf_and_scope(self):
        _, _, patient_id = await self.bound_session(role="patient")
        from app.main import app
        from app.api.routers.device_router import get_device_ingestion_service
        from app.services.device_ingestion_service import DeviceIngestionService

        class PrefixProxy:
            """Model the trusted proxy stripping /medical into ASGI root_path."""
            def __init__(self, wrapped):
                self.wrapped = wrapped
            async def __call__(self, scope, receive, send):
                if scope["type"] == "http" and scope["path"].startswith("/medical/"):
                    scope = dict(scope)
                    scope["root_path"] = "/medical"
                    scope["path"] = scope["path"][len("/medical"):]
                await self.wrapped(scope, receive, send)

        with self.unified_application():
            app.dependency_overrides[get_device_ingestion_service] = lambda: DeviceIngestionService(db=self.db)
            transport = httpx.ASGITransport(app=PrefixProxy(app))
            async with httpx.AsyncClient(transport=transport, base_url="https://care.test") as mini, \
                    httpx.AsyncClient(transport=transport, base_url="https://care.test") as browser:
                verifier = base64.urlsafe_b64encode(os.urandom(32)).rstrip(b"=").decode()
                challenge = self.service.mini_challenge(verifier)
                started = await mini.post("/medical/api/auth/mini/transactions",
                    json={"code_challenge": challenge}, headers={"origin": "https://servicewechat.com"})
                self.assertEqual(started.status_code, 200, started.text)
                handoff = started.json()
                self.assertTrue(handoff["webview_url"].startswith("https://care.test/medical/api/"))
                tx_id = handoff["transaction_id"]

                authorize = await browser.get(handoff["webview_url"])
                self.assertEqual(authorize.status_code, 303, authorize.text)
                authorization_url = authorize.headers["location"]
                # The ID is a public locator, but another browser cannot retry
                # without possession of the original OIDC transaction cookie.
                other_browser_retry = await mini.get(handoff["webview_url"])
                self.assertEqual(other_browser_retry.status_code, 410, other_browser_retry.text)
                same_browser_retry = await browser.get(handoff["webview_url"])
                self.assertEqual(same_browser_retry.status_code, 303, same_browser_retry.text)
                self.assertEqual(same_browser_retry.headers["location"], authorization_url)
                query = parse_qs(urlsplit(authorize.headers["location"]).query)
                oidc_transaction = await self.db.oidc_login_transactions.find_one({
                    "_id": digest(query["state"][0])})
                self.assertIn("mini_authorization_encrypted", oidc_transaction)
                self.assertNotIn(authorization_url, repr(oidc_transaction))
                self.assertNotIn(query["state"][0], repr(oidc_transaction))
                self.assertNotIn(browser.cookies.get("__Host-rehab_oidc"), repr(oidc_transaction))
                code = uuid4().hex
                self.codes[code] = {"nonce": query["nonce"][0], "challenge": query["code_challenge"][0]}
                callback = await browser.get("/medical/api/auth/oidc/callback", params={
                    "state": query["state"][0], "code": code})
                self.assertEqual(callback.status_code, 303, callback.text)
                consumed_retry = await browser.get(handoff["webview_url"])
                self.assertEqual(consumed_retry.status_code, 410, consumed_retry.text)
                confirm_url = callback.headers["location"]
                self.assertIn("/medical/api/auth/mini/transactions/" + tx_id + "/confirm", confirm_url)
                confirmation = await browser.get(confirm_url)
                self.assertEqual(confirmation.status_code, 200, confirmation.text)
                self.assertIn("Reviewed actor", confirmation.text)
                self.assertIn("/medical/api/auth/mini/transactions/", confirmation.text)

                csrf = browser.cookies.get("__Host-rehab_csrf")
                approved = await browser.post("/medical/api/auth/mini/transactions/" + tx_id + "/approve",
                    headers={"origin": "https://care.test", "x-csrf-token": csrf})
                self.assertEqual(approved.status_code, 200, approved.text)
                wrong_proof = await mini.post(f"/medical/api/auth/mini/transactions/{tx_id}/poll",
                    json={"verifier": "A" * 43}, headers={"origin": "https://servicewechat.com"})
                self.assertEqual(wrong_proof.status_code, 401, wrong_proof.text)
                poll = await mini.post(f"/medical/api/auth/mini/transactions/{tx_id}/poll",
                    json={"verifier": verifier}, headers={"origin": "https://servicewechat.com"})
                self.assertEqual(poll.status_code, 200, poll.text)
                self.assertEqual(poll.json()["status"], "ready")
                self.assertEqual(poll.json()["user"]["display_name"], "Reviewed actor")

                exchange = await mini.post(f"/medical/api/auth/mini/transactions/{tx_id}/exchange",
                    json={"verifier": verifier}, headers={"origin": "https://servicewechat.com"})
                self.assertEqual(exchange.status_code, 200, exchange.text)
                token = exchange.json()["access_token"]
                self.assertNotIn(token, handoff["webview_url"])
                self.assertNotIn(token, confirm_url)
                replay = await mini.post(f"/medical/api/auth/mini/transactions/{tx_id}/exchange",
                    json={"verifier": verifier}, headers={"origin": "https://servicewechat.com"})
                self.assertEqual(replay.status_code, 401, replay.text)

                current = await mini.get("/medical/api/users/me", headers={"authorization": f"Bearer {token}"})
                self.assertEqual(current.status_code, 200, current.text)
                self.assertEqual(current.json()["id"], str(patient_id))

                hardware_id = "F300:ONEID:AA:BB:CC:DD"
                bound = await mini.post("/medical/api/devices/bind", headers={
                    "authorization": f"Bearer {token}", "origin": "https://servicewechat.com"}, json={
                    "device_type": "手环", "name": "F300 实机", "manufacturer": "Veepoo",
                    "model": "F300", "connection_type": "bluetooth",
                    "settings": {"claimed_hardware_id": hardware_id},
                })
                self.assertEqual(bound.status_code, 200, bound.text)
                device_id = bound.json()["id"]
                uploaded = await mini.post(f"/medical/api/devices/{device_id}/veepoo/readings", headers={
                    "authorization": f"Bearer {token}", "origin": "https://servicewechat.com"}, json={
                    "hardware_id": hardware_id,
                    "readings": [{"data_type": "heart_rate", "value": 82, "unit": "bpm",
                        "measured_at": datetime.now(timezone.utc).isoformat(), "sdk_type": 51,
                        "record_key": "oneid-mini-http-e2e-1", "raw_payload": {"heartRate": 82}}],
                })
                self.assertEqual(uploaded.status_code, 200, uploaded.text)
                self.assertEqual(uploaded.json()["accepted_count"], 1)
                self.assertEqual(uploaded.json()["clinical_facts_created"], 1)

                forbidden = await mini.get("/medical/api/auth/access-applications/mine",
                    headers={"authorization": f"Bearer {token}"})
                self.assertEqual(forbidden.status_code, 401, forbidden.text)

                browser_csrf_reject = await browser.post("/medical/api/auth/logout",
                    headers={"origin": "https://attacker.test"})
                self.assertEqual(browser_csrf_reject.status_code, 403, browser_csrf_reject.text)
