"""Opt-in real two-application integration, using only newly created synthetic stores.

Run with REHAB_TEST_SOURCE_CATALOG_INTEROP=1. A private TLS source process and
an independently labelled local Mongo container are created and removed here.
No running development or production database is reused.
"""
import asyncio
import ipaddress
import json
import os
from pathlib import Path
import shutil
import ssl
import subprocess
import tempfile
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import unittest
from uuid import uuid4

from bson import ObjectId
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from fastapi import FastAPI
import httpx
from motor.motor_asyncio import AsyncIOMotorClient

from app.core.auth import get_current_active_user
from app.db.mongodb import get_database
from app.integrations.forms import catalog_router, form_bindings, patient_links
from app.integrations.forms.client import FormPlatformClient
from app.integrations.forms.router import router as fill_router


SOURCE_SCRIPT = r'''
import importlib.util,json,os,sys
from pathlib import Path
from werkzeug.serving import make_server
root=Path(sys.argv[1]); store=Path(sys.argv[2]);sys.path.insert(0,str(root))
from app import create_app,db
from app.models import PatientArchive
spec=importlib.util.spec_from_file_location('synthetic_source_fixture',root/'tests/test_integration_catalog_api.py')
fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)
app=create_app('testing',config_overrides={'SQLALCHEMY_DATABASE_URI':'sqlite:///'+str(store/'source.sqlite'),
    'BACKGROUND_TASK_AUTO_RESUME':False,'OIDC_PROVIDER_ENABLED':False})
with app.app_context():
    data=fixture._make_base_data(); ids={key:getattr(value,'id',None) for key,value in data.items()}
    archive=PatientArchive(patient_id=ids['patient_a'],organization_id=ids['org'],status='active')
    db.session.add(archive);db.session.commit();ids['archive']=archive.id
server=make_server('127.0.0.1',0,app,ssl_context=(str(store/'cert.pem'),str(store/'key.pem')))
(store/'ready.json').write_text(json.dumps({'ids':ids,'port':server.server_port}))
receipt={'pid':os.getpid(),'start':Path('/proc/self/stat').read_text().split()[21]}
(store/'process.json').write_text(json.dumps(receipt))
server.serve_forever()
'''

STOP_SCRIPT = r'''
import json,os,signal,sys,time
from pathlib import Path
store=Path(sys.argv[1]);p=store/'process.json'
if not p.exists():raise SystemExit(0)
v=json.loads(p.read_text());pid=v['pid'];proc=Path('/proc')/str(pid)
if not proc.exists():raise SystemExit(0)
if proc.joinpath('stat').read_text().split()[21]!=v['start']:raise RuntimeError('test process identity changed')
if str(store/'source_server.py').encode() not in proc.joinpath('cmdline').read_bytes():raise RuntimeError('wrong test process')
os.kill(pid,signal.SIGTERM)
'''


@unittest.skipUnless(os.environ.get('REHAB_TEST_SOURCE_CATALOG_INTEROP') == '1',
                     'explicit opt-in required for isolated source/Mongo processes')
class SourceCatalogInterop(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.container = None
        cls.process = None
        cls.temp = tempfile.TemporaryDirectory(prefix='rehab-source-catalog-interop-')
        cls.store = Path(cls.temp.name)
        os.chmod(cls.store, 0o700)
        try:
            root = Path(os.environ.get('REHAB_TEST_QUESTIONNAIRE_ROOT',
                                      str(Path(__file__).resolve().parents[3] / '康复问卷管理系统'))).resolve()
            source_python = root / 'venv/bin/python'
            if not source_python.is_file():
                raise RuntimeError('Explicit adjacent source venv is required')
            cls._tls()
            (cls.store/'source_server.py').write_text(SOURCE_SCRIPT)
            (cls.store/'stop_source.py').write_text(STOP_SCRIPT)
            # Lifecycle wrappers belong only to this unique test directory.
            (cls.store/'start.sh').write_text('#!/bin/sh\nexec "'+str(source_python)+'" "'+str(cls.store/'source_server.py')+'" "'+str(root)+'" "'+str(cls.store)+'"\n')
            (cls.store/'stop.sh').write_text('#!/bin/sh\nexec "'+str(source_python)+'" "'+str(cls.store/'stop_source.py')+'" "'+str(cls.store)+'"\n')
            for name in ('start.sh','stop.sh'):
                (cls.store/name).chmod(0o700)
            cls.log = open(cls.store/'source.log', 'wb')
            env = {key: os.environ[key] for key in ('PATH','HOME','LANG') if key in os.environ}
            env.update(FLASK_ENV='testing', SECRET_KEY='synthetic-source-interop-secret',
                       SM4_DATA_KEY='00112233445566778899aabbccddeeff', PYTHONUNBUFFERED='1')
            cls.process = subprocess.Popen([str(cls.store/'start.sh')], cwd=cls.store, env=env,
                                           stdout=cls.log, stderr=subprocess.STDOUT)
            for _ in range(120):
                if (cls.store/'ready.json').exists():
                    break
                if cls.process.poll() is not None:
                    raise RuntimeError('Synthetic source failed; inspect private source.log')
                time.sleep(.1)
            else:
                raise RuntimeError('Synthetic source did not become ready')
            ready = json.loads((cls.store/'ready.json').read_text())
            cls.ids = ready['ids']
            cls.origin = 'https://127.0.0.1:'+str(ready['port'])
            cls.context = ssl.create_default_context(cafile=str(cls.store/'cert.pem'))
            cls.label = 'rehab.source-catalog-interop='+uuid4().hex
            name = 'rehab-source-catalog-interop-'+uuid4().hex[:10]
            cls.container = subprocess.check_output(['docker','run','--rm','-d','--name',name,
                '--label',cls.label,'-p','127.0.0.1::27017','mongo:7.0','--bind_ip_all'], text=True).strip()
            published = subprocess.check_output(['docker','port',cls.container,'27017/tcp'],text=True).strip()
            if not published.startswith('127.0.0.1:'):
                raise RuntimeError('Isolated Mongo must bind loopback only')
            cls.mongo_uri = 'mongodb://'+published+'/?directConnection=true'
            from pymongo import MongoClient
            with MongoClient(cls.mongo_uri, serverSelectionTimeoutMS=15000) as mongo:
                mongo.admin.command('ping')
        except BaseException:
            cls.tearDownClass()
            raise

    @classmethod
    def _tls(cls):
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'Synthetic catalog loopback')])
        cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
                .serial_number(x509.random_serial_number())
                .not_valid_before(datetime.now(timezone.utc)-timedelta(minutes=1))
                .not_valid_after(datetime.now(timezone.utc)+timedelta(hours=2))
                .add_extension(x509.BasicConstraints(ca=True,path_length=None),critical=True)
                .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address('127.0.0.1'))]),critical=False)
                .sign(key,hashes.SHA256()))
        (cls.store/'key.pem').write_bytes(key.private_bytes(serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
        (cls.store/'key.pem').chmod(0o600)
        (cls.store/'cert.pem').write_bytes(cert.public_bytes(serialization.Encoding.PEM))

    @classmethod
    def tearDownClass(cls):
        if getattr(cls,'process',None) and cls.process.poll() is None:
            subprocess.run([str(cls.store/'stop.sh')], check=True, timeout=10)
            cls.process.wait(timeout=10)
        if getattr(cls,'container',None):
            info=json.loads(subprocess.check_output(['docker','inspect',cls.container],text=True))[0]
            if info['Id'] != cls.container or cls.label.split('=',1)[1] != info['Config']['Labels'].get(cls.label.split('=',1)[0]):
                raise RuntimeError('Refuse to stop an unowned container')
            subprocess.run(['docker','stop','--time','5',cls.container],check=True,stdout=subprocess.DEVNULL)
        if getattr(cls,'log',None): cls.log.close()
        if getattr(cls,'temp',None): cls.temp.cleanup()
        super().tearDownClass()

    async def asyncSetUp(self):
        self.mongo = AsyncIOMotorClient(self.mongo_uri,serverSelectionTimeoutMS=3000)
        self.db = self.mongo['rehab_source_catalog_interop_'+uuid4().hex]
        self.actor = SimpleNamespace(id=str(ObjectId()),role='admin')
        self.patient = ObjectId()
        await self.db.users.insert_one({'_id':self.patient,'role':'patient','is_active':True})
        self.source = FormPlatformClient(self.origin,'test-catalog-client','catalog-client-secret',3,
                                         verify_tls=self.context)
        self.app = FastAPI()
        for router in (catalog_router.router,patient_links.router,form_bindings.router,fill_router):
            self.app.include_router(router,prefix='/api')
        self.app.dependency_overrides[get_current_active_user]=lambda:self.actor
        self.app.dependency_overrides[get_database]=lambda:self.db
        self.app.dependency_overrides[catalog_router.get_catalog_client]=lambda:self.source
        self.http = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app),base_url='https://rp.synthetic')

    async def asyncTearDown(self):
        await self.http.aclose()
        await self.mongo.drop_database(self.db.name)
        self.mongo.close()

    async def test_real_source_authorized_directories_and_scope_boundaries(self):
        base='/api/integrations/forms/catalog'
        projects=await self.http.get(base+'/projects')
        self.assertEqual(projects.status_code,200,projects.text)
        self.assertEqual([r['project_id'] for r in projects.json()['data']],[self.ids['project']])
        subjects=await self.http.get(base+f"/projects/{self.ids['project']}/subjects")
        self.assertEqual(subjects.status_code,200,subjects.text)
        self.assertNotIn(self.ids['subject_other_center'],[r['subject_id'] for r in subjects.json()['data']])
        self.assertNotIn(self.ids['subject_unassigned'],[r['subject_id'] for r in subjects.json()['data']])
        for project,center,subject in [(self.ids['project'],self.ids['other_center'],self.ids['subject']),
                (self.ids['project_out'],self.ids['out_center'],self.ids['subject'])]:
            result=await self.http.get(base+f'/projects/{project}/centers/{center}/subjects/{subject}/patient-reference')
            self.assertGreaterEqual(result.status_code,400)
        self.actor.role='doctor'
        self.assertEqual((await self.http.get(base+'/projects')).status_code,403)

    async def test_reviewed_patient_link_and_current_form_binding_persist_without_new_users(self):
        p,c,s,q=(self.ids[k] for k in ('project','center','subject','questionnaire'))
        payload={'local_patient_id':str(self.patient),'project_id':p,'center_id':c,'subject_id':s,
                 'identity_verified':True,'evidence_reference':'synthetic-independent-review'}
        unreviewed=await self.http.post('/api/integrations/forms/patient-links',json=dict(payload,identity_verified=False))
        self.assertEqual(unreviewed.status_code,422)
        linked=await self.http.post('/api/integrations/forms/patient-links',json=payload)
        self.assertEqual(linked.status_code,201,linked.text)
        self.assertEqual(linked.json()['reference']['patient_id'],self.ids['patient_a'])
        self.assertEqual(await self.db.users.count_documents({}),1)
        self.assertEqual(await self.db.external_patient_links.count_documents({}),1)
        duplicate=await self.http.post('/api/integrations/forms/patient-links',json=payload)
        self.assertEqual(duplicate.status_code,409)
        definition=await self.http.get(f'/api/integrations/forms/catalog/projects/{p}/forms/{q}/version')
        self.assertEqual(definition.status_code,200,definition.text)
        self.assertNotIn('definition',definition.json())
        binding={'project_id':p,'form_id':q,'version':definition.json()['version']['version'],
                 'purpose':'followup','evidence_reference':'synthetic-form-review','confirmed':True}
        saved=await self.http.post('/api/integrations/forms/form-bindings',json=binding)
        self.assertEqual(saved.status_code,201,saved.text)
        stored=await self.db.external_form_bindings.find_one({'_id':ObjectId(saved.json()['id'])})
        self.assertEqual(stored['version_ref']['definition_sha256'],definition.json()['version']['definition_sha256'])
        self.assertEqual(stored['audit'][0]['actor_id'],self.actor.id)
        unpublished=await self.http.get(f"/api/integrations/forms/catalog/projects/{p}/forms/{self.ids['questionnaire_unversioned']}/version")
        self.assertEqual(unpublished.status_code,409)

    async def test_operator_claims_rejected_and_fill_stays_disabled(self):
        p,c,s=(self.ids[k] for k in ('project','center','subject'))
        base='/api/integrations/forms'
        self.assertEqual((await self.http.get(base+'/catalog/projects?operator_user_id=999')).status_code,422)
        link={'local_patient_id':str(self.patient),'project_id':p,'center_id':c,'subject_id':s,
              'identity_verified':True,'evidence_reference':'review','remote_operator_user_id':999}
        self.assertEqual((await self.http.post(base+'/patient-links',json=link)).status_code,422)
        form={'project_id':p,'form_id':self.ids['questionnaire'],'version':1,'purpose':'followup',
              'confirmed':True,'evidence_reference':'review','operator_user_id':999}
        self.assertEqual((await self.http.post(base+'/form-bindings',json=form)).status_code,422)
        from unittest.mock import patch
        from app.integrations.forms.router import get_form_platform_client
        self.app.dependency_overrides[get_form_platform_client]=lambda:self.source
        with patch.dict(os.environ,{},clear=False):
            os.environ.pop('FORM_PLATFORM_FILL_ENABLED',None)
            result=await self.http.post(base+'/fill-tasks',json={'patient_id':str(self.patient),'remote_operator_user_id':999})
        self.assertEqual(result.status_code,503,result.text)
        self.assertEqual(result.json()['detail']['error'],'FORM_FILL_DISABLED')
        self.assertEqual(await self.db.integration_fill_tasks.count_documents({}),0)
