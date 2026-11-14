"""OIDC code + S256 client with persistent, atomically consumed login transactions.

In explicit unified mode, reviewed bindings retain the application's existing
role and object scope. Source account state is checked online for each request;
identity-only trials in legacy mode cannot authenticate clinical dependencies.
"""
import hashlib
import math
import secrets
import time
from datetime import datetime, timedelta
from urllib.parse import urlsplit

import httpx
from cryptography.fernet import Fernet
from authlib.integrations.httpx_client import AsyncOAuth2Client
from authlib.oidc.core import CodeIDToken
from bson import ObjectId
from joserfc import jwt
from joserfc.jwk import KeySet
from joserfc.jws import JWSRegistry


def digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class OidcFailure(Exception):
    """Safe outward error. Never expose provider messages or credential material."""


class OidcUnavailable(Exception):
    """Online source status could not be verified; protected operations fail closed."""


async def ensure_identity_indexes(db):
    # Unlike a best-effort business index, these are an enabled auth prerequisite.
    for name in ("oidc_login_transactions", "oidc_application_sessions"):
        await db[name].create_index("expires_at", expireAfterSeconds=0, name="expires_at_ttl")
    await db.oidc_principal_bindings.create_index(
        [("issuer", 1), ("actor_id", 1)], unique=True, name="issuer_actor_unique")


class OidcClient:
    def __init__(self, db, settings, *, transport=None):
        self.db, self.settings, self.transport = db, settings, transport

    async def metadata(self):
        async with httpx.AsyncClient(transport=self.transport, follow_redirects=False, timeout=10) as client:
            result = await client.get(self.settings.issuer + "/.well-known/openid-configuration")
            result.raise_for_status()
            data = result.json()
        if data.get("issuer") != self.settings.issuer:
            raise OidcFailure()
        issuer_origin = urlsplit(self.settings.issuer)
        for key in ("authorization_endpoint", "token_endpoint", "jwks_uri",
                    "introspection_endpoint", "revocation_endpoint"):
            parsed = urlsplit(data.get(key, ""))
            if (parsed.scheme != "https" or parsed.netloc != issuer_origin.netloc
                    or parsed.username or parsed.password or parsed.query or parsed.fragment):
                raise OidcFailure()
        for key, expected in (("response_types_supported", "code"),
                              ("code_challenge_methods_supported", "S256"),
                              ("id_token_signing_alg_values_supported", "RS256"),
                              ("token_endpoint_auth_methods_supported", "client_secret_basic")):
            if expected not in data.get(key, []):
                raise OidcFailure()
        if data["introspection_endpoint"] != self.settings.issuer + "/oidc/introspect":
            raise OidcFailure()
        if data["revocation_endpoint"] != self.settings.issuer + "/oidc/revoke":
            raise OidcFailure()
        return data

    def oauth(self, **kwargs):
        return AsyncOAuth2Client(
            self.settings.client_id, self.settings.client_secret.get_secret_value(),
            token_endpoint_auth_method="client_secret_basic", scope="openid",
            redirect_uri=self.settings.callback_uri, code_challenge_method="S256",
            transport=self.transport, follow_redirects=False, timeout=10, **kwargs)

    async def start(self, old_browser_secret=None):
        metadata = await self.metadata()
        browser_secret = secrets.token_urlsafe(32)
        state, nonce, verifier = (secrets.token_urlsafe(48) for _ in range(3))
        async with self.oauth() as client:
            url, _ = client.create_authorization_url(metadata["authorization_endpoint"],
                state=state, nonce=nonce, code_verifier=verifier)
        if old_browser_secret:
            await self.db.oidc_login_transactions.delete_many({"browser_hash": digest(old_browser_secret)})
        await self.db.oidc_login_transactions.insert_one({
            "_id": digest(state), "browser_hash": digest(browser_secret), "nonce": nonce,
            "verifier": verifier, "expires_at": datetime.utcnow() + timedelta(seconds=300)})
        return url, browser_secret

    async def callback(self, state, code, browser_secret):
        if (not state or not code or not browser_secret
                or max(map(len, (state, code, browser_secret))) > 4096):
            raise OidcFailure()
        # Destructive atomic read gives exactly one exchange attempt across workers.
        transaction = await self.db.oidc_login_transactions.find_one_and_delete({
            "_id": digest(state), "browser_hash": digest(browser_secret),
            "expires_at": {"$gt": datetime.utcnow()}})
        if transaction is None:
            raise OidcFailure()
        metadata = await self.metadata()
        async with self.oauth() as client:
            token = await client.fetch_token(metadata["token_endpoint"], code=code,
                                            code_verifier=transaction["verifier"])
        if (not isinstance(token.get("id_token"), str) or len(token["id_token"]) > 65536
                or not isinstance(token.get("access_token"), str) or not 1 <= len(token["access_token"]) <= 4096):
            raise OidcFailure()
        async with httpx.AsyncClient(transport=self.transport, follow_redirects=False, timeout=10) as client:
            response = await client.get(metadata["jwks_uri"])
            response.raise_for_status()
            keys = response.json()
        if len(keys.get("keys", [])) > 20:
            raise OidcFailure()
        decoded = jwt.decode(token["id_token"], KeySet.import_key_set(keys),
                             registry=JWSRegistry(algorithms=["RS256"]))
        claims = CodeIDToken(decoded.claims, decoded.header,
            {"iss": {"essential": True, "value": self.settings.issuer},
             "aud": {"essential": True, "value": self.settings.client_id}},
            {"client_id": self.settings.client_id, "nonce": transaction["nonce"],
             "access_token": token.get("access_token")})
        claims.validate(leeway=30)
        numeric_dates = (claims["iat"], claims["exp"])
        if any(isinstance(value, bool) or not isinstance(value, (int, float))
               or not math.isfinite(value) for value in numeric_dates):
            raise OidcFailure()
        if (not isinstance(claims["sub"], str) or not 1 <= len(claims["sub"]) <= 255
                or claims["iat"] > time.time() + 30):
            raise OidcFailure()
        sid, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        source_lifetime = token.get("expires_in")
        if (isinstance(source_lifetime, bool) or not isinstance(source_lifetime, (int, float))
                or not math.isfinite(source_lifetime) or source_lifetime <= 0):
            raise OidcFailure()
        # ID-token expiry bounds the initial assertion, not a session that is
        # independently checked against the source on every protected request.
        expiry = time.time() + min(source_lifetime, self.settings.session_seconds)
        if expiry <= time.time():
            raise OidcFailure()
        await self.db.oidc_application_sessions.insert_one({
            "_id": digest(sid), "issuer": claims["iss"], "subject": claims["sub"],
            "csrf_hash": digest(csrf), "expires_at": datetime.utcfromtimestamp(expiry),
            "source_token_encrypted": Fernet(self.settings.session_encryption_key.get_secret_value().encode("ascii")).encrypt(token["access_token"].encode()).decode("ascii")})
        # ID tokens are discarded; delegated access token is encrypted for live status checks.
        return sid, csrf, max(0, int(expiry - time.time()))

    async def load_session(self, sid, *, verify_source=True):
        if not sid or len(sid) > 256:
            return None
        record = await self.db.oidc_application_sessions.find_one({
            "_id": digest(sid), "issuer": self.settings.issuer,
            "expires_at": {"$gt": datetime.utcnow()}})
        if record is None:
            return None
        if verify_source:
            try:
                source_token = Fernet(self.settings.session_encryption_key.get_secret_value().encode("ascii")).decrypt(
                    record["source_token_encrypted"].encode("ascii")).decode("utf-8")
                # Fixed issuer-relative status endpoint: no untrusted URL is stored in sessions.
                async with httpx.AsyncClient(transport=self.transport, follow_redirects=False, timeout=5) as client:
                    result = await client.post(self.settings.issuer + "/oidc/introspect",
                        auth=httpx.BasicAuth(self.settings.client_id, self.settings.client_secret.get_secret_value()),
                        data={"token": source_token, "token_type_hint": "access_token"})
                    result.raise_for_status()
                    state = result.json()
            except Exception:
                raise OidcUnavailable() from None
            if (state.get("active") is not True or state.get("sub") != record["subject"]
                    or state.get("iss") != self.settings.issuer or state.get("client_id") != self.settings.client_id
                    or isinstance(state.get("exp"), bool) or not isinstance(state.get("exp"), (int, float))
                    or not math.isfinite(state["exp"]) or state["exp"] <= time.time()):
                await self.db.oidc_application_sessions.delete_one({"_id": record["_id"]})
                return None
        return record

    async def actor_for_session(self, sid):
        record = await self.load_session(sid)
        if record is None:
            return None, None
        # Review metadata is mandatory. Matching names/emails never create mappings.
        binding = await self.db.oidc_principal_bindings.find_one({
            "_id": digest(record["issuer"] + "\0" + record["subject"]),
            "issuer": record["issuer"], "subject": record["subject"]})
        actor = None
        if (binding and binding.get("enabled") is True
                and isinstance(binding.get("verified_by"), str) and binding["verified_by"]
                and isinstance(binding.get("verified_at"), datetime)
                and isinstance(binding.get("evidence_reference"), str) and binding["evidence_reference"]
                and ObjectId.is_valid(binding.get("actor_id", ""))):
            actor = await self.db.users.find_one({"_id": ObjectId(binding["actor_id"]), "is_active": True})
            if actor and actor.get("role") != binding.get("approved_role"):
                actor = None
        if binding and (binding.get("enabled") is not True or (
                isinstance(binding.get("approved_role"), str) and actor is None)):
            # A known authorization removal/change invalidates this exact session;
            # later reactivation/review must not revive its old cookie.
            await self.db.oidc_application_sessions.delete_one({"_id": record["_id"]})
            return None, None
        return record, actor

    async def session(self, sid):
        record, actor = await self.actor_for_session(sid)
        if record is None:
            return None
        actor_id = str(actor["_id"]) if actor else None
        return {"authenticated": True, "issuer": record["issuer"], "subject": record["subject"],
                "actor_id": actor_id, "identity_state": "bound" if actor_id else "pending_binding",
                "clinical_permissions": [],
                "clinical_access": bool(actor and self.settings.authentication_mode == "oidc"),
                "expires_at": record["expires_at"].isoformat() + "Z"}

    async def verify_csrf(self, sid, csrf):
        if not sid or not csrf or max(len(sid), len(csrf)) > 256:
            return False
        return bool(await self.db.oidc_application_sessions.find_one({
            "_id": digest(sid), "csrf_hash": digest(csrf),
            "expires_at": {"$gt": datetime.utcnow()}}))

    async def logout(self, sid, csrf):
        if not sid or not csrf or max(len(sid), len(csrf)) > 256:
            raise OidcFailure()
        record = await self.db.oidc_application_sessions.find_one({
            "_id": digest(sid), "csrf_hash": digest(csrf)})
        if record is None:
            raise OidcFailure()
        try:
            source_token = Fernet(self.settings.session_encryption_key.get_secret_value().encode("ascii")).decrypt(
                record["source_token_encrypted"].encode("ascii")).decode("utf-8")
            async with httpx.AsyncClient(transport=self.transport, follow_redirects=False, timeout=10) as client:
                result = await client.post(
                    self.settings.issuer + "/oidc/revoke",
                    auth=httpx.BasicAuth(self.settings.client_id, self.settings.client_secret.get_secret_value()),
                    data={"token": source_token, "token_type_hint": "access_token"})
        except httpx.HTTPError:
            raise OidcUnavailable() from None
        if result.status_code != 200:
            raise OidcUnavailable()
        deleted = await self.db.oidc_application_sessions.delete_one({
            "_id": digest(sid), "csrf_hash": digest(csrf)})
        if deleted.deleted_count != 1:
            raise OidcFailure()
