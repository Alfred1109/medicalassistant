"""Reviewed source selectors cannot be replaced by client-supplied identities."""
import unittest
from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from bson import ObjectId
from app.integrations.forms import service


class ReviewedFillContextTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.reference = dict(project_id=1, center_id=2, subject_id=3, patient_id=9,
                              patient_archive_id=10, source=dict(system='form-platform-11344', environment='pilot'))
        self.version = dict(form_id=4, family_id=4, version=1, version_state='current', definition_sha256='a'*64)
        review = dict(verified_by='reviewer', verified_at=datetime.now(timezone.utc), evidence_reference='review-1')
        self.link = dict(_id=ObjectId(), local_patient_id='patient', status='verified', source_origin='https://source.example',
                         reference=deepcopy(self.reference), references=[deepcopy(self.reference)], **review)
        self.binding = dict(_id=ObjectId(), project_id=1, form_id=4, version=1, version_ref=deepcopy(self.version),
                            source=deepcopy(self.reference['source']), status='active', purpose='followup',
                            source_origin='https://source.example', **review)
        self.db = SimpleNamespace(external_patient_links=SimpleNamespace(find_one=AsyncMock(return_value=self.link), update_one=AsyncMock(return_value=SimpleNamespace(matched_count=1))),
                                  external_form_bindings=SimpleNamespace(find_one=AsyncMock(return_value=self.binding), update_one=AsyncMock(return_value=SimpleNamespace(matched_count=1))))
        self.client = SimpleNamespace(source_origin='https://source.example')
        self.refs = dict(project_id=1, center_id=2, subject_id=3, questionnaire_id=4)
        self.payload = dict(form_binding_id=str(self.binding['_id']), form_purpose='followup')
        self.patient = patch('app.integrations.forms.catalog_service.patient_reference', AsyncMock(return_value=deepcopy(self.reference)))
        self.form = patch('app.integrations.forms.catalog_service.form_version', AsyncMock(return_value=dict(source=deepcopy(self.reference['source']), version=deepcopy(self.version))))
        self.remote_patient = self.patient.start(); self.remote_form = self.form.start()
        self.addCleanup(self.patient.stop); self.addCleanup(self.form.stop)

    async def resolve(self):
        return await service._reviewed_fill_context(self.db, self.client, 'patient', self.refs, self.payload)

    async def test_current_reviewed_records_resolve_all_supported_purposes(self):
        for purpose in ('initial_assessment', 'followup', 'reassessment'):
            self.payload['form_purpose'] = self.binding['purpose'] = purpose
            refs, link, binding, reference = await self.resolve()
            self.assertEqual(refs, self.refs)
            self.assertEqual(reference, self.reference)
        self.remote_patient.assert_awaited_with(self.client, 1, 2, 3)
        self.remote_form.assert_awaited_with(self.client, 1, 4, version=1)

    async def test_unreviewed_patient_or_form_never_contacts_source(self):
        for collection in (self.db.external_patient_links, self.db.external_form_bindings):
            saved = collection.find_one.return_value
            collection.find_one.return_value = None
            with self.assertRaises(service.FormIntegrationError) as ctx:
                await self.resolve()
            self.assertEqual(ctx.exception.error_code, 'REVIEWED_CONTEXT_REQUIRED')
            collection.find_one.return_value = saved
        self.remote_patient.assert_not_awaited()

    async def test_client_cannot_substitute_subject_or_form_or_purpose(self):
        for key in ('project_id', 'center_id', 'subject_id', 'questionnaire_id'):
            self.refs[key] += 100
            with self.assertRaises(service.FormIntegrationError): await self.resolve()
            self.refs[key] -= 100
        self.payload['form_purpose'] = 'reassessment'
        with self.assertRaises(service.FormIntegrationError): await self.resolve()
        self.remote_patient.assert_not_awaited()

    async def test_changed_patient_version_or_environment_rejected(self):
        for remote, key, value in ((self.remote_patient, 'patient_id', 99),
                                    (self.remote_form, 'version', dict(self.version, definition_sha256='b'*64)),
                                    (self.remote_form, 'source', dict(system='form-platform-11344', environment='production'))):
            previous = deepcopy(remote.return_value)
            remote.return_value[key] = value
            with self.assertRaises(service.FormIntegrationError) as ctx: await self.resolve()
            self.assertEqual(ctx.exception.error_code, 'SOURCE_CONTEXT_CHANGED')
            remote.return_value = previous

    async def test_origin_mismatch_rejected_before_network(self):
        self.client.source_origin = 'https://another-source.example'
        with self.assertRaises(service.FormIntegrationError): await self.resolve()
        self.remote_patient.assert_not_awaited()

    async def test_transaction_writes_both_authorizations_and_rejects_revocation(self):
        session = object()
        await service._lock_reviewed_fill_context(self.db, session, self.link, self.binding)
        for collection in (self.db.external_patient_links, self.db.external_form_bindings):
            args = collection.update_one.await_args
            self.assertEqual(args.kwargs['session'], session)
            self.assertIn('status', args.args[0])
            self.assertEqual(args.args[1], {'$inc': {'fill_use_revision': 1}})
        self.db.external_form_bindings.update_one.return_value.matched_count = 0
        with self.assertRaises(service.FormIntegrationError) as ctx:
            await service._lock_reviewed_fill_context(self.db, session, self.link, self.binding)
        self.assertEqual(ctx.exception.error_code, 'REVIEWED_CONTEXT_CHANGED')

    async def test_malformed_context_and_missing_review_fail_closed(self):
        for value in (None, {}, 'bad', [None], [dict(self.reference, patient_id=True)]):
            self.link['references'] = value
            with self.assertRaises(service.FormIntegrationError): await self.resolve()
        self.link['references'] = [self.reference]
        self.binding['verified_at'] = 'not-a-date'
        with self.assertRaises(service.FormIntegrationError): await self.resolve()

    async def test_invalid_source_configuration_is_a_service_error(self):
        for value in (None, 'https://source.example/path', 'file:///tmp/source', 'https://user:secret@source.example'):
            self.client.source_origin = value
            with self.assertRaises(service.FormIntegrationError) as ctx: await self.resolve()
            self.assertEqual(ctx.exception.error_code, 'SOURCE_CONFIGURATION_INVALID')


import os
from uuid import uuid4
from motor.motor_asyncio import AsyncIOMotorClient
from app.integrations.forms.client import FormPlatformUnavailable


@unittest.skipUnless(os.environ.get('REHAB_TEST_REVIEWED_FILL_MONGO_URI'), 'isolated replica set required')
class ReviewedFillMongoTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from urllib.parse import urlsplit
        uri = os.environ['REHAB_TEST_REVIEWED_FILL_MONGO_URI']
        if urlsplit(uri).hostname not in {'127.0.0.1', 'localhost', '::1'}: raise RuntimeError('local only')
        self.mongo = AsyncIOMotorClient(uri)
        self.db = self.mongo['reviewed_fill_test_'+uuid4().hex]
        await self.db.command('hello')
        seed = ReviewedFillContextTests(); seed.setUp()
        self.addCleanup(seed.patient.stop); self.addCleanup(seed.form.stop)
        self.seed = seed
        self.patient_id = str(ObjectId())
        seed.link['local_patient_id'] = self.patient_id
        await self.db.users.insert_one(dict(_id=ObjectId(self.patient_id), role='patient', is_active=True))
        await self.db.external_patient_links.insert_one(seed.link)
        await self.db.external_form_bindings.insert_one(seed.binding)
        self.actor = SimpleNamespace(id=str(ObjectId()), role='admin')
        self.payload = dict(seed.payload, patient_id=self.patient_id, remote_project_id=1,
                            remote_center_id=2, remote_subject_id=3, remote_questionnaire_id=4,
                            allowed_origin='https://rp.example')
        self.remote = SimpleNamespace(source_origin=seed.client.source_origin,
            create_fill_session=AsyncMock(return_value=dict(operator_user_id=7, session_uuid='synthetic-session', embed_token='synthetic-token',
                embed_url='https://source.example/integration/embed/synthetic-token')),
            cancel_fill_session=AsyncMock())
        from app.integrations.identity.service import FillDelegation
        self.delegation = FillDelegation(client=SimpleNamespace(settings=SimpleNamespace(issuer='https://source.example')),
            sid='synthetic-session', token='synthetic-source-token', record={'_id':'session-hash','issuer':'https://source.example','subject':'subject','binding_revision':'a'*64}, actor_id=self.actor.id, role=self.actor.role)
        for name in ('revalidate', 'lock'):
            fixture_patch = patch('app.integrations.identity.service.FillDelegation.'+name, new=AsyncMock())
            fixture_patch.start(); self.addCleanup(fixture_patch.stop)
        self.env = patch.dict(os.environ, {'FORM_PLATFORM_FILL_ENABLED':'true'}); self.env.start(); self.addCleanup(self.env.stop)

    async def asyncTearDown(self):
        await self.mongo.drop_database(self.db.name)
        self.mongo.close()

    async def test_success_locks_both_reviews_in_same_task_transaction(self):
        task = await service.create_fill_task(self.db, self.remote, self.actor, self.payload, delegation=self.delegation)
        # Collection name is authoritative; task and locks are persisted together.
        stored = await self.db[service.models.COLLECTION_NAME].find_one({'_id':ObjectId(task['id'])})
        self.assertEqual(stored['reviewed_context']['purpose'], 'followup')
        self.assertEqual((await self.db.external_patient_links.find_one({}))['fill_use_revision'], 1)
        self.assertEqual((await self.db.external_form_bindings.find_one({}))['fill_use_revision'], 1)

    async def test_revocation_during_remote_creation_rolls_back_and_cancels(self):
        for target in ('external_patient_links', 'external_form_bindings'):
            await self.db.external_patient_links.update_one({}, {'$set':{'status':'verified'}})
            await self.db.external_form_bindings.update_one({}, {'$set':{'status':'active'}})
            async def revoke(_payload, **kwargs):
                await self.db[target].update_one({}, {'$set':{'status':'revoked'}})
                return dict(operator_user_id=7, session_uuid='synthetic-'+target, embed_token='synthetic-token', embed_url='https://source.example/embed/synthetic-token')
            self.remote.create_fill_session.side_effect = revoke
            with self.assertRaises(service.FormIntegrationError) as ctx:
                await service.create_fill_task(self.db, self.remote, self.actor, self.payload, delegation=self.delegation)
            self.assertEqual(ctx.exception.error_code, 'REVIEWED_CONTEXT_CHANGED')
            self.remote.cancel_fill_session.assert_awaited_with('synthetic-'+target)
        docs = await self.db[service.models.COLLECTION_NAME].find({}).to_list(None)
        self.assertEqual([d['status'] for d in docs], ['failed', 'failed'])
        self.assertNotIn('fill_use_revision', await self.db.external_patient_links.find_one({}))

    async def test_failed_remote_compensation_records_recovery_requirement(self):
        async def revoke(_payload, **kwargs):
            await self.db.external_form_bindings.update_one({}, {'$set':{'status':'revoked'}})
            return dict(operator_user_id=7, session_uuid='synthetic-failed-cancel', embed_token='synthetic-token', embed_url='https://source.example/embed/synthetic-token')
        self.remote.create_fill_session.side_effect = revoke
        self.remote.cancel_fill_session.side_effect = FormPlatformUnavailable('unavailable')
        with self.assertRaises(service.FormIntegrationError) as ctx:
            await service.create_fill_task(self.db, self.remote, self.actor, self.payload, delegation=self.delegation)
        self.assertEqual(ctx.exception.error_code, 'FILL_TASK_CLEANUP_REQUIRED')
        stored = await self.db[service.models.COLLECTION_NAME].find_one({})
        self.assertEqual(stored['status'], 'failed')
        self.assertTrue(stored['cleanup_required'])

    async def test_snapshot_read_does_not_allow_commit_after_concurrent_revoke(self):
        from app.db.transactions import run_followup_transaction
        first = True
        async def mutation(session):
            nonlocal first
            await self.db.external_patient_links.find_one({'_id':self.seed.link['_id']}, session=session)
            if first:
                first = False
                await self.db.external_patient_links.update_one({'_id':self.seed.link['_id']}, {'$set':{'status':'revoked'}})
            await service._lock_reviewed_fill_context(self.db, session, self.seed.link, self.seed.binding)
            await self.db[service.models.COLLECTION_NAME].insert_one({'status':'session_created'}, session=session)
        with self.assertRaises(service.FormIntegrationError) as ctx:
            await run_followup_transaction(self.db, mutation)
        self.assertEqual(ctx.exception.error_code, 'REVIEWED_CONTEXT_CHANGED')
        self.assertEqual(await self.db[service.models.COLLECTION_NAME].count_documents({}), 0)
        self.assertNotIn('fill_use_revision', await self.db.external_form_bindings.find_one({}))
