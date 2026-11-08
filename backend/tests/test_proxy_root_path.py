"""Real ASGI router redirects/docs under a trusted stripped proxy prefix."""
import unittest
from unittest.mock import patch

import httpx

from app.core.config import Settings
from app.main import app


class ProxyRootPathTests(unittest.IsolatedAsyncioTestCase):
    async def test_root_deployment_keeps_root_locations_and_ignores_public_prefix_header(self):
        with patch.object(app, "root_path", ""):
            async with httpx.AsyncClient(app=app, base_url="https://care.test") as client:
                response = await client.get("/api/users", headers={"x-forwarded-prefix": "/untrusted"})
                self.assertEqual(response.status_code, 307)
                self.assertEqual(response.headers["location"], "https://care.test/api/users/")
                docs = await client.get("/docs")
                self.assertIn("url: '/openapi.json'", docs.text)

    async def test_subpath_preserves_prefix_host_port_scheme_query_and_docs(self):
        with patch.object(app, "root_path", "/medical"):
            async with httpx.AsyncClient(app=app, base_url="https://care.test:8443") as client:
                response = await client.get("/api/users?role=doctor", headers={"x-forwarded-prefix": "/untrusted"})
                self.assertEqual(response.status_code, 307)
                self.assertEqual(response.headers["location"], "https://care.test:8443/medical/api/users/?role=doctor")
                docs = await client.get("/docs")
                self.assertIn("url: '/medical/openapi.json'", docs.text)
                self.assertIn("oauth2RedirectUrl: window.location.origin + '/medical/docs/oauth2-redirect'", docs.text)

    def test_deployment_prefix_validation_rejects_urls_and_traversal(self):
        for value in ("medical", "/medical/", "//medical", "/../medical", "/medical/..",
                      "/medical?query", "https://care.test/medical", "/medical%2fhidden", "/medical\\hidden"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                Settings(MEDICALASSISTANT_ROOT_PATH=value)
        self.assertEqual(Settings(MEDICALASSISTANT_ROOT_PATH="/medical").MEDICALASSISTANT_ROOT_PATH, "/medical")
        self.assertEqual(Settings(MEDICALASSISTANT_ROOT_PATH="/").MEDICALASSISTANT_ROOT_PATH, "")
