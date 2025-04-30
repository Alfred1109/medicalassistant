"""
测试患者数据生成脚本
用于向MongoDB数据库添加模拟患者数据
"""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings
from app.models.user import Patient
from app.services.user_service import UserService
from app.schemas.user import UserCreate
from datetime import datetime
import random

# 模拟患者数据
MOCK_PATIENTS = [
    {
        "name": "张三",
        "email": "zhangsan@example.com",
        "password": "Patient123!",
        "gender": "男",
        "age": 45,
        "phone": "13900001111",
        "address": "北京市海淀区中关村大街1号",
        "emergency_contact": {
            "name": "张太太",
            "relationship": "配偶",
            "phone": "13900002222"
        },
        "medical_info": {
            "blood_type": "A型",
            "allergies": ["青霉素"],
            "chronic_diseases": ["高血压", "糖尿病"],
            "medications": ["降压药", "降糖药"],
            "main_diagnosis": "腰椎间盘突出",
            "diagnosis_date": "2023-01-15"
        }
    },
    {
        "name": "李四",
        "email": "lisi@example.com",
        "password": "Patient123!",
        "gender": "男",
        "age": 38,
        "phone": "13911112222",
        "address": "上海市浦东新区张江高科技园区",
        "emergency_contact": {
            "name": "李父",
            "relationship": "父亲",
            "phone": "13911113333"
        },
        "medical_info": {
            "blood_type": "O型",
            "allergies": [],
            "chronic_diseases": [],
            "medications": [],
            "main_diagnosis": "膝关节韧带损伤",
            "diagnosis_date": "2023-02-20"
        }
    },
    {
        "name": "王五",
        "email": "wangwu@example.com",
        "password": "Patient123!",
        "gender": "男",
        "age": 60,
        "phone": "13922223333",
        "address": "广州市天河区体育西路",
        "emergency_contact": {
            "name": "王妻",
            "relationship": "配偶",
            "phone": "13922224444"
        },
        "medical_info": {
            "blood_type": "B型",
            "allergies": ["磺胺类药物"],
            "chronic_diseases": ["冠心病"],
            "medications": ["阿司匹林", "他汀类药物"],
            "main_diagnosis": "脑卒中康复期",
            "diagnosis_date": "2023-03-10"
        }
    },
    {
        "name": "赵六",
        "email": "zhaoliu@example.com",
        "password": "Patient123!",
        "gender": "女",
        "age": 28,
        "phone": "13933334444",
        "address": "深圳市南山区科技园",
        "emergency_contact": {
            "name": "赵母",
            "relationship": "母亲",
            "phone": "13933335555"
        },
        "medical_info": {
            "blood_type": "AB型",
            "allergies": [],
            "chronic_diseases": [],
            "medications": [],
            "main_diagnosis": "肩袖损伤",
            "diagnosis_date": "2023-04-05"
        }
    },
    {
        "name": "孙七",
        "email": "sunqi@example.com",
        "password": "Patient123!",
        "gender": "女",
        "age": 55,
        "phone": "13944445555",
        "address": "成都市武侯区人民南路",
        "emergency_contact": {
            "name": "孙子",
            "relationship": "子女",
            "phone": "13944446666"
        },
        "medical_info": {
            "blood_type": "A型",
            "allergies": ["海鲜"],
            "chronic_diseases": ["类风湿关节炎"],
            "medications": ["甲氨蝶呤", "强的松"],
            "main_diagnosis": "类风湿关节炎康复",
            "diagnosis_date": "2023-05-12"
        }
    }
]

async def create_test_patients():
    """创建测试患者数据"""
    print("开始创建测试患者数据...")
    
    # 连接数据库
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    db = client[settings.MONGODB_DB_NAME]
    user_service = UserService(db)
    
    # 获取所有医生ID，用于分配医患关系
    doctor_cursor = db.users.find({"role": "doctor"})
    doctor_ids = []
    async for doc in doctor_cursor:
        doctor_ids.append(str(doc["_id"]))
    
    # 如果没有医生，则跳过医患关系分配
    have_doctors = len(doctor_ids) > 0
    
    # 插入或更新每个患者
    for patient_data in MOCK_PATIENTS:
        # 检查患者是否已存在
        existing_patient = await user_service.get_user_by_email(patient_data["email"])
        
        if existing_patient:
            print(f"患者已存在: {patient_data['name']} ({patient_data['email']})")
            continue
        
        # 创建新患者
        user_create = UserCreate(
            email=patient_data["email"],
            password=patient_data["password"],
            name=patient_data["name"],
            role="patient"
        )
        
        # 创建基础用户
        new_patient = await user_service.create_user(user_create)
        
        if not new_patient:
            print(f"创建患者失败: {patient_data['name']}")
            continue
        
        # 获取患者ID
        patient_id = new_patient.id
        
        # 随机分配1-2名医生
        practitioners = []
        if have_doctors:
            num_doctors = random.randint(1, min(2, len(doctor_ids)))
            selected_doctors = random.sample(doctor_ids, num_doctors)
            practitioners = selected_doctors
            
            # 为每个医生更新患者列表
            for doctor_id in selected_doctors:
                await db.users.update_one(
                    {"_id": doctor_id},
                    {"$addToSet": {"patients": patient_id}}
                )
        
        # 添加患者特定数据
        patient_update = {
            "demographic_info": {
                "gender": patient_data["gender"],
                "age": patient_data["age"],
                "address": patient_data["address"],
                "phone": patient_data["phone"]
            },
            "emergency_contact": patient_data["emergency_contact"],
            "medical_info": patient_data["medical_info"],
            "practitioners": practitioners,
            "health_managers": [],
            "rehabilitation_plans": [],
            "devices": []
        }
        
        # 更新患者记录
        await db.users.update_one(
            {"_id": new_patient.id},
            {"$set": patient_update}
        )
        
        print(f"成功创建患者: {patient_data['name']} ({patient_data['email']})")
    
    # 关闭数据库连接
    client.close()
    print("测试患者数据创建完成！")

if __name__ == "__main__":
    asyncio.run(create_test_patients()) 