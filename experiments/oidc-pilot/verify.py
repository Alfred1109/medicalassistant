"""Real loopback HTTP verification. Every account/database/key is synthetic."""
import base64
import hashlib
import json
from pathlib import Path
import re
import secrets
import threading
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit
import uuid

from pilot import build_apps, ROOT, ISSUER, RP, CALLBACK, CLIENT_ID, db, User, make_server
import requests


def replace_query(url, **values):
    parts = urlsplit(url)
    query = {key: value[0] for key, value in parse_qs(parts.query).items()}
    query.update(values)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))


def run():
    runtime = ROOT / ".runtime" / ("verify-" + uuid.uuid4().hex)
    source, rp = build_apps(runtime)
    servers = [make_server("127.0.0.1", 15512, source, threaded=True), make_server("127.0.0.1", 15513, rp, threaded=True)]
    for server in servers:
        threading.Thread(target=server.serve_forever, daemon=True).start()
    results = {}
    s = requests.Session()
    try:
        response = s.get(ISSUER + "/auth/login", timeout=5)
        csrf = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', response.text).group(1)
        s.get(ISSUER + "/_pilot/captcha", timeout=5).raise_for_status()
        credentials = source.pilot["credentials"]
        response = s.post(ISSUER + "/auth/login", data={**credentials, "csrf_token": csrf, "captcha": "2468"}, allow_redirects=False, timeout=5)
        assert response.status_code == 302, "real source login failed"
        results["source_password_login"] = True

        def start_flow(**changes):
            start = s.get(RP + "/auth/oidc/start", allow_redirects=False, timeout=5)
            assert start.status_code == 302
            authorization = replace_query(start.headers["Location"], **changes)
            authorized = s.get(authorization, allow_redirects=False, timeout=5)
            assert authorized.status_code == 302, authorized.text
            assert authorized.headers["Location"].startswith(CALLBACK + "?")
            return authorized.headers["Location"]

        callback = start_flow()
        response = s.get(callback, timeout=5)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["authenticated"] and body["issuer"] == ISSUER and body["subject"] == source.pilot["subject"]
        assert body["clinical_permissions"] == []
        assert s.get(RP + "/clinical/patients", timeout=5).status_code == 403
        assert all("token" not in cookie.value and len(cookie.value) < 100 for cookie in s.cookies)
        results["authorization_code_pkce_login"] = True
        results["no_clinical_permission"] = True
        assert s.get(callback, timeout=5).status_code == 400
        results["callback_replay_rejected"] = True

        callback = start_flow()
        assert s.get(replace_query(callback, state="wrong-state"), timeout=5).status_code == 400
        results["wrong_state_rejected"] = True
        callback = start_flow(nonce="wrong-nonce")
        assert s.get(callback, timeout=5).status_code == 400
        results["wrong_nonce_rejected"] = True

        def raw_code():
            verifier = secrets.token_urlsafe(48)
            challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
            response = s.get(ISSUER + "/oidc/authorize", params={
                "response_type": "code", "client_id": CLIENT_ID, "redirect_uri": CALLBACK,
                "scope": "openid profile", "state": secrets.token_urlsafe(24), "nonce": secrets.token_urlsafe(24),
                "code_challenge": challenge, "code_challenge_method": "S256"}, allow_redirects=False, timeout=5)
            assert response.status_code == 302, response.text
            return parse_qs(urlsplit(response.headers["Location"]).query)["code"][0], verifier

        def exchange(code, verifier):
            return s.post(ISSUER + "/oidc/token", auth=(CLIENT_ID, source.pilot["client_secret"]), data={
                "grant_type": "authorization_code", "code": code, "redirect_uri": CALLBACK, "code_verifier": verifier}, timeout=5)

        code, verifier = raw_code()
        assert exchange(code, "x" * 60).status_code == 400
        assert exchange(code, verifier).status_code == 200
        assert exchange(code, verifier).status_code == 400
        results["wrong_pkce_rejected"] = True
        results["authorization_code_replay_rejected"] = True
        code, verifier = raw_code()
        with source.app_context():
            user = db.session.get(User, source.pilot["user_id"])
            user.is_active = False
            db.session.commit()
        assert exchange(code, verifier).status_code == 400
        results["disabled_source_user_rejected_at_exchange"] = True
        (ROOT / ".runtime" / "verification-result.json").write_text(json.dumps(results, indent=2))
        print(json.dumps(results))
    finally:
        s.close()
        for server in servers:
            server.shutdown()
        with source.app_context():
            db.session.remove()
            db.engine.dispose()
        # Exact fresh experiment directory only, no source instance paths.
        import shutil
        shutil.rmtree(runtime)


if __name__ == "__main__":
    run()
