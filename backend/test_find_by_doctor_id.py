import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
from app.core.config import settings
from app.models.user import Patient
from app.db.crud_services import PatientCRUD

async def test_find_by_doctor_id():
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
    
    # 创建PatientCRUD实例
    patient_crud = PatientCRUD(db, Patient)
    
    # 测试find_by_doctor_id方法
    try:
        patients = await patient_crud.find_by_doctor_id(doctor_id)
        
        if patients:
            print(f'成功获取到 {len(patients)} 个患者:')
            for i, patient in enumerate(patients, 1):
                print(f'{i}. {patient["name"]} (ID: {patient["id"]})')
                print(f'   年龄: {patient["age"]}, 性别: {patient["gender"]}, 诊断: {patient["diagnosis"]}, 状态: {patient["status"]}')
                print()
        else:
            print('没有找到任何患者')
    except Exception as e:
        print(f'测试时出错: {str(e)}')
    
    # 测试直接从MongoDB中查询
    print("直接从MongoDB查询患者数据:")
    patients_list = doctor.get('patients', [])
    for patient_id in patients_list:
        try:
            patient = await db['users'].find_one({"_id": ObjectId(patient_id), "role": "patient"})
            if patient:
                print(f'MongoDB中的患者: {patient.get("name", "未知")} (ID: {patient_id})')
                print(f'字段: {", ".join(patient.keys())}')
                print()
            else:
                print(f'MongoDB中找不到患者 (ID: {patient_id})')
        except Exception as e:
            print(f'查询患者 {patient_id} 时出错: {str(e)}')
    
    client.close()

if __name__ == "__main__":
    asyncio.run(test_find_by_doctor_id()) 