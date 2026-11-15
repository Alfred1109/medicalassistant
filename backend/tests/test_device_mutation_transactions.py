"""Device writes serialize with account, patient assignment and device removal."""
import asyncio
import os
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import urlsplit
from uuid import uuid4
from bson import ObjectId
from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection
from app.services.device_service import DeviceService
from app.core.patient_access import PatientAccessError

@unittest.skipUnless(os.getenv('REHAB_TEST_DEVICE_MUTATION_MONGO_URI'), 'isolated replica set required')
class DeviceMutationTransactions(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        uri = os.environ['REHAB_TEST_DEVICE_MUTATION_MONGO_URI']
        if urlsplit(uri).hostname not in {'127.0.0.1', 'localhost', '::1'}:
            raise RuntimeError('Only disposable local Mongo databases are allowed')
        self.mongo = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=3000)
        self.db = self.mongo['rehab_device_mutation_' + uuid4().hex]
        self.pid, self.did = ObjectId(), ObjectId()
        self.actor = SimpleNamespace(id=str(ObjectId()), role='doctor')
        await self.db.users.insert_many([
            {'_id': ObjectId(self.actor.id), 'role': 'doctor', 'is_active': True},
            {'_id': self.pid, 'role': 'patient', 'is_active': True, 'practitioners': [self.actor.id]}])
        await self.db.devices.insert_one({'_id': self.did, 'patient_id': str(self.pid), 'status': 'active', 'settings': {'old': 'kept'}})
        self.service = DeviceService(self.db)
    async def asyncTearDown(self):
        await self.mongo.drop_database(self.db.name)
        self.mongo.close()
    async def reading(self):
        return await self.service.record_manual_reading(str(self.did), 'synthetic', '1', 'unit', datetime.utcnow(), actor=self.actor)
    async def paused_mutation(self, operation, collection_name, identifier, revoke):
        original = AsyncIOMotorCollection.update_one
        reached, proceed = asyncio.Event(), asyncio.Event()
        paused = False
        async def intercept(collection, query, update, **kwargs):
            nonlocal paused
            if not paused and collection.name == collection_name and query.get('_id') == identifier:
                paused = True; reached.set()
                await asyncio.wait_for(proceed.wait(), 5)
            return await original(collection, query, update, **kwargs)
        with patch.object(AsyncIOMotorCollection, 'update_one', intercept):
            task = asyncio.create_task(operation())
            try:
                await asyncio.wait_for(reached.wait(), 5)
                await revoke(original)
            finally:
                proceed.set()
            with self.assertRaises((HTTPException, PatientAccessError)) as raised:
                await task
            self.assertIn(raised.exception.status_code, {403, 404, 409})
    async def test_assignment_removed_during_manual_reading_rejects_write(self):
        async def revoke(original):
            await original(self.db.users, {'_id': self.pid}, {'$set': {'practitioners': []}})
        await self.paused_mutation(self.reading, 'users', self.pid, revoke)
        self.assertEqual(await self.db.device_data.count_documents({}), 0)
        self.assertEqual(await self.db.health_data.count_documents({}), 0)
    async def test_device_removed_during_manual_reading_rejects_write(self):
        async def revoke(original):
            await original(self.db.devices, {'_id': self.did}, {'$set': {'status': 'deleted'}})
        await self.paused_mutation(self.reading, 'devices', self.did, revoke)
        self.assertEqual(await self.db.device_data.count_documents({}), 0)
        self.assertEqual(await self.db.health_data.count_documents({}), 0)
    async def test_account_disabled_during_configure_rolls_back(self):
        async def operation():
            return await self.service.configure_device(str(self.did), {'new': 'blocked'}, actor=self.actor)
        async def revoke(original):
            await original(self.db.users, {'_id': ObjectId(self.actor.id)}, {'$set': {'is_active': False}})
        await self.paused_mutation(operation, 'users', ObjectId(self.actor.id), revoke)
        device = await self.db.devices.find_one({'_id': self.did})
        self.assertEqual(device['settings'], {'old': 'kept'})
    async def test_concurrent_config_merges_distinct_keys_and_preserves_manual_source(self):
        await asyncio.gather(*(self.service.configure_device(str(self.did), {key: True}, actor=self.actor) for key in ('a', 'b')))
        row = await self.db.devices.find_one({'_id': self.did})
        self.assertEqual(row['settings'], {'old': 'kept', 'a': True, 'b': True})
        reading = await self.reading()
        self.assertEqual(reading['metadata']['source'], '手工登记')
        self.assertEqual(reading['metadata']['recorded_by'], self.actor.id)
        self.assertNotIn('last_connected', row)
    async def test_new_registration_does_not_claim_a_real_connection(self):
        row = await self.service.bind_device(str(self.pid), {'device_type': '血压计', 'name': 'synthetic'}, actor=self.actor)
        self.assertIsNone(row['last_connected'])
        status = await self.service.get_device_status(row['_id'])
        self.assertEqual(status['status'], 'offline')
    async def test_health_manager_reading_allowed_but_configuration_rejected(self):
        manager = SimpleNamespace(id=str(ObjectId()), role='health_manager')
        await self.db.users.insert_one({'_id': ObjectId(manager.id), 'role': manager.role, 'is_active': True})
        await self.db.users.update_one({'_id': self.pid}, {'$set': {'health_managers': [manager.id]}})
        with self.assertRaises(HTTPException) as raised:
            await self.service.configure_device(str(self.did), {'forbidden': True}, actor=manager)
        self.assertEqual(raised.exception.status_code, 403)
        await self.service.record_manual_reading(str(self.did), 'synthetic', '1', 'unit', datetime.utcnow(), actor=manager)
        self.assertEqual(await self.db.device_data.count_documents({}), 1)
