"""
测试医生数据生成脚本
用于向MongoDB数据库添加模拟医生数据
"""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings
from app.models.user import Doctor
from app.services.user_service import UserService
from app.schemas.user import UserCreate
from datetime import datetime
import bcrypt

# 模拟医生数据，与前端硬编码数据匹配
MOCK_DOCTORS = [
    {
        "name": "王医生",
        "email": "wang@hospital.com",
        "password": "Doctor123!",
        "department": "骨科",
        "professional_title": "主任医师",
        "specialty": "脊柱外科",
        "phone": "13800138001",
        "patients_count": 45,
        "status": "在职",
        "join_date": "2015-05-10",
        "certifications": ["医师资格证", "医师执业证", "专科医师证书"],
    },
    {
        "name": "李医生",
        "email": "li@hospital.com",
        "password": "Doctor123!",
        "department": "神经内科",
        "professional_title": "副主任医师",
        "specialty": "神经康复",
        "phone": "13800138002",
        "patients_count": 38,
        "status": "在职",
        "join_date": "2017-03-15",
        "certifications": ["医师资格证", "医师执业证"]
    },
    {
        "name": "赵医生",
        "email": "zhao@hospital.com",
        "password": "Doctor123!",
        "department": "康复科",
        "professional_title": "主治医师",
        "specialty": "运动康复",
        "phone": "13800138003",
        "patients_count": 30,
        "status": "在职",
        "join_date": "2018-09-01",
        "certifications": ["医师资格证", "医师执业证", "康复治疗师证书"]
    },
    {
        "name": "钱医生",
        "email": "qian@hospital.com",
        "password": "Doctor123!",
        "department": "内科",
        "professional_title": "副主任医师",
        "specialty": "心脏康复",
        "phone": "13800138004",
        "patients_count": 42,
        "status": "休假",
        "join_date": "2016-07-20",
        "certifications": ["医师资格证", "医师执业证", "心脏康复专科证书"]
    },
    {
        "name": "孙医生",
        "email": "sun@hospital.com",
        "password": "Doctor123!",
        "department": "康复科",
        "professional_title": "主治医师",
        "specialty": "神经康复",
        "phone": "13800138005",
        "patients_count": 35,
        "status": "在职",
        "join_date": "2019-02-10",
        "certifications": ["医师资格证", "医师执业证"]
    }
]

async def create_test_doctors():
    """创建测试医生数据"""
    print("开始创建测试医生数据...")
    
    # 连接数据库
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    db = client[settings.MONGODB_DB_NAME]
    user_service = UserService(db)
    
    # 插入或更新每个医生
    for doctor_data in MOCK_DOCTORS:
        # 检查医生是否已存在
        existing_doctor = await user_service.get_user_by_email(doctor_data["email"])
        
        if existing_doctor:
            print(f"医生已存在: {doctor_data['name']} ({doctor_data['email']})")
            continue
        
        # 创建新医生
        user_create = UserCreate(
            email=doctor_data["email"],
            password=doctor_data["password"],
            name=doctor_data["name"],
            role="doctor"
        )
        
        # 创建基础用户
        new_doctor = await user_service.create_user(user_create)
        
        if not new_doctor:
            print(f"创建医生失败: {doctor_data['name']}")
            continue
        
        # 添加医生特定数据
        doctor_update = {
            "specialty": doctor_data["specialty"],
            "department": doctor_data["department"],
            "professional_title": doctor_data["professional_title"],
            "metadata": {
                "phone": doctor_data["phone"],
                "patients_count": doctor_data["patients_count"],
                "status": doctor_data["status"],
                "join_date": doctor_data["join_date"],
                "certifications": doctor_data["certifications"]
            }
        }
        
        # 更新医生记录
        await db.users.update_one(
            {"_id": new_doctor.id},
            {"$set": doctor_update}
        )
        
        print(f"成功创建医生: {doctor_data['name']} ({doctor_data['email']})")
    
    # 关闭数据库连接
    client.close()
    print("测试医生数据创建完成！")

if __name__ == "__main__":
    asyncio.run(create_test_doctors()) 