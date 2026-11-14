"""Opt-in real source login to reviewed fill task; disposable data only."""
import os,time
import json
from urllib.parse import urljoin, urlsplit, parse_qs
import sqlite3
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch
import httpx
from bson import ObjectId
from pymongo import MongoClient
from tests import test_oidc_source_interop as base
from app.integrations.forms.client import FormPlatformClient
from app.integrations.forms.router import get_form_platform_client
from app.integrations.forms.patient_links import bind_reviewed_patient,PatientLinkRequest
from app.integrations.forms.form_bindings import bind_form,FormBindingRequest
from app.integrations.forms.catalog_service import form_version
from app.integrations.identity.bindings import manage_binding

SCRIPT=base.SOURCE_SCRIPT.replace("'name':'Synthetic Rehabman'","'name':'Synthetic Rehabman','integration_client_id':'test-catalog-client'")
SCRIPT=SCRIPT.replace("    user=User(username='interop_user',email='interop@example.invalid',role=User.ROLE_USER,is_active=True)\n    user.set_password('Synthetic-Interop-User-Password-42');db.session.add(user);db.session.commit();uid=user.id",'''    import importlib.util
    spec=importlib.util.spec_from_file_location('fill_fixture',root/'tests/test_integration_catalog_api.py')
    fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)
    data=fixture._make_base_data(capability_profile='fill');ids={key:getattr(value,'id',None) for key,value in data.items()}
    user=data['operator'];user.username='interop_user';user.set_password('Synthetic-Interop-User-Password-42');uid=user.id
    from app.models import PatientArchive
    db.session.add(PatientArchive(patient_id=ids['patient_a'],organization_id=ids['org'],status='active'));db.session.commit();ids['user']=uid''').replace("'ids':{'user':uid}","'ids':ids")

@base.harness.unittest.skipUnless(os.environ.get('REHAB_TEST_OIDC_FILL_INTEROP')=='1','explicit isolated process opt-in required')
class OidcFillInterop(base.OidcSourceInterop):
    __unittest_skip__=os.environ.get('REHAB_TEST_OIDC_FILL_INTEROP')!='1'
    test_real_login_binding_and_source_disable_fail_closed=None
    @classmethod
    def setUpClass(cls):
        original=base.harness.subprocess.check_output
        def command(args,**kwargs):
            if args[:2]==['docker','run']:args=list(args)+['--replSet','reviewed_fill']
            return original(args,**kwargs)
        with patch.object(base,'SOURCE_SCRIPT',SCRIPT),patch.object(base.harness.subprocess,'check_output',command):super().setUpClass()
        try:
            with MongoClient(cls.mongo_uri,serverSelectionTimeoutMS=10000) as mongo:
                mongo.admin.command('replSetInitiate',{'_id':'reviewed_fill','members':[{'_id':0,'host':'127.0.0.1:27017'}]})
                for _ in range(100):
                    if mongo.admin.command('hello').get('isWritablePrimary'):break
                    time.sleep(.1)
                else:raise RuntimeError('isolated replica not primary')
        except BaseException:cls.tearDownClass();raise
    async def test_real_reviewed_fill_identity(self):
        with self.application() as app,patch.dict(os.environ,{'FORM_PLATFORM_FILL_ENABLED':'true'}), patch('app.integrations.identity.config.oidc_settings',self.config), patch('app.integrations.identity.service.OidcClient',return_value=self.service):
            self.http=httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://rp.synthetic')
            pending=await self.login_and_consent();self.assertEqual(pending.status_code,200,pending.text)
            actor_id=ObjectId();patient_id=ObjectId()
            await self.db.users.insert_one({'_id':actor_id,'name':'Reviewed actor','email':'reviewed@example.com','role':'doctor','is_active':True,'created_at':datetime.utcnow(),'updated_at':datetime.utcnow()})
            await self.db.users.insert_one({'_id':patient_id,'role':'patient','is_active':True,'practitioners':[str(actor_id)]})
            await manage_binding(self.db,issuer=self.origin,subject=pending.json()['subject'],actor_id=str(actor_id),reviewer='reviewer',evidence_reference='review/account',approved_role='doctor',apply=True)
            self.assertEqual((await self.login_and_consent()).status_code,200)
            source=FormPlatformClient(self.origin,'test-catalog-client','catalog-client-secret',5,verify_tls=self.context)
            actor=SimpleNamespace(id=str(actor_id))
            await bind_reviewed_patient(self.db,source,actor,PatientLinkRequest(local_patient_id=str(patient_id),project_id=self.ids['project'],center_id=self.ids['center'],subject_id=self.ids['subject'],evidence_reference='review/patient',identity_verified=True))
            version=await form_version(source,self.ids['project'],self.ids['questionnaire'])
            binding=await bind_form(self.db,source,actor,FormBindingRequest(project_id=self.ids['project'],form_id=self.ids['questionnaire'],version=version['version']['version'],purpose='followup',confirmed=True,evidence_reference='review/form'))
            app.dependency_overrides[get_form_platform_client]=lambda:source
            payload={'patient_id':str(patient_id),'remote_project_id':self.ids['project'],'remote_center_id':self.ids['center'],'remote_subject_id':self.ids['subject'],'remote_questionnaire_id':self.ids['questionnaire'],'form_binding_id':binding['id'],'form_purpose':'followup','allowed_origin':'https://rp.synthetic'}
            headers={'Origin':'https://rp.synthetic','X-CSRF-Token':self.http.cookies.get('__Host-rehab_csrf')}
            rejected=await self.http.post('/api/integrations/forms/fill-tasks',json={**payload,'remote_operator_user_id':999},headers=headers);self.assertEqual(rejected.status_code,422,rejected.text)
            original_create = source.create_fill_session
            async def create_with_stale_version(body, **kwargs):
                stale = dict(body['questionnaire_version_ref'])
                stale['version'] += 1
                return await original_create({**body, 'questionnaire_version_ref': stale}, **kwargs)
            with patch.object(source, 'create_fill_session', side_effect=create_with_stale_version):
                stale = await self.http.post('/api/integrations/forms/fill-tasks', json=payload, headers=headers)
            self.assertEqual(stale.status_code, 409, stale.text)
            self.assertEqual(await self.db.integration_fill_tasks.count_documents({}), 0)
            with sqlite3.connect(f'file:{self.store / "source.sqlite"}?mode=ro', uri=True) as source_db:
                self.assertEqual(source_db.execute('SELECT COUNT(*) FROM integration_fill_session').fetchone()[0], 0)
            created=await self.http.post('/api/integrations/forms/fill-tasks',json=payload,headers=headers);self.assertEqual(created.status_code,200,created.text)
            stored=await self.db.integration_fill_tasks.find_one({'_id':ObjectId(created.json()['id'])})
            self.assertEqual(stored['operator']['remote_user_id'],self.ids['user'])
            remote=await source.get_fill_session(created.json()['session']['sessionUuid']);self.assertEqual(remote['operator_user_id'],self.ids['user'])
            self.assertEqual(remote['subject_id'],self.ids['subject'])
            self.assertEqual(remote['questionnaire_id'],self.ids['questionnaire'])
            self.assertNotIn('embedToken', created.json())
            old_entry = await self.http.get('/api/integrations/forms/fill-tasks/' + created.json()['id'] + '/embed-url')
            self.assertEqual(old_entry.status_code, 410)
            launched = await self.http.post('/api/integrations/forms/fill-tasks/' + created.json()['id'] + '/launch', headers=headers)
            self.assertEqual(launched.status_code, 200, launched.text)
            self.assertEqual(launched.headers['Cache-Control'], 'no-store')
            opening = launched.json()
            self.assertEqual(opening['mode'], 'launch')
            source_headers = {'Origin': 'https://rp.synthetic'}
            consumed = await self.browser.post(opening['action'], data={'token': opening['token']}, headers=source_headers)
            self.assertEqual(consumed.status_code, 303, consumed.text)
            replay = await self.browser.post(opening['action'], data={'token': opening['token']}, headers=source_headers)
            self.assertEqual(replay.status_code, 410, replay.text)
            fill_url = urljoin(self.origin, consumed.headers['Location'])
            fill_page = await self.browser.get(fill_url)
            self.assertEqual(fill_page.status_code, 200, fill_page.text)
            inputs = base.Inputs(fill_page.text).values
            submit_url = fill_url.rsplit('/fill', 1)[0] + '/submit'
            draft = await self.browser.post(submit_url, data={
                'submit_type': 'draft',
                'questionnaire_version_presentation': inputs['questionnaire_version_presentation'],
                'csrf_token': inputs['csrf_token'],
                f'question_{self.ids["question"]}': 'synthetic draft preserved',
            }, headers={'Origin': self.origin, 'Referer': fill_url})
            self.assertEqual(draft.status_code, 302, draft.text)
            resumed = await self.http.post('/api/integrations/forms/fill-tasks/' + created.json()['id'] + '/launch', headers=headers)
            self.assertEqual(resumed.status_code, 200, resumed.text)
            self.assertEqual(resumed.json()['mode'], 'resume')
            self.assertNotIn('token', resumed.json())
            restored = await self.browser.get(resumed.json()['url'])
            self.assertEqual(restored.status_code, 303, restored.text)
            draft_id = parse_qs(urlsplit(restored.headers['Location']).query)['response_id'][0]
            recovered = await self.browser.get(urljoin(self.origin, restored.headers['Location']))
            self.assertEqual(recovered.status_code, 200, recovered.text)
            self.assertIn('synthetic draft preserved', recovered.text)
            async with httpx.AsyncClient(verify=self.context, follow_redirects=False) as clean_browser:
                denied_resume = await clean_browser.get(resumed.json()['url'])
                self.assertEqual(denied_resume.status_code, 403)
            for collection in await self.db.list_collection_names():
                rows = await self.db[collection].find({}).to_list(None)
                self.assertNotIn(opening['token'], json.dumps(rows, default=str))
            with sqlite3.connect(f'file:{self.store / "source.sqlite"}?mode=ro', uri=True) as source_db:
                row = source_db.execute('SELECT response_id,embed_token_hash FROM integration_fill_session').fetchone()
                self.assertEqual(str(row[0]), draft_id)
                self.assertNotEqual(row[1], opening['token'])
                self.assertEqual(source_db.execute('SELECT COUNT(*) FROM response WHERE id=?', (draft_id,)).fetchone()[0], 1)
            (self.store/'disable-account').touch()
            disabled=await self.http.post('/api/integrations/forms/fill-tasks',json=payload,headers=headers);self.assertEqual(disabled.status_code,401,disabled.text)
            self.assertEqual(await self.db.integration_fill_tasks.count_documents({}),1)
