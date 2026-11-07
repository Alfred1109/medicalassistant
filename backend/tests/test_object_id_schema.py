"""ObjectId boundaries and the real application OpenAPI must work under Pydantic v2."""
import json
import unittest
from datetime import datetime, timezone

import httpx
from bson import ObjectId
from pydantic import TypeAdapter, ValidationError

from app.main import app
from app.schemas.base import PyObjectId
from app.schemas.health_record import (
    FollowUpRecordDB, FollowUpTemplate, HealthDataDB,
    HealthRecordAttachment, HealthRecordDB,
)


class ObjectIdSchemaTests(unittest.TestCase):
    def setUp(self):
        self.adapter = TypeAdapter(PyObjectId)

    def test_python_and_json_inputs_share_strict_string_contract(self):
        value = ObjectId()
        for candidate in (value, str(value), str(value).upper()):
            parsed = self.adapter.validate_python(candidate)
            self.assertIsInstance(parsed, str)
            self.assertEqual(str(parsed), str(candidate))
            self.assertEqual(self.adapter.dump_json(parsed), json.dumps(str(candidate)).encode())
        self.assertEqual(self.adapter.validate_json(json.dumps(str(value))), str(value))
        for candidate in (None, True, 1234, b"123456789012", "", "f" * 23, "g" * 24, {}, []):
            with self.subTest(candidate=repr(candidate)):
                with self.assertRaises(ValidationError):
                    self.adapter.validate_python(candidate)
                if not isinstance(candidate, bytes):
                    with self.assertRaises(ValidationError):
                        self.adapter.validate_json(json.dumps(candidate))

    def test_direct_factory_creates_valid_distinct_ids_but_null_is_not_a_default(self):
        first, second = PyObjectId(), PyObjectId()
        self.assertTrue(ObjectId.is_valid(first))
        self.assertNotEqual(first, second)
        with self.assertRaises(ValueError):
            PyObjectId(None)

    def model_examples(self):
        return [
            (HealthRecordAttachment, dict(filename="synthetic.txt", file_type="text/plain", file_size=1,
                                         file_url="/synthetic", uploaded_by="synthetic-actor")),
            (HealthRecordDB, dict(patient_id="synthetic-patient", record_type="note", title="Test",
                                 content="Synthetic", created_by="synthetic-actor")),
            (FollowUpTemplate, dict(name="Synthetic", follow_up_type="test", created_by="synthetic-actor")),
            (FollowUpRecordDB, dict(patient_id="synthetic-patient", follow_up_type="test",
                                    scheduled_date=datetime.now(timezone.utc), provider_id="synthetic-provider",
                                    description="Synthetic", created_by="synthetic-actor")),
            (HealthDataDB, dict(patient_id="synthetic-patient", data_type="test", data_content={})),
        ]

    def test_all_calling_models_accept_bson_ids_and_serialize_aliases(self):
        for model, fields in self.model_examples():
            with self.subTest(model=model.__name__):
                default = model(**fields)
                self.assertTrue(ObjectId.is_valid(default.id))
                value = ObjectId()
                record = model(**fields, _id=value)
                self.assertEqual(record.id, str(value))
                dumped = record.model_dump(mode="json", by_alias=True)
                self.assertEqual(dumped["_id"], str(value))
                self.assertEqual(model.model_validate_json(record.model_dump_json(by_alias=True)).id, str(value))
                with self.assertRaises(ValidationError):
                    model(**fields, _id=None)
                schema = model.model_json_schema()
                self.assertEqual(schema["properties"]["_id"]["type"], "string")
                self.assertIn("pattern", schema["properties"]["_id"])


class ApplicationOpenAPITests(unittest.IsolatedAsyncioTestCase):
    async def test_real_application_generates_and_serves_complete_openapi_without_database(self):
        previous = app.openapi_schema
        app.openapi_schema = None
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/openapi.json")
            self.assertEqual(response.status_code, 200)
            schema = response.json()
            self.assertIn("/api/users/me", schema["paths"])
            self.assertIn("/api/health-records", schema["paths"])
            attachment = schema["components"]["schemas"]["HealthRecordAttachment"]
            self.assertEqual(attachment["properties"]["_id"]["type"], "string")
            self.assertEqual(app.openapi(), schema)
        finally:
            app.openapi_schema = previous
