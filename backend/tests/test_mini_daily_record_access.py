"""Exact Mini Bearer route scope for patient-owned daily-record writes."""
import unittest

from app.integrations.identity.access import mini_bearer_route


class MiniDailyRecordAccessTests(unittest.TestCase):
    def test_read_and_create_routes_remain_available(self):
        self.assertTrue(mini_bearer_route("GET", "/api/patients/daily-records"))
        self.assertTrue(mini_bearer_route("POST", "/api/patients/daily-records"))

    def test_update_and_delete_allow_only_typed_record_ids(self):
        object_id = "0123456789abcdef01234567"
        for prefix, value in (("object", object_id), ("string", "legacy-record_1"), ("string", "旧记录 1:2")):
            path = f"/api/patients/daily-records/{prefix}:{value}"
            self.assertTrue(mini_bearer_route("PUT", path))
            self.assertTrue(mini_bearer_route("DELETE", path))

    def test_rejects_other_methods_malformed_ids_and_neighboring_routes(self):
        base = "/api/patients/daily-records"
        for method in ("GET", "POST", "PATCH"):
            self.assertFalse(mini_bearer_route(method, base + "/object:0123456789abcdef01234567"))
        for method in ("PUT", "DELETE"):
            self.assertFalse(mini_bearer_route(method, base + "/object:not-an-object-id"))
            self.assertFalse(mini_bearer_route(method, base + "/string:bad/id"))
            self.assertFalse(mini_bearer_route(method, base + "/object:0123456789abcdef01234567/extra"))
            self.assertFalse(mini_bearer_route(method, "/api/patients/daily-records/../users/me"))

    def test_followup_detail_is_get_only_and_requires_one_object_id(self):
        path = "/api/health-records/followups/0123456789abcdef01234567"
        self.assertTrue(mini_bearer_route("GET", path))
        for method in ("POST", "PUT", "DELETE"):
            self.assertFalse(mini_bearer_route(method, path))
        self.assertFalse(mini_bearer_route("GET", path + "/extra"))
        self.assertFalse(mini_bearer_route("GET", "/api/health-records/followups/not-an-id"))

    def test_conversation_detail_allows_only_exact_get(self):
        path = "/api/communications/conversations/0123456789abcdef01234567"
        self.assertTrue(mini_bearer_route("GET", path))
        for method in ("POST", "PUT", "DELETE"):
            self.assertFalse(mini_bearer_route(method, path))
        self.assertFalse(mini_bearer_route("GET", path + "/extra"))

    def test_patient_self_confirmation_is_exact_post_only(self):
        path = "/api/integrations/forms/patient-self/tasks/0123456789abcdef01234567/confirm"
        self.assertTrue(mini_bearer_route("POST", path))
        self.assertFalse(mini_bearer_route("GET", path))
        self.assertFalse(mini_bearer_route("POST", path + "/extra"))


if __name__ == "__main__":
    unittest.main()
