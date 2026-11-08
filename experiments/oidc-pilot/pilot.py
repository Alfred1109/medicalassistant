"""Loopback-only OIDC experiment. Imports the real questionnaire app against a NEW DB.

No route is installed in either application's production factory. Runtime state,
private keys and synthetic credentials live only in the ignored runtime directory.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import signal
import sys
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parent
SOURCE = Path(os.environ.get("QUESTIONNAIRE_ROOT", str(ROOT.parents[2] / "康复问卷管理系统"))).resolve()
os.environ["FLASK_ENV"] = "testing"
os.environ["AUTHLIB_INSECURE_TRANSPORT"] = "true"  # loopback experiment only
sys.path.insert(0, str(ROOT / ".deps"))
sys.path.insert(0, str(SOURCE))

from flask import Flask, jsonify, redirect, request, session, url_for
from flask.sessions import SessionInterface, SessionMixin
from flask_login import current_user
from authlib.integrations.flask_oauth2 import AuthorizationServer
from authlib.integrations.flask_client import OAuth
from authlib.integrations.sqla_oauth2 import OAuth2ClientMixin, OAuth2AuthorizationCodeMixin
from authlib.oauth2.rfc6749 import grants
from authlib.oauth2.rfc7636 import CodeChallenge
from authlib.oidc.core import grants as oidc_grants, UserInfo
from joserfc.jwk import RSAKey, KeySet
from werkzeug.serving import make_server as _make_server, WSGIRequestHandler
from urllib.parse import urlsplit
from app import create_app, db
from app.models import User
from app.services.authentication_state_service import AuthenticationStateStore

ISSUER = "http://127.0.0.1:15512"
RP = "http://127.0.0.1:15513"
CLIENT_ID = "rehabman-oidc-isolated-pilot"
CALLBACK = RP + "/auth/oidc/callback"


class ProtocolRequestHandler(WSGIRequestHandler):
    def log_request(self, code="-", size="-"):
        # Authorization codes, nonce, state and PKCE challenges are never logged.
        self.log("info", '%s %s %s', self.command, urlsplit(self.path).path, code)


def make_server(*args, **kwargs):
    return _make_server(*args, request_handler=ProtocolRequestHandler, **kwargs)


class ServerSession(dict, SessionMixin):
    def __init__(self, values, sid):
        super().__init__(values)
        self.sid = sid


class MemorySessions(SessionInterface):
    """Server-side, process-local experiment sessions; cookie contains only random ID."""
    def __init__(self):
        self.values = {}

    def open_session(self, app, req):
        sid = req.cookies.get(app.config["SESSION_COOKIE_NAME"])
        if sid not in self.values:
            sid = secrets.token_urlsafe(32)
        values, expiry = self.values.get(sid, ({}, 0))
        return ServerSession(dict(values) if expiry > time.time() else {}, sid)

    def save_session(self, app, sess, response):
        self.values[sess.sid] = (dict(sess), time.time() + 600)
        response.set_cookie(app.config["SESSION_COOKIE_NAME"], sess.sid,
                            httponly=True, samesite="Lax", secure=False, max_age=600)


class PilotClient(db.Model, OAuth2ClientMixin):
    __tablename__ = "oidc_pilot_client"
    id = db.Column(db.Integer, primary_key=True)


class PilotCode(db.Model, OAuth2AuthorizationCodeMixin):
    __tablename__ = "oidc_pilot_code"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)
    credential_snapshot = db.Column(db.String(64), nullable=False)


def build_apps(runtime):
    runtime = runtime.resolve()
    runtime.mkdir(mode=0o700, parents=True, exist_ok=False)
    (runtime / "sm4.key").write_text(secrets.token_hex(16))
    (runtime / "sm4.key").chmod(0o600)
    driver = SOURCE / ".local-only/sm4-sqlite/python"
    from app.services.database_encryption_service import DatabaseEncryptionService
    connection = DatabaseEncryptionService.connect(
        runtime / "source.sqlite3", key=bytes.fromhex((runtime / "sm4.key").read_text()),
        driver_path=str(driver), mode="rwc")
    connection.close()
    source = create_app("testing", config_overrides={
        "SECRET_KEY": secrets.token_hex(32), "SM4_DATA_KEY": secrets.token_hex(16),
        "SQLALCHEMY_DATABASE_URI": "sqlite:///" + str(runtime / "source.sqlite3"),
        "DATABASE_ENCRYPTION": "sm4", "DATABASE_SM4_KEY_FILE": str(runtime / "sm4.key"),
        "SM4_SQLITE_DRIVER_PATH": str(driver), "AUTH_STATE_PATH": str(runtime / "auth.sqlite3"),
        "SESSION_COOKIE_NAME": "oidc_pilot_source", "SESSION_COOKIE_SECURE": False,
        "REMEMBER_COOKIE_SECURE": False, "BACKGROUND_TASK_AUTO_RESUME": False,
        "WTF_CSRF_ENABLED": True,
    }, initialize_database=True)
    source.session_interface = MemorySessions()
    private_key = RSAKey.generate_key(2048, parameters={"kid": "pilot-" + uuid.uuid4().hex}, private=True)
    client_secret = secrets.token_urlsafe(32)
    credentials = {"username": "oidc_synthetic", "password": secrets.token_urlsafe(24)}
    subject = "pilot-" + uuid.uuid4().hex
    with source.app_context():
        db.create_all()
        user = User(username=credentials["username"], email="oidc-synthetic@example.invalid", role="user", is_active=True)
        user.set_password(credentials["password"])
        db.session.add(user)
        client = PilotClient(client_id=CLIENT_ID, client_secret=client_secret)
        client.set_client_metadata({"redirect_uris": [CALLBACK], "scope": "openid profile",
                                    "grant_types": ["authorization_code"], "response_types": ["code"],
                                    "token_endpoint_auth_method": "client_secret_basic",
                                    "id_token_signed_response_alg": "RS256"})
        db.session.add(client)
        db.session.commit()
        user_id = user.id

    class CodeGrant(grants.AuthorizationCodeGrant):
        TOKEN_ENDPOINT_AUTH_METHODS = ["client_secret_basic"]

        def save_authorization_code(self, code, req):
            obj = PilotCode(code=code, client_id=req.client.client_id, redirect_uri=req.payload.redirect_uri,
                            scope=req.scope, user_id=req.user.id, nonce=req.payload.data.get("nonce"),
                            code_challenge=req.payload.data.get("code_challenge"),
                            code_challenge_method=req.payload.data.get("code_challenge_method"),
                            auth_time=session.get("auth_issued_at", int(time.time())),
                            credential_snapshot=req.user.auth_session_token)
            db.session.add(obj)
            db.session.commit()
            return obj

        def query_authorization_code(self, code, client):
            obj = PilotCode.query.filter_by(code=code, client_id=client.client_id).first()
            return obj if obj and not obj.is_expired() else None

        def delete_authorization_code(self, obj):
            db.session.delete(obj)
            db.session.commit()

        def authenticate_user(self, obj):
            user = db.session.get(User, obj.user_id)
            return user if user and user.is_active and user.auth_session_token == obj.credential_snapshot else None

    class OpenIDCode(oidc_grants.OpenIDCode):
        def resolve_client_private_key(self, client):
            return KeySet([private_key])

        def get_client_claims(self, client):
            return {"iss": ISSUER}

        def exists_nonce(self, nonce, req):
            return bool(PilotCode.query.filter_by(client_id=req.payload.client_id, nonce=nonce).first())

        def generate_user_info(self, user, scope):
            return UserInfo(sub=subject, name="合成身份试验账号")

    server = AuthorizationServer(source,
        query_client=lambda cid: PilotClient.query.filter_by(client_id=cid).first(),
        save_token=lambda token, req: None)
    server.register_grant(CodeGrant, [CodeChallenge(required=True), OpenIDCode(require_nonce=True)])

    @source.get("/.well-known/openid-configuration")
    def metadata():
        return jsonify(issuer=ISSUER, authorization_endpoint=ISSUER + "/oidc/authorize",
                       token_endpoint=ISSUER + "/oidc/token", jwks_uri=ISSUER + "/oidc/jwks",
                       response_types_supported=["code"], subject_types_supported=["public"],
                       id_token_signing_alg_values_supported=["RS256"],
                       code_challenge_methods_supported=["S256"], scopes_supported=["openid", "profile"])

    @source.get("/oidc/jwks")
    def jwks():
        return jsonify(keys=[private_key.as_dict(private=False)])

    @source.get("/oidc/authorize")
    def authorize():
        if not current_user.is_authenticated:
            return redirect(url_for("auth.login", next=request.full_path))
        if request.args.get("code_challenge_method") != "S256":
            return jsonify(error="invalid_request"), 400
        return server.create_authorization_response(grant_user=current_user)

    @source.post("/oidc/token")
    def token():
        return server.create_token_response()
    # Only this experiment app grants a machine token endpoint CSRF exemption.
    from app import csrf
    csrf.exempt(token)

    @source.get("/_pilot/captcha")
    def synthetic_captcha():
        # Test fixture only: the actual /auth/login still verifies its state,
        # password and enabled user. This does not accept production captcha/MFA.
        sid = secrets.token_urlsafe(24)
        session["captcha_session_id"] = sid
        session["captcha_challenge_id"] = AuthenticationStateStore().issue_captcha("2468", sid)
        return jsonify(captcha="2468")

    rp = Flask("rehabman_oidc_pilot")
    rp.secret_key = secrets.token_hex(32)
    rp.config["SESSION_COOKIE_NAME"] = "oidc_pilot_rp"
    rp.session_interface = MemorySessions()
    oauth = OAuth(rp)
    oauth.register("source", client_id=CLIENT_ID, client_secret=client_secret,
                   server_metadata_url=ISSUER + "/.well-known/openid-configuration",
                   client_kwargs={"scope": "openid profile", "code_challenge_method": "S256"})

    @rp.get("/auth/oidc/start")
    def start():
        return oauth.source.authorize_redirect(CALLBACK, nonce=secrets.token_urlsafe(24))

    @rp.get("/auth/oidc/callback")
    def callback():
        try:
            token = oauth.source.authorize_access_token()
        except Exception:
            session.clear()
            return jsonify(error="OIDC_VALIDATION_FAILED"), 400
        # Tokens remain in server-side process memory; no clinical permissions.
        session.clear()
        session["token"] = token
        return redirect("/auth/session")

    @rp.get("/auth/session")
    def auth_session():
        token = session.get("token")
        if not token:
            return jsonify(authenticated=False), 401
        info = token["userinfo"]
        return jsonify(authenticated=True, issuer=info["iss"], subject=info["sub"],
                       clinical_permissions=[], source="isolated_oidc_pilot")

    @rp.get("/clinical/patients")
    def clinical():
        return jsonify(error="CLINICAL_GRANT_REQUIRED"), 403

    source.pilot = {"user_id": user_id, "subject": subject, "client_secret": client_secret,
                    "private_key": private_key, "credentials": credentials}
    credentials_file = runtime / "synthetic-credentials.json"
    credentials_file.write_text(json.dumps(credentials))
    credentials_file.chmod(0o600)
    return source, rp


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", type=Path, required=True)
    args = parser.parse_args()
    source, rp = build_apps(args.runtime)
    servers = [make_server("127.0.0.1", 15512, source, threaded=True),
               make_server("127.0.0.1", 15513, rp, threaded=True)]
    for server in servers:
        threading.Thread(target=server.serve_forever, daemon=True).start()
    print("isolated OIDC pilot ready: ports 15512/15513", flush=True)
    stopped = threading.Event()
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda *_: stopped.set())
    stopped.wait()
    for server in servers:
        server.shutdown()


if __name__ == "__main__":
    main()
