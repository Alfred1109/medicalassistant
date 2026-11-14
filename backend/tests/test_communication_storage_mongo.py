"""Opt-in tests use only disposable local databases."""
import asyncio
import os
import unittest
from uuid import uuid4
from urllib.parse import urlsplit
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient
from app.core.exceptions import AppBaseException
from app.services.communication_service import CommunicationService
from app.db.indexes import MESSAGE_IDEMPOTENCY_INDEX_NAME

@unittest.skipUnless(os.getenv('REHAB_TEST_COMMUNICATION_MONGO_URI'), 'isolated Mongo URI required')
class CommunicationStorageMongoTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        uri = os.environ['REHAB_TEST_COMMUNICATION_MONGO_URI']
        if urlsplit(uri).hostname not in {'127.0.0.1', 'localhost', '::1'}:
            raise RuntimeError('Only disposable local Mongo is allowed')
        self.mongo = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=3000)
        self.db = self.mongo['rehab_communication_storage_' + uuid4().hex]
        self.sender, self.recipient, self.cid = map(str, [ObjectId(), ObjectId(), ObjectId()])
        await self.db.users.insert_many([{'_id': ObjectId(uid), 'is_active': True, 'name': uid} for uid in (self.sender, self.recipient)])
        await self.db.conversations.insert_one({'_id': ObjectId(self.cid), 'participant1_id': self.sender, 'participant2_id': self.recipient})
    async def asyncTearDown(self):
        await self.mongo.drop_database(self.db.name)
        self.mongo.close()
    async def send(self):
        return await CommunicationService.send_message(self.db, self.cid, self.sender, 'once', client_message_id='retry-key')
    async def test_concurrent_first_writes_are_deduplicated(self):
        values = await asyncio.gather(*(self.send() for _ in range(8)))
        self.assertEqual(len({v['id'] for v in values}), 1)
        self.assertEqual(await self.db.messages.count_documents({}), 1)
        self.assertEqual(await self.db.notifications.count_documents({}), 1)
    async def test_duplicate_history_preserved_and_blocks_new_write(self):
        history = {'conversation_id': self.cid, 'sender_id': self.sender, 'client_message_id': 'old-duplicate'}
        await self.db.messages.insert_many([dict(history), dict(history)])
        with self.assertRaises(AppBaseException) as raised:
            await self.send()
        self.assertEqual(raised.exception.error_code, 'MESSAGE_STORAGE_UNAVAILABLE')
        self.assertEqual(await self.db.messages.count_documents({}), 2)
    async def test_conflicting_index_blocks_write_until_repaired(self):
        await self.db.messages.create_index('content', name=MESSAGE_IDEMPOTENCY_INDEX_NAME)
        with self.assertRaises(AppBaseException):
            await self.send()
        self.assertEqual(await self.db.messages.count_documents({}), 0)
        await self.db.messages.drop_index(MESSAGE_IDEMPOTENCY_INDEX_NAME)
        await self.send()
        self.assertEqual(await self.db.messages.count_documents({}), 1)
