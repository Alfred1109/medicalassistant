"""Reviewed task actions remain subject to active original authorization."""
import os
import unittest
from copy import deepcopy
from uuid import uuid4
from urllib.parse import urlsplit
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient
from app.db.transactions import run_followup_transaction
from app.integrations.forms import service
import test_reviewed_fill_context as reviewed_fixture

@unittest.skipUnless(os.environ.get('REHAB_TEST_REVIEWED_FILL_MONGO_URI'), 'isolated replica set required')
class FillReviewRevocationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        uri = os.environ['REHAB_TEST_REVIEWED_FILL_MONGO_URI']
        if urlsplit(uri).hostname not in {'127.0.0.1', 'localhost', '::1'}:
            raise RuntimeError('loopback instance required')
        self.mongo = AsyncIOMotorClient(uri)
        self.db = self.mongo['fill_review_revocation_' + uuid4().hex]
        seed = reviewed_fixture.ReviewedFillContextTests()
        seed.setUp()
        seed.patient.stop()
        seed.form.stop()
        self.link, self.binding = seed.link, seed.binding
        await self.db.external_patient_links.insert_one(deepcopy(self.link))
        await self.db.external_form_bindings.insert_one(deepcopy(self.binding))
        self.task = {'patient_id': 'patient', 'remote_refs': seed.refs,
            'reviewed_context': {'patient_link_id': self.link['_id'],
                'form_binding_id': self.binding['_id'], 'reference': seed.reference,
                'version_ref': seed.version, 'purpose': 'followup'}}

    async def asyncTearDown(self):
        await self.mongo.drop_database(self.db.name)
        self.mongo.close()

    async def test_old_task_cannot_authorize_new_action(self):
        for context in (None, {}, {'patient_link_id': 'invalid'}):
            with self.assertRaises(service.FormIntegrationError):
                await service.require_task_reviewed_context(self.db, dict(self.task, reviewed_context=context))

    async def test_revoke_and_recreate_does_not_revive_old_task(self):
        await self.db.external_patient_links.update_one({}, {'$set': {'status': 'revoked'}})
        await self.db.external_patient_links.insert_one(dict(self.link, _id=ObjectId()))
        with self.assertRaises(service.FormIntegrationError):
            await service.require_task_reviewed_context(self.db, self.task)

    async def test_form_revocation_and_version_change_block_action(self):
        for fields in ({'status': 'revoked'}, {'status': 'active', 'version_ref': {'version': 2}}):
            await self.db.external_form_bindings.update_one({}, {'$set': fields})
            with self.assertRaises(service.FormIntegrationError):
                await service.require_task_reviewed_context(self.db, self.task)

    async def test_concurrent_revoke_blocks_commit_and_preserves_history(self):
        historical = {'_id': ObjectId(), 'status': 'confirmed', 'confirmation': {'response_id': 42}}
        await self.db.integration_fill_tasks.insert_one(deepcopy(historical))
        first = True
        async def approve(session):
            nonlocal first
            await self.db.external_patient_links.find_one({}, session=session)
            if first:
                first = False
                await self.db.external_patient_links.update_one({}, {'$set': {'status': 'revoked'}})
            await service.require_task_reviewed_context(self.db, self.task, session=session)
            await self.db.accepted_actions.insert_one({'accepted': True}, session=session)
        with self.assertRaises(service.FormIntegrationError):
            await run_followup_transaction(self.db, approve)
        self.assertEqual(await self.db.accepted_actions.count_documents({}), 0)
        self.assertEqual(await self.db.integration_fill_tasks.find_one({}), historical)
