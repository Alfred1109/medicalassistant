"""Real ASGI catalog boundary plus HTTP transport contracts; synthetic data only."""
import json
from types import SimpleNamespace
from unittest.mock import patch

import httpx
import pytest
from fastapi import FastAPI

from app.core.auth import get_current_active_user
from app.integrations.forms import catalog_router as routes
from app.integrations.forms.client import FormPlatformClient, FormPlatformError
from app.core.config import settings

@pytest.fixture
def anyio_backend():
    return "asyncio"


SOURCE = {"system": "form-platform-11344", "environment": "production"}
PAGE = {"limit": 50, "has_more": False, "next_cursor": None}


def fixture(handler, role="admin"):
    app = FastAPI()
    app.include_router(routes.router, prefix="/api")
    calls = []

    def transport(request):
        calls.append(request)
        return handler(request)

    client = FormPlatformClient("https://source.example", "catalog-test", "synthetic-secret", 1,
                                transport=httpx.MockTransport(transport))
    app.dependency_overrides[get_current_active_user] = lambda: SimpleNamespace(role=role, id="synthetic-actor")
    app.dependency_overrides[routes.get_catalog_client] = lambda: client
    return app, client, calls


async def get(app, path):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://rp.example") as client:
        return await client.get("/api/integrations/forms/catalog" + path)


@pytest.mark.anyio
async def test_admin_catalog_is_whitelisted_read_only_and_uses_machine_auth():
    def respond(request):
        assert request.method == "GET"
        assert request.url.path == "/integration/v1/projects"
        assert dict(request.url.params) == {"limit": "50"}
        assert request.headers["authorization"] == "Bearer catalog-test.synthetic-secret"
        return httpx.Response(200, json={"data": [{"project_id": 4, "name": "合成项目", "status": "active",
                                                   "source": SOURCE, "secret": "must-not-escape"}],
                                        "page": PAGE, "private": "must-not-escape"})
    app, _, calls = fixture(respond)
    response = await get(app, "/projects")
    assert response.status_code == 200 and len(calls) == 1
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {"data": [{"project_id": 4, "name": "合成项目", "status": "active", "source": SOURCE}], "page": PAGE}
    assert "must-not-escape" not in response.text


@pytest.mark.anyio
@pytest.mark.parametrize("role", ["doctor", "health_manager", "patient"])
async def test_non_admin_never_constructs_source_client(role):
    app, _, calls = fixture(lambda r: httpx.Response(200), role=role)
    def forbidden():
        raise AssertionError("non-admin must not construct source credentials")
    app.dependency_overrides[routes.get_catalog_client] = forbidden
    response = await get(app, "/projects")
    assert response.status_code == 403 and calls == []


@pytest.mark.anyio
async def test_anonymous_rejected_without_source_request():
    from fastapi import HTTPException
    app, _, calls = fixture(lambda r: httpx.Response(200))
    def reject():
        raise HTTPException(401)
    app.dependency_overrides[get_current_active_user] = reject
    response = await get(app, "/projects")
    assert response.status_code == 401 and calls == []


@pytest.mark.anyio
@pytest.mark.parametrize("path", [
    "/projects?operator_user_id=1", "/projects?limit=1&limit=2", "/projects?cursor=../private",
    "/projects?limit=0", "/projects?limit=201", "/projects/0/forms", "/projects/-1/centers",
    "/projects/2/subjects?center_id=0", "/projects/2/forms?status=deleted",
    "/projects/2/subjects?include_unassigned=true", "/projects/2/subjects?status=unknown",
    "/projects/2/centers/3/subjects/4/patient-reference?operator_user_id=1",
])
async def test_invalid_parameters_never_reach_source(path):
    app, _, calls = fixture(lambda r: httpx.Response(200))
    response = await get(app, path)
    assert response.status_code == 422 and calls == []


@pytest.mark.anyio
async def test_paginated_subject_params_encoded_and_context_checked():
    def respond(request):
        assert request.url.path == "/integration/v1/projects/2/subjects"
        assert dict(request.url.params) == {"limit": "2", "cursor": "YWJj=", "center_id": "3", "status": "enrolled"}
        return httpx.Response(200, json={"data": [{"subject_id": 4, "project_id": 2, "center_id": 3,
                                                    "code": "SYN-4", "status": "enrolled", "patient_name": "strip"}],
                                        "page": {"limit": 2, "has_more": True, "next_cursor": "bmV4dA=="}})
    app, _, _ = fixture(respond)
    response = await get(app, "/projects/2/subjects?center_id=3&status=enrolled&limit=2&cursor=YWJj%3D")
    assert response.status_code == 200
    assert "patient_name" not in response.text


@pytest.mark.anyio
async def test_patient_reference_exact_context_and_only_ids():
    reference = dict(source=SOURCE, project_id=2, center_id=3, subject_id=4,
                     patient_id=10, patient_archive_id=11, name="must-not-escape", email="must-not-escape")
    app, client, calls = fixture(lambda r: httpx.Response(200, json=reference))
    response = await get(app, "/projects/2/centers/3/subjects/4/patient-reference")
    assert response.status_code == 200
    assert set(response.json()) == {"source", "project_id", "center_id", "subject_id", "patient_id", "patient_archive_id"}
    assert calls[0].url.path == "/integration/v1/projects/2/centers/3/subjects/4/patient-reference"
    reference["subject_id"] = 9
    assert (await get(app, "/projects/2/centers/3/subjects/4/patient-reference")).status_code == 502


@pytest.mark.anyio
@pytest.mark.parametrize("body", [
    {"data": [{"center_id": 3, "project_id": 9, "name": "other", "center_code": "X", "status": "active"}], "page": PAGE},
    {"data": [], "page": {"limit": 50, "has_more": True, "next_cursor": None}},
    {"data": [], "page": {"limit": 50, "has_more": "false", "next_cursor": None}},
    {"data": [], "page": {"limit": 49, "has_more": False, "next_cursor": None}},
    {"data": "not-a-list", "page": PAGE},
])
async def test_malformed_or_cross_context_catalog_is_rejected(body):
    app, _, _ = fixture(lambda r: httpx.Response(200, json=body))
    response = await get(app, "/projects/2/centers")
    assert response.status_code == 502


@pytest.mark.anyio
async def test_form_version_and_project_context_are_validated():
    form = {"form_id": 6, "project_id": 2, "title": "合成问卷", "status": "active", "current_version": {
        "form_id": 6, "family_id": 7, "version": 1, "version_state": "current", "definition_sha256": "a" * 64}}
    app, _, _ = fixture(lambda r: httpx.Response(200, json={"data": [form], "page": PAGE}))
    assert (await get(app, "/projects/2/forms")).status_code == 200
    form["current_version"]["form_id"] = 8
    assert (await get(app, "/projects/2/forms")).status_code == 502


@pytest.mark.anyio
@pytest.mark.parametrize("status,expected,code", [(401, 502, "FORM_PLATFORM_AUTH_REJECTED"),
    (403, 502, "FORM_PLATFORM_AUTH_REJECTED"), (404, 404, "FORM_PLATFORM_CATALOG_REJECTED"),
    (500, 502, "FORM_PLATFORM_CATALOG_REJECTED")])
async def test_remote_messages_and_credentials_not_reflected(status, expected, code):
    app, _, _ = fixture(lambda r: httpx.Response(status, json={"message": "synthetic-secret patient-record", "code": "untrusted"}))
    response = await get(app, "/projects")
    assert response.status_code == expected and response.json()["detail"]["error"] == code
    assert "synthetic-secret" not in response.text and "patient-record" not in response.text


@pytest.mark.anyio
async def test_timeout_redacted():
    def respond(request):
        raise httpx.ReadTimeout("patient-record synthetic-secret", request=request)
    app, _, _ = fixture(respond)
    response = await get(app, "/projects")
    assert response.status_code == 502
    assert response.json()["detail"]["error"] == "FORM_PLATFORM_UNAVAILABLE"
    assert "synthetic-secret" not in response.text


def test_missing_config_and_insecure_catalog_config_fail_closed():
    with patch.object(FormPlatformClient, "from_settings", side_effect=FormPlatformError("private")):
        with pytest.raises(Exception) as error: routes.get_catalog_client()
        assert error.value.status_code == 503 and "private" not in str(error.value.detail)
    for url, verify in [("http://source.example", True), ("https://source.example", False)]:
        client = FormPlatformClient(url, "id", "secret", 1, verify_tls=verify)
        with patch.object(FormPlatformClient, "from_settings", return_value=client):
            with pytest.raises(Exception) as error: routes.get_catalog_client()
            assert error.value.status_code == 503


def test_source_origin_is_controlled_and_production_requires_https():
    assert FormPlatformClient("https://SOURCE.example/", "id", "secret", 1).source_origin == "https://source.example"
    for url in ["https://user:secret@source.example", "https://source.example?a=1", "https://source.example#x", "https://source.example/path", "https://source.example:bad", "https://source.example\n"]:
        with pytest.raises(FormPlatformError): FormPlatformClient(url, "id", "secret", 1).source_origin
    with patch.object(settings, "ENVIRONMENT", "production"):
        with pytest.raises(FormPlatformError): FormPlatformClient("http://source.example", "id", "secret", 1).source_origin


@pytest.mark.anyio
async def test_form_version_hides_questions_and_checks_published_context():
    version = {"form_id": 6, "family_id": 7, "version": 2, "version_state": "current", "definition_sha256": "a" * 64}
    body = {"source": SOURCE, "form": {"form_id": 6, "project_id": 2, "title": "合成问卷", "status": "active",
                                       "current_version": version}, "version": version,
            "definition": {"questions": [{"private": "must-not-escape"}]}}
    def respond(request):
        assert request.url.path == "/integration/v1/forms/6/definition"
        assert dict(request.url.params) == {"version": "2"}
        return httpx.Response(200, json=body)
    app, _, _ = fixture(respond)
    response = await get(app, "/projects/2/forms/6/version?version=2")
    assert response.status_code == 200
    assert "definition" not in response.json() and "must-not-escape" not in response.text
    body["form"]["project_id"] = 3
    assert (await get(app, "/projects/2/forms/6/version?version=2")).status_code == 502


@pytest.mark.anyio
@pytest.mark.parametrize("status,state,digest", [("draft", "current", "a" * 64),
    ("active", "draft", "a" * 64), ("active", "retired", "a" * 64), ("active", "current", None)])
async def test_form_not_bindable_without_active_current_snapshot(status, state, digest):
    version = {"form_id": 6, "family_id": 7, "version": 1, "version_state": state, "definition_sha256": digest}
    body = {"source": SOURCE, "form": {"form_id": 6, "project_id": 2, "title": "合成问卷", "status": status,
                                       "current_version": version}, "version": version}
    app, _, _ = fixture(lambda r: httpx.Response(200, json=body))
    response = await get(app, "/projects/2/forms/6/version")
    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "FORM_DEFINITION_NOT_PUBLISHED"


@pytest.mark.anyio
async def test_source_unpublished_definition_has_clear_error_without_remote_body():
    app, _, _ = fixture(lambda r: httpx.Response(409, json={"message": "private", "code": "definition_not_published"}))
    response = await get(app, "/projects/2/forms/6/version")
    assert response.status_code == 409 and "private" not in response.text
    assert response.json()["detail"]["error"] == "FORM_DEFINITION_NOT_PUBLISHED"
