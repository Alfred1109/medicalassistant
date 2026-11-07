import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from app.db import mongodb


class MongoLifecycleTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.original_client = mongodb.db.client
        self.original_db = mongodb.db.db
        self.original_lock = mongodb._connection_lock
        mongodb.db.client = None
        mongodb.db.db = None
        mongodb._connection_lock = asyncio.Lock()

    def tearDown(self):
        mongodb.db.client = self.original_client
        mongodb.db.db = self.original_db
        mongodb._connection_lock = self.original_lock

    async def test_failed_ping_does_not_publish_client_and_closes_it(self):
        candidate = MagicMock()
        candidate_db = MagicMock()
        candidate_db.command = AsyncMock(side_effect=RuntimeError("unavailable"))
        candidate.__getitem__.return_value = candidate_db
        with patch.object(mongodb, "AsyncIOMotorClient", return_value=candidate):
            with self.assertRaises(mongodb.DatabaseConnectionError):
                await mongodb.connect_to_mongodb()
        self.assertIsNone(mongodb.db.client)
        self.assertIsNone(mongodb.db.db)
        candidate.close.assert_called_once()

    async def test_existing_healthy_client_is_reused(self):
        previous, previous_db = MagicMock(), MagicMock()
        previous_db.command = AsyncMock(return_value={"ok": 1})
        mongodb.db.client, mongodb.db.db = previous, previous_db
        with patch.object(mongodb, "AsyncIOMotorClient") as factory:
            await mongodb.connect_to_mongodb()
        self.assertIs(mongodb.db.client, previous)
        self.assertIs(mongodb.db.db, previous_db)
        previous.close.assert_not_called()
        factory.assert_not_called()

    async def test_unhealthy_existing_client_is_preserved_and_fails_closed(self):
        previous, previous_db = MagicMock(), MagicMock()
        previous_db.command = AsyncMock(side_effect=OSError("down"))
        mongodb.db.client, mongodb.db.db = previous, previous_db
        with patch.object(mongodb, "AsyncIOMotorClient") as factory:
            with self.assertRaises(mongodb.DatabaseConnectionError):
                await mongodb.get_db()
        self.assertIs(mongodb.db.client, previous)
        self.assertIs(mongodb.db.db, previous_db)
        previous.close.assert_not_called()
        factory.assert_not_called()

    async def test_concurrent_initialization_publishes_one_client(self):
        candidate, candidate_db = MagicMock(), MagicMock()
        entered, release = asyncio.Event(), asyncio.Event()

        async def ping(_command):
            entered.set()
            await release.wait()
            return {"ok": 1}

        candidate_db.command = AsyncMock(side_effect=ping)
        candidate.__getitem__.return_value = candidate_db
        with patch.object(mongodb, "AsyncIOMotorClient", return_value=candidate) as factory:
            first = asyncio.create_task(mongodb.connect_to_mongodb())
            await entered.wait()
            second = asyncio.create_task(mongodb.connect_to_mongodb())
            await asyncio.sleep(0)
            release.set()
            await asyncio.gather(first, second)
        factory.assert_called_once()
        candidate.close.assert_not_called()
        self.assertIs(mongodb.db.client, candidate)

    async def test_cancelled_initialization_closes_unpublished_client(self):
        candidate, candidate_db = MagicMock(), MagicMock()
        entered = asyncio.Event()

        async def ping(_command):
            entered.set()
            await asyncio.Event().wait()

        candidate_db.command = AsyncMock(side_effect=ping)
        candidate.__getitem__.return_value = candidate_db
        with patch.object(mongodb, "AsyncIOMotorClient", return_value=candidate):
            task = asyncio.create_task(mongodb.connect_to_mongodb())
            await entered.wait()
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        candidate.close.assert_called_once()
        self.assertIsNone(mongodb.db.client)
        self.assertIsNone(mongodb.db.db)

    async def test_application_startup_propagates_connection_failure(self):
        from app import main

        with patch.object(main, "connect_to_mongodb", new=AsyncMock(
            side_effect=mongodb.DatabaseConnectionError("unavailable")
        )):
            with self.assertRaises(mongodb.DatabaseConnectionError):
                await main.startup_db_client()


if __name__ == "__main__":
    unittest.main()
