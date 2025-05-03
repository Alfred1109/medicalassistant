import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
from app.core.config import settings

async def create_test_patients():
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
    
    # 创建测试患者数据
    test_patients = [
        {
            '_id': ObjectId(),
            'name': '张三',
            'email': 'patient1@example.com',
            'role': 'patient',
            'age': 45,
            'gender': '男',
            'diagnosis': '腰椎间盘突出',
            'status': '在治疗',
            'is_active': True
        },
        {
            '_id': ObjectId(),
            'name': '李四',
            'email': 'patient2@example.com',
            'role': 'patient',
            'age': 62,
            'gender': '女',
            'diagnosis': '膝关节炎',
            'status': '已完成',
            'is_active': True
        },
        {
            '_id': ObjectId(),
            'name': '王五',
            'email': 'patient3@example.com',
            'role': 'patient',
            'age': 38,
            'gender': '男',
            'diagnosis': '肩周炎',
            'status': '在治疗',
            'is_active': True
        }
    ]
    
    # 插入患者数据
    for patient in test_patients:
        patient_id = patient['_id']
        await db['users'].insert_one(patient)
        print(f'创建患者: {patient["name"]} (ID: {patient_id})')
        
        # 将患者添加到医生的患者列表中
        await db['users'].update_one(
            {'_id': ObjectId(doctor_id)},
            {'$addToSet': {'patients': str(patient_id)}}
        )
        print(f'将患者 {patient["name"]} 添加到医生的患者列表')
    
    # 检查更新后的医生信息
    updated_doctor = await db['users'].find_one({'_id': ObjectId(doctor_id)})
    print(f'医生现在有 {len(updated_doctor.get("patients", []))} 个患者')
    
    client.close()

if __name__ == "__main__":
    asyncio.run(create_test_patients()) 