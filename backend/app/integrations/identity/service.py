"""OIDC code + S256 client with persistent, atomically consumed login transactions.

In explicit unified mode, reviewed bindings retain the application's existing
role and object scope. Source account state is checked online for each request;
identity-only trials in legacy mode cannot authenticate clinical dependencies.
"""
from dataclasses import dataclass, field
import hashlib
import base64
import json
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


def binding_revision(binding):
    """Only explicitly versioned reviews can authorize a newly authenticated session."""
    value = binding.get("authorization_revision") if binding else None
    return value if isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value) else None


@dataclass(frozen=True, repr=False)
class FillDelegation:
    client: object = field(repr=False)
    sid: str = field(repr=False)
    token: str = field(repr=False)
    record: dict = field(repr=False)
    actor_id: str
    role: str
    session_hash: str | None = field(default=None, repr=False)
    mini_session_id: str | None = field(default=None, repr=False)

    async def revalidate(self):
        if self.session_hash:
            record, actor = await self.client.actor_for_session_hash(self.session_hash)
        else:
            record, actor = await self.client.actor_for_session(self.sid)
        if (record is None or actor is None or str(actor['_id']) != self.actor_id
                or actor['role'] != self.role
                or record.get('binding_revision') != self.record.get('binding_revision')):
            raise OidcFailure()
        if self.mini_session_id:
            mini = await self.client.db.oidc_mini_sessions.find_one({
                "_id": self.mini_session_id, "source_session_id": self.session_hash,
                "actor_id": self.actor_id, "expires_at": {"$gt": datetime.utcnow()},
            })
            if mini is None:
                raise OidcFailure()

    async def lock(self, db, session):
        binding_id = digest(self.record['issuer'] + "\0" + self.record['subject'])
        checks = (
            (db.oidc_application_sessions, {'_id': self.record['_id'], 'binding_revision': self.record['binding_revision'], 'expires_at': {'$gt': datetime.utcnow()}}),
            (db.oidc_principal_bindings, {'_id': binding_id, 'enabled': True, 'actor_id': self.actor_id, 'approved_role': self.role, 'authorization_revision': self.record['binding_revision']}),
            (db.users, {'_id': ObjectId(self.actor_id), 'is_active': True, 'role': self.role}),
        )
        for collection, query in checks:
            result = await collection.update_one(query, {'$inc': {'fill_use_revision': 1}}, session=session)
            if result.matched_count != 1:
                raise OidcFailure()
        if self.mini_session_id:
            result = await db.oidc_mini_sessions.update_one({
                "_id": self.mini_session_id, "source_session_id": self.session_hash,
                "actor_id": self.actor_id, "expires_at": {"$gt": datetime.utcnow()},
            }, {'$inc': {'fill_use_revision': 1}}, session=session)
            if result.matched_count != 1:
                raise OidcFailure()


class OidcFailure(Exception):
    """Safe outward error. Never expose provider messages or credential material."""


class OidcUnavailable(Exception):
    """Online source status could not be verified; protected operations fail closed."""


async def ensure_identity_indexes(db):
    # Unlike a best-effort business index, these are an enabled auth prerequisite.
    for name in ("oidc_login_transactions", "oidc_application_sessions"):
        await db[name].create_index("expires_at", expireAfterSeconds=0, name="expires_at_ttl")
    for name in ("oidc_mini_login_transactions", "oidc_mini_sessions"):
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

    async def start(self, old_browser_secret=None, *, mini_transaction_id=None):
        metadata = await self.metadata()
        browser_secret = secrets.token_urlsafe(32)
        state, nonce, verifier = (secrets.token_urlsafe(48) for _ in range(3))
        async with self.oauth() as client:
            url, _ = client.create_authorization_url(metadata["authorization_endpoint"],
                state=state, nonce=nonce, code_verifier=verifier)
        if old_browser_secret:
            await self.db.oidc_login_transactions.delete_many({"browser_hash": digest(old_browser_secret)})
        transaction = {
            "_id": digest(state), "browser_hash": digest(browser_secret), "nonce": nonce,
            "verifier": verifier, "mini_transaction_id": mini_transaction_id,
            "expires_at": datetime.utcnow() + timedelta(seconds=300)}
        if mini_transaction_id is not None:
            encrypted = Fernet(self.settings.session_encryption_key.get_secret_value().encode("ascii")).encrypt(
                json.dumps({"authorization_url": url, "browser_secret": browser_secret},
                           separators=(",", ":")).encode("utf-8")).decode("ascii")
            transaction["mini_authorization_encrypted"] = encrypted
        await self.db.oidc_login_transactions.insert_one(transaction)
        return url, browser_secret

    async def mini_authorization_for_browser(self, mini_transaction_id, browser_secret):
        """Return the same pending OIDC redirect only to its original browser cookie."""
        if (not isinstance(mini_transaction_id, str) or len(mini_transaction_id) > 128
                or not isinstance(browser_secret, str) or not 1 <= len(browser_secret) <= 256):
            return None
        transaction = await self.db.oidc_login_transactions.find_one({
            "browser_hash": digest(browser_secret), "mini_transaction_id": mini_transaction_id,
            "expires_at": {"$gt": datetime.utcnow()}})
        encrypted = (transaction or {}).get("mini_authorization_encrypted")
        if not isinstance(encrypted, str):
            return None
        try:
            payload = json.loads(Fernet(self.settings.session_encryption_key.get_secret_value().encode("ascii")).decrypt(
                encrypted.encode("ascii")).decode("utf-8"))
            target = payload.get("authorization_url")
            saved_secret = payload.get("browser_secret")
            parsed = urlsplit(target) if isinstance(target, str) else None
            issuer = urlsplit(self.settings.issuer)
            if (not parsed or parsed.scheme != "https" or parsed.netloc != issuer.netloc
                    or parsed.username or parsed.password or parsed.fragment
                    or not isinstance(saved_secret, str)
                    or not secrets.compare_digest(saved_secret, browser_secret)):
                raise OidcFailure()
        except Exception:
            raise OidcFailure() from None
        return target

    async def callback(self, state, code, browser_secret, *, include_transaction=False):
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
        from app.operations.runtime import session_timeout_minutes
        from app.core.config import settings as runtime_settings
        # The administrative lifetime is an authentication constraint, not just
        # a browser cookie preference. Read it before creating a server session;
        # an unavailable policy store must not silently issue a longer session.
        policy_seconds = 60 * await session_timeout_minutes(
            self.db, runtime_settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        # ID-token expiry bounds the initial assertion, not a session that is
        # independently checked against the source on every protected request.
        expiry = time.time() + min(source_lifetime, self.settings.session_seconds, policy_seconds)
        if expiry <= time.time():
            raise OidcFailure()
        binding = await self.db.oidc_principal_bindings.find_one({
            "_id": digest(claims["iss"] + "\0" + claims["sub"]),
            "issuer": claims["iss"], "subject": claims["sub"]})
        await self.db.oidc_application_sessions.insert_one({
            "_id": digest(sid), "issuer": claims["iss"], "subject": claims["sub"],
            "binding_revision": binding_revision(binding),
            "csrf_hash": digest(csrf), "expires_at": datetime.utcfromtimestamp(expiry),
            "source_token_encrypted": Fernet(self.settings.session_encryption_key.get_secret_value().encode("ascii")).encrypt(token["access_token"].encode()).decode("ascii")})
        # ID tokens are discarded; delegated access token is encrypted for live status checks.
        result = (sid, csrf, max(0, int(expiry - time.time())))
        return (*result, transaction.get("mini_transaction_id")) if include_transaction else result

    async def load_session(self, sid, *, verify_source=True):
        if not sid or len(sid) > 256:
            return None
        record = await self.db.oidc_application_sessions.find_one({
            "_id": digest(sid), "issuer": self.settings.issuer,
            "expires_at": {"$gt": datetime.utcnow()}})
        if record is None:
            return None
        if verify_source:
            if not await self._source_session_active(record):
                return None
        return record

    async def _source_session_active(self, record):
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
            return False
        return True

    async def actor_for_session(self, sid):
        record = await self.load_session(sid)
        if record is None:
            return None, None
        return await self._actor_for_record(record)

    async def actor_for_session_hash(self, session_hash):
        """Validate a referenced browser session using the same live checks."""
        if not isinstance(session_hash, str) or len(session_hash) != 64:
            return None, None
        record = await self.db.oidc_application_sessions.find_one({
            "_id": session_hash, "issuer": self.settings.issuer,
            "expires_at": {"$gt": datetime.utcnow()}})
        if record is None:
            return None, None
        if not await self._source_session_active(record):
            return None, None
        return await self._actor_for_record(record)

    async def _actor_for_record(self, record):
        if "binding_revision" not in record:
            # Historical cookies have no proof of the authorization reviewed at
            # authentication time. They must authenticate again, never upgrade.
            await self.db.oidc_application_sessions.delete_one({"_id": record["_id"]})
            return None, None
        # Review metadata is mandatory. Matching names/emails never create mappings.
        binding = await self.db.oidc_principal_bindings.find_one({
            "_id": digest(record["issuer"] + "\0" + record["subject"]),
            "issuer": record["issuer"], "subject": record["subject"]})
        if binding and (binding_revision(binding) is None
                        or record["binding_revision"] != binding_revision(binding)):
            await self.db.oidc_application_sessions.delete_one({"_id": record["_id"]})
            return None, None
        if not binding and record["binding_revision"] is not None:
            await self.db.oidc_application_sessions.delete_one({"_id": record["_id"]})
            return None, None
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
        if actor and not await self.db.oidc_principal_bindings.find_one({
                "_id": binding["_id"], "enabled": True,
                "authorization_revision": record["binding_revision"]}):
            # A review concurrent with actor lookup cannot authorize the old cookie.
            await self.db.oidc_application_sessions.delete_one({"_id": record["_id"]})
            return None, None
        return record, actor

    @staticmethod
    def mini_challenge(verifier):
        if not isinstance(verifier, str) or len(verifier) != 43:
            return None
        try:
            raw = verifier.encode("ascii")
        except UnicodeEncodeError:
            return None
        if any(char not in b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_" for char in raw):
            return None
        value = hashlib.sha256(raw).digest()
        return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")

    async def create_mini_transaction(self, challenge):
        if not isinstance(challenge, str) or len(challenge) != 43:
            raise OidcFailure()
        try:
            if any(char not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_" for char in challenge):
                raise OidcFailure()
            decoded = base64.urlsafe_b64decode(challenge + "=")
            if len(decoded) != 32 or base64.urlsafe_b64encode(decoded).rstrip(b"=").decode("ascii") != challenge:
                raise OidcFailure()
        except Exception:
            raise OidcFailure() from None
        transaction_id = secrets.token_urlsafe(32)
        await self.db.oidc_mini_login_transactions.insert_one({
            "_id": digest(transaction_id), "challenge_hash": digest(challenge),
            "status": "pending", "expires_at": datetime.utcnow() + timedelta(seconds=300)})
        return transaction_id

    async def mini_transaction(self, transaction_id, verifier):
        challenge = self.mini_challenge(verifier)
        if not transaction_id or len(transaction_id) > 128 or challenge is None:
            return None
        transaction = await self.db.oidc_mini_login_transactions.find_one({
            "_id": digest(transaction_id), "challenge_hash": digest(challenge),
            "expires_at": {"$gt": datetime.utcnow()}})
        return transaction

    async def set_mini_login_result(self, transaction_id, source_session_id, *, approved_binding):
        """Bind only this browser callback to its mini transaction."""
        result = await self.db.oidc_mini_login_transactions.update_one({
            "_id": digest(transaction_id), "status": "oidc_started",
            "expires_at": {"$gt": datetime.utcnow()}},
            {"$set": {"status": "awaiting_confirmation" if approved_binding else "denied",
                      "source_session_id": source_session_id}})
        return result.modified_count == 1

    async def mini_transaction_status(self, transaction_id, verifier):
        challenge = self.mini_challenge(verifier)
        if not transaction_id or len(transaction_id) > 128 or challenge is None:
            return None, None
        query = {"_id": digest(transaction_id), "challenge_hash": digest(challenge)}
        transaction = await self.db.oidc_mini_login_transactions.find_one({
            **query, "expires_at": {"$gt": datetime.utcnow()}})
        if transaction is None:
            old = await self.db.oidc_mini_login_transactions.find_one(query)
            return (old, "expired") if old else (None, None)
        return transaction, transaction["status"]

    async def approve_mini_transaction(self, transaction_id, browser_sid):
        transaction = await self.db.oidc_mini_login_transactions.find_one({
            "_id": digest(transaction_id), "status": "awaiting_confirmation",
            "source_session_id": digest(browser_sid), "expires_at": {"$gt": datetime.utcnow()}})
        if transaction is None:
            raise OidcFailure()
        record, actor = await self.actor_for_session(browser_sid)
        if record is None or actor is None or record["_id"] != transaction.get("source_session_id"):
            await self.db.oidc_mini_login_transactions.update_one(
                {"_id": transaction["_id"], "status": "awaiting_confirmation"},
                {"$set": {"status": "denied"}})
            raise OidcFailure()
        updated = await self.db.oidc_mini_login_transactions.update_one({
            "_id": transaction["_id"], "status": "awaiting_confirmation",
            "source_session_id": record["_id"], "expires_at": {"$gt": datetime.utcnow()}},
            {"$set": {"status": "ready", "approved_at": datetime.utcnow()}})
        if updated.modified_count != 1:
            raise OidcFailure()
        return actor

    async def exchange_mini_transaction(self, transaction_id, verifier):
        transaction = await self.mini_transaction(transaction_id, verifier)
        if transaction is None or transaction.get("status") != "ready":
            raise OidcFailure()
        source_hash = transaction.get("source_session_id")
        record, actor = await self.actor_for_session_hash(source_hash)
        if record is None or actor is None:
            raise OidcFailure()
        # Single-use consume is atomic across workers; a race loser receives no token.
        consumed = await self.db.oidc_mini_login_transactions.find_one_and_delete({
            "_id": transaction["_id"], "challenge_hash": transaction["challenge_hash"],
            "source_session_id": source_hash, "status": "ready",
            "expires_at": {"$gt": datetime.utcnow()}})
        if consumed is None:
            raise OidcFailure()
        token = secrets.token_urlsafe(32)
        expires_at = min(record["expires_at"], datetime.utcnow() + timedelta(minutes=15))
        await self.db.oidc_mini_sessions.insert_one({
            "_id": digest(token), "source_session_id": source_hash,
            "actor_id": str(actor["_id"]), "expires_at": expires_at})
        return token, max(0, int((expires_at - datetime.utcnow()).total_seconds())), actor

    async def actor_for_mini_session(self, token):
        if not token or len(token) > 256:
            return None, None
        mini = await self.db.oidc_mini_sessions.find_one({
            "_id": digest(token), "expires_at": {"$gt": datetime.utcnow()}})
        if mini is None:
            return None, None
        record, actor = await self.actor_for_session_hash(mini.get("source_session_id"))
        if record is None or actor is None or str(actor["_id"]) != mini.get("actor_id"):
            await self.db.oidc_mini_sessions.delete_one({"_id": mini["_id"]})
            return None, None
        return mini, actor

    async def revoke_mini_session(self, token):
        if not token or len(token) > 256:
            return False
        result = await self.db.oidc_mini_sessions.delete_one({"_id": digest(token)})
        return result.deleted_count == 1

    async def fill_delegation(self, sid, actor):
        record, current = await self.actor_for_session(sid)
        if (record is None or current is None or str(current['_id']) != str(actor.id) or current['role'] != actor.role):
            raise OidcFailure()
        return self._build_fill_delegation(sid, record, current)

    def _build_fill_delegation(self, sid, record, current, *, session_hash=None, mini_session_id=None):
        try:
            token = Fernet(self.settings.session_encryption_key.get_secret_value().encode('ascii')).decrypt(record['source_token_encrypted'].encode('ascii')).decode('utf-8')
        except Exception:
            raise OidcUnavailable() from None
        return FillDelegation(self, sid, token, record, str(current['_id']), current['role'],
                              session_hash=session_hash, mini_session_id=mini_session_id)

    async def fill_delegation_for_mini_session(self, token, actor):
        """Derive the existing reviewed OIDC delegation from a live mini session.

        Mini sessions keep only the source-session hash, so no browser cookie or
        client-supplied source identity is accepted on this path.
        """
        mini, mini_actor = await self.actor_for_mini_session(token)
        if (mini is None or mini_actor is None or str(mini_actor['_id']) != str(actor.id)
                or mini_actor['role'] != actor.role):
            raise OidcFailure()
        source_hash = mini.get('source_session_id')
        record, current = await self.actor_for_session_hash(source_hash)
        if (record is None or current is None or str(current['_id']) != str(actor.id)
                or current['role'] != actor.role):
            raise OidcFailure()
        return self._build_fill_delegation(
            None, record, current, session_hash=source_hash, mini_session_id=mini['_id'])

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
