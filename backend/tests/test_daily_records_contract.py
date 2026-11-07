"""Real isolated Mongo/JWT tests; explicit loopback URI required, no production writes."""
import os
import unittest
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
from uuid import uuid4
from unittest.mock import patch

import httpx
from bson import ObjectId
from fastapi import FastAPI
from jose import jwt
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection
from pymongo.errors import AutoReconnect

from app.api.routers.patient_router import DAILY_RECORDS_COLLECTION, router
from app.core.config import settings
from app.db.mongodb import get_database

URI = os.environ.get('MEDICALASSISTANT_DAILY_TEST_MONGO_URL')

@unittest.skipUnless(URI, 'explicit isolated loopback Mongo URI required')
class DailyRecordsContractTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.assertIn(urlparse(URI).hostname, {'localhost', '127.0.0.1', '::1'})
        self.mongo = AsyncIOMotorClient(URI, serverSelectionTimeoutMS=3000)
        await self.mongo.admin.command('ping')
        self.name = 'daily_contract_' + uuid4().hex
        self.db = self.mongo[self.name]
        self.app = FastAPI()
        self.app.include_router(router, prefix='/api/patients')
        async def database():
            yield self.db
        self.app.dependency_overrides[get_database] = database
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app, raise_app_exceptions=False), base_url='http://daily-test')
        self.patient, self.other, self.doctor = [str(ObjectId()) for _ in range(3)]
        for identifier, role in [(self.patient, 'patient'), (self.other, 'patient'), (self.doctor, 'doctor')]:
            await self.db.users.insert_one({'_id': ObjectId(identifier.removeprefix('object:')), 'email': identifier+'@example.com', 'name':'Synthetic test', 'role':role, 'is_active':True, 'created_at':datetime.now(timezone.utc), 'updated_at':datetime.now(timezone.utc)})
        self.payload = {'date':'2026-11-07', 'pain_level':0, 'mood':'良好', 'sleep':'6小时', 'exercise_completed':False, 'note':'Synthetic daily record'}
        self.collection = self.db[DAILY_RECORDS_COLLECTION]

    async def asyncTearDown(self):
        await self.client.aclose()
        await self.mongo.drop_database(self.name)
        self.mongo.close()

    def headers(self, identifier=None):
        token = jwt.encode({'sub':identifier or self.patient, 'token_type':'access', 'exp':datetime.now(timezone.utc)+timedelta(minutes=10)}, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
        return {'Authorization':'Bearer '+token}

    async def request(self, method, path='', **kwargs):
        return await self.client.request(method, '/api/patients/daily-records'+path, headers=kwargs.pop('headers', self.headers()), **kwargs)

    async def test_empty_get_has_no_writes_and_requires_patient(self):
        for _ in range(2):
            response = await self.request('GET')
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.json(),[])
        self.assertEqual(await self.collection.count_documents({}),0)
        self.assertEqual((await self.request('GET', headers=self.headers(self.doctor))).status_code,403)
        self.assertEqual((await self.client.get('/api/patients/daily-records')).status_code,401)

    async def test_real_create_update_refresh_and_delete(self):
        created = await self.request('POST', json=self.payload)
        self.assertEqual(created.status_code,201,created.text)
        identifier=created.json()['id']
        self.assertTrue(ObjectId.is_valid(identifier.removeprefix('object:')))
        persisted=await self.collection.find_one({'_id':ObjectId(identifier.removeprefix('object:'))})
        self.assertEqual(persisted['user_id'],self.patient)
        self.assertEqual(persisted['pain_level'],0)
        update={**self.payload,'date':'2026-11-08','note':'Updated real persisted record','exercise_completed':True}
        changed=await self.request('PUT','/'+identifier,json=update)
        self.assertEqual(changed.status_code,200,changed.text)
        self.assertEqual(changed.json()['note'],update['note'])
        self.assertEqual((await self.request('GET')).json()[0]['note'],update['note'])
        self.assertEqual((await self.collection.find_one({'_id':ObjectId(identifier.removeprefix('object:'))}))['created_at'],persisted['created_at'])
        deleted=await self.request('DELETE','/'+identifier)
        self.assertEqual(deleted.status_code,204,deleted.text)
        self.assertEqual(deleted.content,b'')
        self.assertEqual((await self.request('GET')).json(),[])
        self.assertEqual((await self.request('DELETE','/'+identifier)).status_code,404)

    async def test_ownership_forgery_and_ids(self):
        created=(await self.request('POST',json=self.payload)).json()
        identifier=created['id']
        self.assertEqual((await self.request('GET',headers=self.headers(self.other))).json(),[])
        for method in ['DELETE','PUT']:
            response=await self.request(method,'/'+identifier,headers=self.headers(self.other),**({'json':self.payload} if method=='PUT' else {}))
            self.assertEqual(response.status_code,404,response.text)
        self.assertIsNotNone(await self.collection.find_one({'_id':ObjectId(identifier.removeprefix('object:'))}))
        self.assertEqual((await self.request('POST',json={**self.payload,'user_id':self.other})).status_code,422)
        self.assertEqual((await self.request('POST',json={**self.payload,'_id':identifier})).status_code,422)
        self.assertEqual((await self.request('DELETE','/invalid')).status_code,422)
        self.assertEqual((await self.request('PUT','/invalid',json=self.payload)).status_code,422)
        for method in ['POST','PUT','DELETE']:
            path='/' + identifier if method!='POST' else ''
            response=await self.request(method,path,headers=self.headers(self.doctor),**({'json':self.payload} if method!='DELETE' else {}))
            self.assertEqual(response.status_code,403,response.text)

    async def test_legacy_string_ids_dates_and_inclusive_filters(self):
        old_id=str(ObjectId())
        await self.collection.insert_many([
            {'_id':old_id,'user_id':self.patient,**self.payload,'date':'2026-11-07T23:59:59'},
            {'user_id':self.patient,**self.payload,'date':datetime(2026,11,6,12)},
            {'user_id':self.patient,**self.payload,'date':'invalid legacy date'},
            {'user_id':self.other,**self.payload},
        ])
        all_records=(await self.request('GET')).json()
        self.assertEqual(len(all_records),3)
        selected=await self.request('GET',params={'start_date':'2026-11-07','end_date':'2026-11-07'})
        self.assertEqual([row['id'] for row in selected.json()],['string:'+old_id])
        self.assertEqual((await self.request('PUT','/'+old_id,json=self.payload)).status_code,200)
        self.assertEqual((await self.request('DELETE','/'+old_id)).status_code,204)
        self.assertIsNone(await self.collection.find_one({'_id':old_id}))
        self.assertEqual((await self.request('GET',params={'start_date':'bad'})).status_code,422)
        self.assertEqual((await self.request('GET',params={'start_date':'2026-11-08','end_date':'2026-11-07'})).status_code,422)

    async def test_bson_id_collision_requires_exact_type(self):
        value = str(ObjectId())
        await self.collection.insert_many([
            {**self.payload, '_id':ObjectId(value), 'user_id':self.patient},
            {**self.payload, '_id':value, 'user_id':self.patient, 'note':'Legacy string ID'},
        ])
        rows=(await self.request('GET')).json()
        self.assertEqual({row['id'] for row in rows},{'object:'+value,'string:'+value})
        self.assertEqual((await self.request('DELETE','/'+value)).status_code,409)
        self.assertEqual((await self.request('PUT','/'+value,json=self.payload)).status_code,409)
        self.assertEqual(await self.collection.count_documents({}),2)
        self.assertEqual((await self.request('PUT','/string:'+value,json={**self.payload,'note':'Edited legacy'})).status_code,200)
        self.assertEqual((await self.collection.find_one({'_id':ObjectId(value)}))['note'],self.payload['note'])
        self.assertEqual((await self.request('DELETE','/object:'+value)).status_code,204)
        self.assertIsNotNone(await self.collection.find_one({'_id':value}))

    async def test_validation_and_database_failures_are_explicit(self):
        for changes in [{'pain_level':-1},{'pain_level':11},{'pain_level':1.5},{'pain_level':True},{'date':'bad'},{'exercise_completed':'false'},{'mood':' '}]:
            self.assertEqual((await self.request('POST',json={**self.payload,**changes})).status_code,422)
        with patch.object(AsyncIOMotorCollection,'find',side_effect=AutoReconnect('synthetic outage')):
            self.assertEqual((await self.request('GET')).status_code,503)
        with patch.object(AsyncIOMotorCollection,'insert_one',side_effect=AutoReconnect('synthetic outage')):
            response=await self.request('POST',json=self.payload)
            self.assertEqual(response.status_code,503,response.text)
        with patch.object(AsyncIOMotorCollection,'delete_one',side_effect=AutoReconnect('synthetic outage')):
            self.assertEqual((await self.request('DELETE','/'+str(ObjectId()))).status_code,503)
        with patch.object(AsyncIOMotorCollection,'find_one_and_update',side_effect=AutoReconnect('synthetic outage')):
            self.assertEqual((await self.request('PUT','/'+str(ObjectId()),json=self.payload)).status_code,503)
        self.assertEqual(await self.collection.count_documents({}),0)
