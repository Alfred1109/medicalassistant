import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings
from bson import ObjectId

async def check_doctor_patients():
    # 连接数据库
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    db = client[settings.MONGODB_DB_NAME]
    
    # 获取医生
    doctor = await db['users'].find_one({'email': 'doctor@example.com'})
    if not doctor:
        print('未找到医生账号')
        return
    
    print(f'医生ID: {doctor["_id"]}')
    print(f'医生信息: {doctor}')
    
    # 获取患者列表
    if 'patients' in doctor:
        print(f'患者列表: {doctor["patients"]}')
        for patient_id in doctor['patients']:
            try:
                patient = await db['users'].find_one({'_id': ObjectId(patient_id)})
                if patient:
                    print(f'患者: {patient["name"]} (ID: {patient["_id"]})')
                else:
                    print(f'未找到患者: {patient_id}')
            except Exception as e:
                print(f'查询患者出错 {patient_id}: {str(e)}')
    else:
        print('医生没有患者列表字段')
    
    client.close()

if __name__ == "__main__":
    asyncio.run(check_doctor_patients()) 