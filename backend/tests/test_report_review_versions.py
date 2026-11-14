"""A report review attests one immutable content revision."""
import asyncio
import os
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from urllib.parse import urlsplit
from uuid import uuid4
from unittest.mock import patch, AsyncMock
from motor.motor_asyncio import AsyncIOMotorCollection
from bson import ObjectId
from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorClient
from app.clinical import workspace as clinical


@unittest.skipUnless(os.environ.get('REHAB_TEST_REPORT_MONGO_URI'), 'isolated local Mongo URI required')
class ReportReviewVersions(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        uri = os.environ['REHAB_TEST_REPORT_MONGO_URI']
        if urlsplit(uri).hostname not in {'127.0.0.1', 'localhost', '::1'}:
            raise RuntimeError('Only local disposable test databases are allowed')
        self.mongo = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=3000)
        self.db = self.mongo['rehab_report_review_' + uuid4().hex]
        self.pid = str(ObjectId())
        self.actor = SimpleNamespace(id=str(ObjectId()), role='doctor')
        await self.db.users.insert_many([{'_id': ObjectId(self.pid), 'role': 'patient', 'practitioners': [self.actor.id]}, {'_id': ObjectId(self.actor.id), 'role': 'doctor', 'is_active': True}])
        with patch.object(clinical, '_report_excerpt', AsyncMock(return_value=(None, None))):
            self.report = await clinical.add_report(self.db, self.actor, self.pid, filename='synthetic.pdf', content_type='application/pdf', content=b'synthetic', report_date='2026-11-14', stated_patient_id=self.pid)
    async def asyncTearDown(self):
        await self.mongo.drop_database(self.db.name)
        self.mongo.close()
    async def add(self, value, version):
        return await clinical.add_finding(self.db, self.actor, self.report['id'], '指标', value, 'unit', expected_version=version)
    async def test_new_content_requires_review_and_keeps_old_attestation(self):
        await self.add('1', 0)
        reviewed = await clinical.review_report(self.db, self.actor, self.report['id'], accepted=True, note='reviewed original', expected_version=1)
        self.assertTrue(reviewed['review_current'])
        changed = await self.add('2', 2)
        self.assertEqual(changed['review_status'], 'pending')
        row = await self.db.clinical_reports.find_one({'_id': ObjectId(self.report['id'])})
        self.assertIsNone(clinical._reviewed_findings(row))
        self.assertEqual(row['content_history'][-1]['review']['reviewed_snapshot']['findings'][0]['value'], '1')
        self.assertEqual(row['review_history'][0]['note'], 'reviewed original')
        self.assertFalse((await clinical.recorded_plan_sources(self.db, self.actor, self.pid))['description'].find('已审核指标') >= 0)
        await clinical.review_report(self.db, self.actor, self.report['id'], accepted=True, note='reviewed revision', expected_version=3)
        row = await self.db.clinical_reports.find_one({'_id': row['_id']})
        self.assertEqual([x['value'] for x in clinical._reviewed_findings(row)], ['1', '2'])
    async def test_concurrent_edits_one_wins_and_stale_review_is_rejected(self):
        results = await asyncio.gather(self.add('a', 0), self.add('b', 0), return_exceptions=True)
        self.assertEqual(sum(isinstance(x, HTTPException) and x.status_code == 409 for x in results), 1)
        row = await self.db.clinical_reports.find_one({'_id': ObjectId(self.report['id'])})
        self.assertEqual(len(row['findings']), 1)
        with self.assertRaises(HTTPException) as raised:
            await clinical.review_report(self.db, self.actor, self.report['id'], accepted=True, note='stale', expected_version=0)
        self.assertEqual(raised.exception.status_code, 409)
    async def test_authorization_revoked_during_approval_rolls_back(self):
        await self.add('1', 0)
        reached, proceed = asyncio.Event(), asyncio.Event()
        original = AsyncIOMotorCollection.update_one
        paused = False
        async def intercept(collection, query, update, **kwargs):
            nonlocal paused
            if collection.name == 'users' and query.get('_id') == ObjectId(self.pid) and not paused:
                paused = True
                reached.set()
                await asyncio.wait_for(proceed.wait(), 5)
            return await original(collection, query, update, **kwargs)
        with patch.object(AsyncIOMotorCollection, 'update_one', intercept):
            review = asyncio.create_task(clinical.review_report(self.db, self.actor, self.report['id'], accepted=True, note='checked', expected_version=1))
            try:
                await asyncio.wait_for(reached.wait(), 5)
                await original(self.db.users, {'_id': ObjectId(self.pid)}, {'$set': {'practitioners': []}})
            finally:
                proceed.set()
            with self.assertRaises(HTTPException) as raised:
                await review
            self.assertEqual(raised.exception.status_code, 403)
        row = await self.db.clinical_reports.find_one({'_id': ObjectId(self.report['id'])})
        self.assertEqual(row['review_status'], 'pending')
        self.assertEqual(row['mutation_version'], 1)
        self.assertIsNone(clinical._reviewed_findings(row))

    async def test_account_disabled_during_edit_rolls_back(self):
        reached, proceed = asyncio.Event(), asyncio.Event()
        original = AsyncIOMotorCollection.update_one
        paused = False
        async def intercept(collection, query, update, **kwargs):
            nonlocal paused
            if collection.name == 'users' and query.get('_id') == ObjectId(self.actor.id) and not paused:
                paused = True
                reached.set()
                await asyncio.wait_for(proceed.wait(), 5)
            return await original(collection, query, update, **kwargs)
        with patch.object(AsyncIOMotorCollection, 'update_one', intercept):
            edit = asyncio.create_task(self.add('1', 0))
            try:
                await asyncio.wait_for(reached.wait(), 5)
                await original(self.db.users, {'_id': ObjectId(self.actor.id)}, {'$set': {'is_active': False}})
            finally:
                proceed.set()
            with self.assertRaises(HTTPException) as raised:
                await edit
            self.assertEqual(raised.exception.status_code, 403)
        row = await self.db.clinical_reports.find_one({'_id': ObjectId(self.report['id'])})
        self.assertEqual(row['findings'], [])
        self.assertEqual(row['mutation_version'], 0)

    async def test_legacy_review_is_not_automatically_trusted(self):
        oid = ObjectId(self.report['id'])
        await self.db.clinical_reports.update_one({'_id': oid}, {'$set': {'review_status': 'reviewed', 'review_note': 'legacy', 'findings': [{'label': 'old', 'value': '5'}]}, '$unset': {'mutation_version': '', 'content_revision': ''}})
        row = await self.db.clinical_reports.find_one({'_id': oid})
        self.assertIsNone(clinical._reviewed_findings(row))
        reviewed = await clinical.review_report(self.db, self.actor, self.report['id'], accepted=True, note='explicitly rechecked', expected_version=0)
        self.assertTrue(reviewed['review_current'])
        row = await self.db.clinical_reports.find_one({'_id': oid})
        self.assertEqual(row['legacy_review']['review_note'], 'legacy')

class ReportPatientVisibility(unittest.TestCase):
    def test_legacy_and_changed_content_are_not_patient_approved(self):
        row = {'_id': ObjectId(), 'patient_id': 'patient', 'filename': 'test.pdf', 'report_date': '2026-11-14',
               'content_type': 'application/pdf', 'size': 4, 'sha256': 'hash', 'review_status': 'reviewed',
               'review_note': 'old approval', 'findings': [{'label': 'secret-unreviewed', 'value': '5'}]}
        actor = SimpleNamespace(role='patient')
        self.assertFalse(clinical._show_findings(actor, row))
        result = clinical._report_public(row, include_findings=clinical._show_findings(actor, row))
        self.assertEqual(result['findings'], [])
        self.assertNotIn('review_history', result)
        clinical_view = clinical._report_public(row, include_findings=True, include_history=True)
        self.assertEqual(clinical_view['review_history'][0]['note'], 'old approval')
        row.update(content_revision=1, reviewed_content_revision=1, reviewed_snapshot=clinical._content_snapshot(row))
        self.assertTrue(clinical._show_findings(actor, row))
        row['findings'] = [{'label': 'changed', 'value': '9'}]
        self.assertFalse(clinical._show_findings(actor, row))
