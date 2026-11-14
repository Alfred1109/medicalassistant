"""Opt-in production provider/RP interop with disposable SQLite/Mongo and verified TLS."""
import os
from contextlib import ExitStack, contextmanager
from datetime import datetime
from html.parser import HTMLParser
from unittest.mock import AsyncMock, patch
from urllib.parse import urlsplit
from uuid import uuid4
import httpx
from bson import ObjectId
from cryptography.fernet import Fernet
from motor.motor_asyncio import AsyncIOMotorClient
from app.integrations.identity.bindings import manage_binding
from app.integrations.identity.config import OidcSettings
from app.integrations.identity.router import oidc_client
from app.integrations.identity.service import OidcClient, ensure_identity_indexes
from tests import test_source_catalog_interop as harness

SOURCE_SCRIPT = r'''
import json,os,socket,sys
from pathlib import Path
from werkzeug.serving import make_server
from werkzeug.security import generate_password_hash
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
root=Path(sys.argv[1]);store=Path(sys.argv[2]);sys.path.insert(0,str(root))
from app import create_app,db
from app.models import User
sock=socket.socket();sock.bind(('127.0.0.1',0));sock.listen(16);port=sock.getsockname()[1]
issuer='https://127.0.0.1:'+str(port)
private=rsa.generate_private_key(public_exponent=65537,key_size=2048)
key=store/'signing.pem';key.write_bytes(private.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()));key.chmod(0o600)
clients=store/'clients.json';clients.write_text(json.dumps([{'client_id':'rehab-interop','name':'Synthetic Rehabman','secret_hash':generate_password_hash('synthetic-interop-client-secret'),'redirect_uris':['https://rp.synthetic/api/auth/oidc/callback']} ]));clients.chmod(0o600)
app=create_app('testing',config_overrides={'SQLALCHEMY_DATABASE_URI':'sqlite:///'+str(store/'source.sqlite'),'BACKGROUND_TASK_AUTO_RESUME':False,'WTF_CSRF_ENABLED':True,'OIDC_PROVIDER_ENABLED':True,'OIDC_ISSUER':issuer,'OIDC_SIGNING_KEY_FILE':str(key),'OIDC_CLIENTS_FILE':str(clients),'AUTH_STATE_PATH':str(store/'authentication.sqlite')})
# Only captcha generation is deterministic; its real storage and consumption remain.
import app.routes.auth as auth
auth.generate_captcha_text=lambda:'A123'
with app.app_context():
    user=User(username='interop_user',email='interop@example.invalid',role=User.ROLE_USER,is_active=True)
    user.set_password('Synthetic-Interop-User-Password-42');db.session.add(user);db.session.commit();uid=user.id
@app.before_request
def synthetic_account_state():
    if (store/'disable-account').exists():
        user=db.session.get(User,uid)
        if user.is_active:user.is_active=False;db.session.commit()
server=make_server('127.0.0.1',port,app,ssl_context=(str(store/'cert.pem'),str(store/'key.pem')),fd=sock.fileno())
(store/'ready.json').write_text(json.dumps({'ids':{'user':uid},'port':port}))
(store/'process.json').write_text(json.dumps({'pid':os.getpid(),'start':Path('/proc/self/stat').read_text().split()[21]}))
server.serve_forever()
'''

class Inputs(HTMLParser):
    def __init__(self, html):
        super().__init__();self.values={};self.feed(html)
    def handle_starttag(self,tag,attrs):
        values=dict(attrs)
        if tag=='input' and values.get('name'):self.values[values['name']]=values.get('value','')

class SharedTlsTransport(httpx.AsyncHTTPTransport):
    async def aclose(self):pass
    async def finish(self):await super().aclose()

@harness.unittest.skipUnless(os.environ.get('REHAB_TEST_OIDC_SOURCE_INTEROP')=='1','explicit isolated process opt-in required')
class OidcSourceInterop(harness.SourceCatalogInterop):
    __unittest_skip__ = os.environ.get('REHAB_TEST_OIDC_SOURCE_INTEROP') != '1'
    test_real_source_authorized_directories_and_scope_boundaries=None
    test_reviewed_patient_link_and_current_form_binding_persist_without_new_users=None
    test_operator_claims_rejected_and_fill_stays_disabled=None
    @classmethod
    def setUpClass(cls):
        with patch.object(harness,'SOURCE_SCRIPT',SOURCE_SCRIPT):super().setUpClass()
    async def asyncSetUp(self):
        self.mongo=AsyncIOMotorClient(self.mongo_uri,serverSelectionTimeoutMS=3000)
        self.db=self.mongo['rehab_oidc_interop_'+uuid4().hex]
        await ensure_identity_indexes(self.db)
        self.config=OidcSettings(_env_file=None,enabled=True,authentication_mode='oidc',issuer=self.origin,
            public_base_url='https://rp.synthetic',client_id='rehab-interop',client_secret='synthetic-interop-client-secret',
            session_encryption_key=Fernet.generate_key().decode())
        self.transport=SharedTlsTransport(verify=self.context)
        self.service=OidcClient(self.db,self.config,transport=self.transport)
        self.browser=httpx.AsyncClient(verify=self.context,follow_redirects=False)
        self.http=None
    async def asyncTearDown(self):
        if self.http:await self.http.aclose()
        await self.browser.aclose();await self.transport.finish()
        await self.mongo.drop_database(self.db.name);self.mongo.close()
        (self.store/'disable-account').unlink(missing_ok=True)
    @contextmanager
    def application(self):
        from app.main import app
        from app.db.mongodb import get_database
        previous=dict(app.dependency_overrides)
        async def database():yield self.db
        app.dependency_overrides[get_database]=database
        app.dependency_overrides[oidc_client]=lambda:self.service
        try:
            with ExitStack() as stack:
                for module in ('access','router'):stack.enter_context(patch('app.integrations.identity.'+module+'.oidc_settings',self.config))
                stack.enter_context(patch('app.core.auth.oidc_settings',self.config))
                stack.enter_context(patch('app.core.auth.OidcClient',return_value=self.service))
                stack.enter_context(patch('app.integrations.identity.access.OidcClient',return_value=self.service))
                stack.enter_context(patch('app.db.mongodb.get_db',new=AsyncMock(return_value=self.db)))
                yield app
        finally:app.dependency_overrides.clear();app.dependency_overrides.update(previous)
    async def login_and_consent(self):
        start=await self.http.get('/api/auth/oidc/start');self.assertEqual(start.status_code,303,start.text)
        target=start.headers['location'];consent=await self.browser.get(target)
        if consent.status_code==302:
            login_url=self.origin+consent.headers['location'];login=await self.browser.get(login_url)
            csrf=Inputs(login.text).values['csrf_token']
            self.assertEqual((await self.browser.get(self.origin+'/auth/captcha')).status_code,200)
            signed=await self.browser.post(login_url,data={'username':'interop_user','password':'Synthetic-Interop-User-Password-42','captcha':'A123','csrf_token':csrf},headers={'Referer':login_url})
            self.assertEqual(signed.status_code,302,signed.text);consent=await self.browser.get(target)
        self.assertEqual(consent.status_code,200,consent.text)
        allowed=await self.browser.post(target,data={'decision':'allow','csrf_token':Inputs(consent.text).values['csrf_token']},headers={'Referer':target})
        self.assertEqual(allowed.status_code,302,allowed.text)
        result=await self.http.get('/api/auth/oidc/callback?'+urlsplit(allowed.headers['location']).query)
        self.assertEqual(result.status_code,303,result.text)
        return await self.http.get('/api/auth/session')
    async def test_real_login_binding_and_source_disable_fail_closed(self):
        with self.application() as app:
            self.http=httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://rp.synthetic')
            identity=await self.login_and_consent();self.assertEqual(identity.status_code,200,identity.text)
            body=identity.json();self.assertEqual(body['identity_state'],'pending_binding');self.assertFalse(body['clinical_access'])
            subject=body['subject'];self.assertNotEqual(subject,str(self.ids['user']))
            actor_id=ObjectId()
            await self.db.users.insert_one({'_id':actor_id,'name':'Reviewed actor','email':'reviewed@example.com','role':'doctor','is_active':True,'created_at':datetime.utcnow(),'updated_at':datetime.utcnow()})
            await manage_binding(self.db,issuer=self.origin,subject=subject,actor_id=str(actor_id),reviewer='synthetic-reviewer',evidence_reference='synthetic-reviewed-account',approved_role='doctor',apply=True)
            self.assertEqual((await self.http.get('/api/auth/session')).status_code,401)
            bound=await self.login_and_consent();self.assertEqual(bound.status_code,200,bound.text)
            self.assertTrue(bound.json()['clinical_access']);self.assertEqual(bound.json()['actor_id'],str(actor_id))
            self.assertEqual((await self.http.get('/api/users/me')).status_code,200)
            (self.store/'disable-account').touch()
            self.assertEqual((await self.http.get('/api/users/me')).status_code,401)
            self.assertEqual(await self.db.oidc_application_sessions.count_documents({}),0)
