"""Authentication never depends on a demo email; demo data requires an isolated DB."""
import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

from app.services.user_service import UserService
from app.schemas.user import UserUpdate
from app.tools import seed_demo


class PasswordHashTests(unittest.IsolatedAsyncioTestCase):
    async def test_preset_credentials_cannot_override_current_hash(self):
        db = MagicMock()
        db.users.update_one = AsyncMock()
        service = UserService(db)
        for _name, email, preset, _role in seed_demo.DEMO_USERS:
            with self.subTest(email=email):
                user = {"_id": ObjectId(), "email": email, "is_active": True,
                        "hashed_password": service._get_password_hash("A-different-current-password!")}
                service.get_user_by_email = AsyncMock(return_value=user)
                self.assertIsNone(await service.authenticate_user(email, preset))
                self.assertIs(await service.authenticate_user(email, "A-different-current-password!"), user)

    async def test_disabled_or_corrupt_accounts_cannot_authenticate(self):
        db = MagicMock()
        db.users.update_one = AsyncMock()
        service = UserService(db)
        user = {"_id": ObjectId(), "email": "admin@example.com", "is_active": False,
                "hashed_password": service._get_password_hash("Admin123!")}
        service.get_user_by_email = AsyncMock(return_value=user)
        with self.assertRaises(ValueError):
            await service.authenticate_user(user["email"], "Admin123!")
        db.users.update_one.assert_not_awaited()
        for invalid_hash in (None, "", "malformed", {}, 7):
            user.update(is_active=True, hashed_password=invalid_hash)
            self.assertIsNone(await service.authenticate_user(user["email"], "Admin123!"))


class DemoTargetTests(unittest.IsolatedAsyncioTestCase):
    async def test_unsafe_targets_are_rejected_before_connecting(self):
        for uri, database in (
            ("mongodb://example.com:27017", "medicalassistant_demo_test0000"),
            ("mongodb://localhost:27017", "medicalassistant_demo_test0000"),
            ("mongodb+srv://127.0.0.1", "medicalassistant_demo_test0000"),
            ("mongodb://127.0.0.1:27017/?replicaSet=prod", "medicalassistant_demo_test0000"),
            ("mongodb://127.0.0.1:27017,example.com:27017", "medicalassistant_demo_test0000"),
            ("mongodb://name:secret@127.0.0.1:27017", "medicalassistant_demo_test0000"),
            ("mongodb://127.0.0.1:0", "medicalassistant_demo_test0000"),
            ("mongodb://127.0.0.1:27017", "rehab_assistant"),
            ("mongodb://127.0.0.1:27017", "medicalassistant_demo_x"),
        ):
            with self.subTest(uri=uri, database=database), patch.object(seed_demo, "AsyncIOMotorClient") as factory:
                with self.assertRaises(ValueError):
                    await seed_demo.initialize_demo_database(uri, database)
                factory.assert_not_called()

    async def test_nonempty_target_is_not_modified(self):
        client = MagicMock()
        database = client.__getitem__.return_value
        database.command = AsyncMock()
        database.list_collection_names = AsyncMock(return_value=["patients"])
        database.create_collection = AsyncMock()
        with patch.object(seed_demo, "AsyncIOMotorClient", return_value=client):
            with self.assertRaises(ValueError):
                await seed_demo.initialize_demo_database("mongodb://127.0.0.1:37020", "medicalassistant_demo_test0000")
        database.create_collection.assert_not_awaited()
        client.close.assert_called_once()


URI = os.environ.get("MEDICALASSISTANT_AUTH_TEST_MONGO_URL")


@unittest.skipUnless(URI, "explicit isolated loopback Mongo URI required")
class RealDemoDatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.name = "medicalassistant_demo_" + uuid4().hex
        seed_demo.validate_target(URI, self.name)
        self.client = AsyncIOMotorClient(URI, directConnection=True, serverSelectionTimeoutMS=3000)
        self.db = self.client[self.name]
        await self.db.command("ping")

    async def asyncTearDown(self):
        await self.client.drop_database(self.name)
        self.client.close()

    async def test_explicit_seed_uses_hashes_and_never_resets_existing_users(self):
        self.assertEqual(await seed_demo.initialize_demo_database(URI, self.name), 5)
        service = UserService(self.db)
        for _name, email, password, _role in seed_demo.DEMO_USERS:
            user = await service.authenticate_user(email, password)
            self.assertIsNotNone(user)
            self.assertNotEqual(user["hashed_password"], password)
        admin = await service.get_user_by_email("admin@example.com")
        await service.update_user(str(admin["_id"]), UserUpdate(password="Changed-admin-password!"))
        self.assertIsNone(await service.authenticate_user("admin@example.com", "Admin123!"))
        self.assertIsNotNone(await service.authenticate_user("admin@example.com", "Changed-admin-password!"))
        snapshot = await self.db.users.find({}).to_list(length=None)
        with self.assertRaises(ValueError):
            await seed_demo.initialize_demo_database(URI, self.name)
        self.assertEqual(await self.db.users.find({}).to_list(length=None), snapshot)
        await self.db.users.update_one({"_id": admin["_id"]}, {"$set": {"is_active": False}})
        with self.assertRaises(ValueError):
            await service.authenticate_user("admin@example.com", "Changed-admin-password!")

    async def test_normal_startup_does_not_seed_any_accounts(self):
        from app import main
        from app.db import mongodb
        original_client, original_db = mongodb.db.client, mongodb.db.db
        original_lock = mongodb._connection_lock
        import asyncio
        mongodb.db.client, mongodb.db.db = self.client, self.db
        mongodb._connection_lock = asyncio.Lock()
        try:
            with patch.object(main, "setup_websockets"):
                await main.startup_db_client()
            self.assertEqual(await self.db.list_collection_names(), [])
        finally:
            mongodb.db.client, mongodb.db.db = original_client, original_db
            mongodb._connection_lock = original_lock

    async def test_existing_patient_data_prevents_seed_without_changes(self):
        await self.db.patients.insert_one({"_id": "synthetic-protected", "note": "must remain unchanged"})
        before = await self.db.patients.find({}).to_list(length=None)
        with self.assertRaises(ValueError):
            await seed_demo.initialize_demo_database(URI, self.name)
        self.assertEqual(await self.db.list_collection_names(), ["patients"])
        self.assertEqual(await self.db.patients.find({}).to_list(length=None), before)
