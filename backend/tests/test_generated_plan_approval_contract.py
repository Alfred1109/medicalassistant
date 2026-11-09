"""Generated-plan persistence and atomic approval, without LLM or external data."""
from copy import deepcopy
from datetime import datetime, timedelta
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock
from bson import ObjectId
from fastapi import FastAPI
import httpx
from pymongo.errors import AutoReconnect
from app.api.routers.rehabilitation_router import router
from app.core.auth import get_current_active_user
from app.core.dependencies import get_database, get_rehabilitation_service
from app.core.exceptions import AppBaseException
from app.schemas.rehabilitation import GeneratedPlanEdits, RehabPlanUpdate
from app.services.rehabilitation_service import RehabilitationService

class Plans:
    def __init__(self, doc=None):
        self.doc = deepcopy(doc)
        self.writes = 0
        self.before_update = None
        self.insert_error = None
    async def find_one(self, query):
        return deepcopy(self.doc)
    async def insert_one(self, doc):
        if self.insert_error:
            raise self.insert_error
        self.doc = deepcopy(doc)
        self.doc['_id'] = ObjectId()
        return SimpleNamespace(inserted_id=self.doc['_id'])
    async def find_one_and_update(self, query, update, **kwargs):
        if self.before_update:
            self.before_update(self.doc)
        if any(self.doc.get(key) != value for key, value in query.items()):
            return None
        self.writes += 1
        self.doc.update(deepcopy(update['$set']))
        for key, amount in update.get('$inc', {}).items():
            self.doc[key] = self.doc.get(key, 0) + amount
        return deepcopy(self.doc)
    async def update_one(self, query, update):
        if self.before_update:
            self.before_update(self.doc)
        if any(self.doc.get(key) != value for key, value in query.items()):
            return SimpleNamespace(matched_count=0, modified_count=0)
        self.writes += 1
        self.doc.update(deepcopy(update['$set']))
        for key, amount in update.get('$inc', {}).items():
            self.doc[key] = self.doc.get(key, 0) + amount
        return SimpleNamespace(matched_count=1, modified_count=1)

def make_service(doc=None):
    plans = Plans(doc)
    db = SimpleNamespace(rehab_plans=plans, exercises=None, rehab_assessments=None, agents=None)
    return RehabilitationService(db), plans

def draft():
    return {'_id': ObjectId(), 'patient_id': str(ObjectId()), 'status': 'draft',
            'name': 'synthetic', 'updated_at': datetime(2026, 11, 8),
            'metadata': {'generated_by': 'llm', 'approval_history': []}}

class GeneratedPlanApprovalTests(unittest.IsolatedAsyncioTestCase):
    async def test_ordinary_update_cannot_bypass_generated_approval_or_erase_marker(self):
        for source in ('legacy', 'top_level'):
            doc = draft()
            if source == 'top_level':
                doc['generation_source'] = 'llm'
                doc['metadata'].pop('generated_by')
            for update in (
                {'status': 'active'}, {'metadata': None},
                {'metadata': {'generated_by': 'manual'}},
                {'metadata': {'is_approved': True}},
                {'metadata': {'approval_history': [{'status': 'approved'}]}},
                {'metadata': {'approval_timestamp': 'forged'}},
            ):
                with self.subTest(source=source, update=update):
                    service, plans = make_service(doc)
                    with self.assertRaises(AppBaseException) as error:
                        await service.update_rehab_plan(str(doc['_id']), RehabPlanUpdate(**update))
                    self.assertEqual(error.exception.status_code, 409)
                    self.assertEqual(plans.writes, 0)
            service, plans = make_service(doc)
            updated = await service.update_rehab_plan(str(doc['_id']),
                            RehabPlanUpdate(metadata={'local_note': 'editable'}))
            self.assertEqual(updated['metadata']['local_note'], 'editable')
            for key, value in doc['metadata'].items():
                self.assertEqual(updated['metadata'][key], value)
            self.assertTrue(service._is_generated_plan(updated))
            with self.assertRaises(AppBaseException):
                await service.update_rehab_plan(str(doc['_id']), RehabPlanUpdate(status='active'))

    async def test_generated_update_conflicts_with_concurrent_approval(self):
        doc = draft()
        service, plans = make_service(doc)
        plans.before_update = lambda current: current.update(status='active')
        with self.assertRaises(AppBaseException) as error:
            await service.update_rehab_plan(str(doc['_id']), RehabPlanUpdate(name='edited'))
        self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(plans.writes, 0)

    async def test_ordinary_manual_plan_status_and_metadata_edit_remain_available(self):
        doc = draft()
        doc['metadata'] = {'custom': 'existing'}
        service, plans = make_service(doc)
        updated = await service.update_rehab_plan(str(doc['_id']),
                    RehabPlanUpdate(status='completed', metadata={'custom': 'updated'}))
        self.assertEqual(updated['status'], 'completed')
        self.assertEqual(updated['metadata'], {'custom': 'updated'})

    async def test_published_and_withdrawn_plans_cannot_change_status_through_legacy_update(self):
        for status in ('cancelled', 'archived', 'active'):
            doc = draft()
            doc.update(status='draft', metadata={}, has_publication_history=True,
                       published_version_id=None, publication_revision=2)
            service, plans = make_service(doc)
            with self.assertRaises(AppBaseException) as error:
                await service.update_rehab_plan(str(doc['_id']), RehabPlanUpdate(status=status))
            self.assertEqual(error.exception.status_code, 409)
            self.assertEqual(plans.writes, 0)

    async def test_publication_racing_legacy_status_update_cannot_be_overwritten(self):
        doc = draft()
        doc['metadata'] = {}
        service, plans = make_service(doc)
        plans.before_update = lambda current: current.update(has_publication_history=True,
            published_version_id=str(ObjectId()), publication_revision=1, _publication_fence=1)
        with self.assertRaises(AppBaseException) as error:
            await service.update_rehab_plan(str(doc['_id']), RehabPlanUpdate(status='cancelled'))
        self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(plans.writes, 0)

    async def test_database_read_and_approval_write_failure_are_explicit(self):
        doc = draft()
        service, plans = make_service(doc)
        plans.find_one = AsyncMock(side_effect=AutoReconnect('unavailable'))
        with self.assertRaises(AppBaseException) as error:
            await service.get_rehab_plan(str(doc['_id']))
        self.assertEqual(error.exception.status_code, 503)
        plans.find_one = AsyncMock(return_value=doc)
        plans.find_one_and_update = AsyncMock(side_effect=AutoReconnect('unavailable'))
        with self.assertRaises(AppBaseException) as error:
            await service.approve_generated_plan(str(doc['_id']), GeneratedPlanEdits(),
                        approved_by='doctor', patient_id=doc['patient_id'])
        self.assertEqual(error.exception.status_code, 503)
        self.assertEqual(plans.doc['status'], 'draft')

    async def test_malformed_approval_history_is_not_overwritten(self):
        for metadata in ('invalid', {'approval_history': 'invalid'}):
            doc = draft()
            doc['metadata'] = metadata
            service, plans = make_service(doc)
            with self.assertRaises(AppBaseException) as error:
                await service.approve_generated_plan(str(doc['_id']), GeneratedPlanEdits(),
                            approved_by='doctor', patient_id=doc['patient_id'])
            self.assertEqual(error.exception.status_code, 409)
            self.assertEqual(plans.writes, 0)

    async def test_database_save_failure_never_returns_temporary_plan(self):
        service, plans = make_service()
        service.agent_service.generate_rehab_plan = AsyncMock(return_value={'name': 'synthetic'})
        plans.insert_error = AutoReconnect('synthetic unavailable')
        with self.assertRaises(AppBaseException) as error:
            await service.generate_rehab_plan_with_llm('patient', 'synthetic', 'synthetic', 'synthetic')
        self.assertEqual(error.exception.status_code, 503)
        self.assertEqual(error.exception.error_code, 'REHAB_PLAN_SAVE_FAILED')
        self.assertIsNone(plans.doc)
    async def test_approval_updates_content_evidence_and_state_once(self):
        doc = draft()
        service, plans = make_service(doc)
        result = await service.approve_generated_plan(str(doc['_id']), GeneratedPlanEdits(name='edited'),
                    approved_by='doctor', patient_id=doc['patient_id'], expected_updated_at=doc['updated_at'])
        self.assertEqual(result['name'], 'edited')
        self.assertEqual(result['status'], 'active')
        self.assertEqual(plans.writes, 1)
        self.assertEqual(plans.doc['_id'], doc['_id'])
        self.assertEqual(plans.doc['patient_id'], doc['patient_id'])
        self.assertEqual(plans.doc['metadata']['approved_by'], 'doctor')
        self.assertEqual(len(plans.doc['metadata']['approval_history']), 1)
        with self.assertRaises(AppBaseException):
            await service.approve_generated_plan(str(doc['_id']), GeneratedPlanEdits(),
                         approved_by='doctor', patient_id=doc['patient_id'])
        self.assertEqual(plans.writes, 1)
    async def test_concurrent_change_and_stale_snapshot_conflict(self):
        for change in ('patient_id', 'status', 'updated_at'):
            with self.subTest(change=change):
                doc = draft()
                service, plans = make_service(doc)
                plans.before_update = lambda current: current.update({change: 'changed'})
                with self.assertRaises(AppBaseException) as error:
                    await service.approve_generated_plan(str(doc['_id']), GeneratedPlanEdits(name='edited'),
                                approved_by='doctor', patient_id=doc['patient_id'])
                self.assertEqual(error.exception.status_code, 409)
                self.assertEqual(plans.writes, 0)
        doc = draft()
        service, plans = make_service(doc)
        with self.assertRaises(AppBaseException):
            await service.approve_generated_plan(str(doc['_id']), GeneratedPlanEdits(), approved_by='doctor',
                patient_id=doc['patient_id'], expected_updated_at=doc['updated_at'] - timedelta(seconds=1))
        self.assertEqual(plans.writes, 0)
    async def test_legacy_draft_without_timestamps_or_history_is_approvable(self):
        doc = draft()
        del doc['updated_at']
        doc['metadata'] = {'generated_by': 'llm'}
        service, plans = make_service(doc)
        result = await service.approve_generated_plan(str(doc['_id']), GeneratedPlanEdits(),
                    approved_by='doctor', patient_id=doc['patient_id'])
        self.assertEqual(result['status'], 'active')
        self.assertEqual(len(result['metadata']['approval_history']), 1)

class ApprovalRouteTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.doc = draft()
        self.service, self.plans = make_service(self.doc)
        self.actor = SimpleNamespace(id='doctor', role='doctor')
        self.db = SimpleNamespace(users=SimpleNamespace(find_one=AsyncMock(return_value={
            '_id': ObjectId(self.doc['patient_id']), 'role': 'patient', 'practitioners': ['doctor']})))
        self.app = FastAPI()
        self.app.include_router(router, prefix='/rehabilitation')
        self.app.dependency_overrides[get_current_active_user] = lambda: self.actor
        self.app.dependency_overrides[get_database] = lambda: self.db
        self.app.dependency_overrides[get_rehabilitation_service] = lambda: self.service
        @self.app.exception_handler(AppBaseException)
        async def handler(request, exc):
            from fastapi.responses import JSONResponse
            return JSONResponse(status_code=exc.status_code, content=exc.to_dict())
        self.client = httpx.AsyncClient(app=self.app, base_url='http://test')
        self.path = f'/rehabilitation/plans/{self.doc["_id"]}/approve'
    async def asyncTearDown(self):
        await self.client.aclose()
    async def test_nested_request_matches_actual_frontend_and_records_actor(self):
        response = await self.client.post(self.path, json={'modifications': {'name': 'edited'},
                    'expected_updated_at': self.doc['updated_at'].isoformat()})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['name'], 'edited')
        self.assertEqual(response.json()['metadata']['approved_by'], 'doctor')
    async def test_identity_status_and_metadata_injection_rejected(self):
        for key, value in (('_id', str(ObjectId())), ('patient_id', 'other'), ('status', 'active'),
                           ('metadata', {'is_approved': True}), ('$set', {'status': 'active'})):
            response = await self.client.post(self.path, json={'modifications': {key: value}})
            self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(self.plans.writes, 0)
    async def test_ordinary_put_cannot_activate_or_forge_review_of_generated_plan(self):
        path = self.path.removesuffix('/approve')
        for payload in ({'status': 'active'}, {'metadata': {'is_approved': True}},
                        {'metadata': {'generated_by': 'manual'}}):
            response = await self.client.put(path, json=payload)
            self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(self.plans.writes, 0)
    async def test_non_medical_and_unassigned_operator_cannot_approve(self):
        self.actor.role = 'patient'
        response = await self.client.post(self.path, json={})
        self.assertEqual(response.status_code, 403)
        self.actor.role = 'doctor'
        self.db.users.find_one.return_value['practitioners'] = []
        response = await self.client.post(self.path, json={})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.plans.writes, 0)

import asyncio
import os
from uuid import uuid4
from motor.motor_asyncio import AsyncIOMotorClient

REPLICA_URI = os.environ.get('REHAB_TEST_REPLICA_URI')

@unittest.skipUnless(REPLICA_URI, 'set isolated REHAB_TEST_REPLICA_URI')
class GeneratedPlanMongoApprovalTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.assertTrue(REPLICA_URI.startswith(('mongodb://127.0.0.1:', 'mongodb://localhost:')))
        self.client = AsyncIOMotorClient(REPLICA_URI, serverSelectionTimeoutMS=3000)
        self.db = self.client['rehab_approval_' + uuid4().hex]
        self.service = RehabilitationService(self.db)
    async def asyncTearDown(self):
        await self.client.drop_database(self.db.name)
        self.client.close()
    async def test_generation_json_time_roundtrip_and_parallel_approval(self):
        self.service.agent_service.generate_rehab_plan = AsyncMock(return_value={
            'name': 'synthetic', 'metadata': {'generated_by': 'llm', 'approval_history': []}})
        generated = await self.service.generate_rehab_plan_with_llm('patient', 'synthetic', 'test', 'test')
        wire_time = datetime.fromisoformat(generated['updated_at'].isoformat())
        results = await asyncio.gather(*[
            self.service.approve_generated_plan(generated['_id'], GeneratedPlanEdits(name='reviewed'),
                approved_by=f'doctor-{i}', patient_id='patient', expected_updated_at=wire_time)
            for i in range(8)], return_exceptions=True)
        self.assertEqual(sum(isinstance(result, dict) for result in results), 1)
        self.assertEqual(sum(isinstance(result, AppBaseException) and result.status_code == 409
                             for result in results), 7)
        stored = await self.db.rehab_plans.find_one({'_id': ObjectId(generated['_id'])})
        self.assertEqual(stored['status'], 'active')
        self.assertEqual(len(stored['metadata']['approval_history']), 1)
        self.assertEqual(stored['name'], 'reviewed')

    async def test_revision_rejects_stale_content_even_with_identical_millisecond_time(self):
        doc = draft()
        doc.update(content_revision=0, generation_source='llm')
        await self.db.rehab_plans.insert_one(doc)
        await self.db.rehab_plans.update_one({'_id': doc['_id']},
            {'$set': {'name': 'concurrent edit'}, '$inc': {'content_revision': 1}})
        with self.assertRaises(AppBaseException) as error:
            await self.service.approve_generated_plan(str(doc['_id']), GeneratedPlanEdits(name='stale'),
                approved_by='doctor', patient_id=doc['patient_id'],
                expected_updated_at=doc['updated_at'], expected_revision=0)
        self.assertEqual(error.exception.status_code, 409)
        stored = await self.db.rehab_plans.find_one({'_id': doc['_id']})
        self.assertEqual(stored['status'], 'draft')
        self.assertEqual(stored['name'], 'concurrent edit')
