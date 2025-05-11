import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
from app.core.config import settings

async def update_test_patients():
    # 连接数据库
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    db = client[settings.MONGODB_DB_NAME]
    
    # 获取医生ID
    doctor = await db['users'].find_one({'email': 'doctor@example.com'})
    if not doctor:
        print('未找到医生账号')
        return
    
    doctor_id = str(doctor['_id'])
    print(f'医生ID: {doctor_id}')
    
    # 获取所有患者ID
    patient_ids = doctor.get('patients', [])
    if not patient_ids:
        print('医生没有关联患者')
        return
    
    print(f'找到 {len(patient_ids)} 个患者ID')
    
    # 更新每个患者确保有必要字段
    for patient_id in patient_ids:
        try:
            patient = await db['users'].find_one({'_id': ObjectId(patient_id)})
            if not patient:
                print(f'找不到患者 ID: {patient_id}')
                continue
                
            # 检查并添加缺失字段
            update_fields = {}
            
            if 'password_hash' not in patient and 'hashed_password' not in patient:
                update_fields['password_hash'] = 'default_hash_value'
                
            if 'email' not in patient:
                update_fields['email'] = f'patient_{patient_id}@example.com'
                
            if update_fields:
                await db['users'].update_one(
                    {'_id': ObjectId(patient_id)},
                    {'$set': update_fields}
                )
                print(f'更新患者 {patient.get("name", "未知")} (ID: {patient_id}): 添加了字段 {", ".join(update_fields.keys())}')
            else:
                print(f'患者 {patient.get("name", "未知")} (ID: {patient_id}) 数据完整，无需更新')
                
        except Exception as e:
            print(f'更新患者数据时出错 (ID: {patient_id}): {str(e)}')
    
    client.close()

if __name__ == "__main__":
    asyncio.run(update_test_patients()) 