"""Filling requires separate opt-in; directory credentials alone grant no launch."""
import os
import unittest
from unittest.mock import patch

from app.integrations.forms import service
import test_integration_forms_contract as forms_contract


class FormFillFeatureGateTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # Reuse the existing synthetic DB/remote setup, not its test methods.
        self.fixture = forms_contract.IntegrationFormsContractTests(methodName="runTest")
        self.fixture.setUp()
        self.env = patch.dict(os.environ, {}, clear=False)
        self.env.start()
        os.environ.pop("FORM_PLATFORM_FILL_ENABLED", None)

    async def asyncTearDown(self):
        self.env.stop()
        await self.fixture.asyncTearDown()
        self.fixture.doCleanups()

    async def test_default_disabled_with_valid_read_only_client_has_no_side_effects(self):
        f = self.fixture
        response = await f.client.post("/api/integrations/forms/fill-tasks",
                                       json=f.payload(), headers=f.auth())
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"]["error"], "FORM_FILL_DISABLED")
        self.assertEqual(f.remote.requests, [])
        self.assertEqual(f.collection.docs, {})

    async def test_direct_service_cannot_bypass_default_gate(self):
        f = self.fixture
        with self.assertRaises(service.FormIntegrationError) as raised:
            await service.create_fill_task(f.database, f.remote_client, f.operator, f.payload())
        self.assertEqual(raised.exception.error_code, "FORM_FILL_DISABLED")
        self.assertEqual(f.remote.requests, [])
        self.assertEqual(f.collection.docs, {})

    async def test_invalid_or_false_flags_fail_closed(self):
        f = self.fixture
        for value, code in (("false", "FORM_FILL_DISABLED"), ("1", "FORM_FILL_CONFIGURATION_INVALID"),
                            ("yes", "FORM_FILL_CONFIGURATION_INVALID"), ("", "FORM_FILL_CONFIGURATION_INVALID")):
            with self.subTest(value=value), patch.dict(os.environ, {"FORM_PLATFORM_FILL_ENABLED": value}):
                response = await f.client.post("/api/integrations/forms/fill-tasks",
                                               json=f.payload(), headers=f.auth())
                self.assertEqual(response.status_code, 503)
                self.assertEqual(response.json()["detail"]["error"], code)
        self.assertEqual(f.remote.requests, [])
        self.assertEqual(f.collection.docs, {})

    async def create_enabled(self):
        f = self.fixture
        with patch.dict(os.environ, {"FORM_PLATFORM_FILL_ENABLED": "true"}):
            response = await f.client.post("/api/integrations/forms/fill-tasks",
                                           json=f.payload(), headers=f.auth())
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["id"]

    async def test_disabling_launch_keeps_task_reads_and_cancellation_available(self):
        f = self.fixture
        task_id = await self.create_enabled()
        launch = await f.client.get(f"/api/integrations/forms/fill-tasks/{task_id}/embed-url", headers=f.auth())
        self.assertEqual(launch.status_code, 503)
        self.assertEqual(launch.json()["detail"]["error"], "FORM_FILL_DISABLED")
        self.assertNotIn("embedUrl", launch.json())
        detail = await f.fetch_task(task_id)
        self.assertEqual(detail.status_code, 200)
        listing = await f.client.get("/api/integrations/forms/fill-tasks", headers=f.auth())
        self.assertEqual(listing.status_code, 200)
        canceled = await f.client.post(f"/api/integrations/forms/fill-tasks/{task_id}/cancel", headers=f.auth())
        self.assertEqual(canceled.status_code, 200, canceled.text)
        self.assertEqual(canceled.json()["status"], "cancelled")

    async def test_disabling_launch_keeps_existing_submission_confirmation_available(self):
        f = self.fixture
        task_id = await self.create_enabled()
        f.remote.session_body.update(status="submitted", response_id=42)
        confirmed = await f.client.post(f"/api/integrations/forms/fill-tasks/{task_id}/confirm", headers=f.auth())
        self.assertEqual(confirmed.status_code, 200, confirmed.text)
        self.assertEqual(confirmed.json()["status"], "confirmed")

    async def test_explicit_test_opt_in_retains_existing_launch_contract(self):
        f = self.fixture
        task_id = await self.create_enabled()
        with patch.dict(os.environ, {"FORM_PLATFORM_FILL_ENABLED": "true"}):
            response = await f.client.get(f"/api/integrations/forms/fill-tasks/{task_id}/embed-url", headers=f.auth())
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["embedUrl"], f.remote.session_body["embed_url"])
