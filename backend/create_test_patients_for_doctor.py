"""
为医生创建测试患者数据
此脚本会创建几个测试患者并将其关联到特定医生
"""
import asyncio
import sys
import os
from datetime import datetime

# 添加后端目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 使用后端已有的模块
from app.db.mongodb import connect_to_mongodb, close_mongodb_connection
from app.models.user import User
from app.core.config import settings
from bson import ObjectId

async def create_test_data():
    """创建测试数据"""
    # 先连接到MongoDB
    await connect_to_mongodb()
    from app.db.mongodb import db
    
    # 获取所有医生
    doctors_cursor = db.users.find({"role": "doctor"})
    doctors = await doctors_cursor.to_list(length=100)
    
    if not doctors:
        print("没有找到医生账户！请先创建医生账户。")
        return
    
    # 为每个医生创建患者
    for doctor in doctors:
        doctor_id = str(doctor["_id"])
        doctor_name = doctor.get("name", "未知医生")
        print(f"为医生 {doctor_name} (ID: {doctor_id}) 创建测试患者...")
        
        # 创建5个测试患者
        patient_ids = []
        for i in range(1, 6):
            # 创建患者基本信息
            patient_data = {
                "name": f"测试患者{i}",
                "email": f"patient{i}_{doctor_id[:5]}@example.com",
                "password_hash": "bcrypt_hashed_password",  # 实际应用中应使用bcrypt等算法加密
                "role": "patient",
                "gender": "男" if i % 2 == 0 else "女",
                "age": 30 + i,
                "phone": f"1380000{1000+i}",
                "address": "北京市海淀区",
                "diagnosis": ["椎间盘突出", "腰肌劳损"][i % 2],
                "status": ["在治疗", "随访中", "已完成"][i % 3],
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                "practitioners": [doctor_id],  # 关联到当前医生
            }
            
            # 检查患者是否已存在
            existing_patient = await db.users.find_one({
                "email": patient_data["email"],
                "role": "patient"
            })
            
            if existing_patient:
                patient_id = str(existing_patient["_id"])
                print(f"患者 {patient_data['name']} 已存在 (ID: {patient_id})")
            else:
                # 插入新患者
                result = await db.users.insert_one(patient_data)
                patient_id = str(result.inserted_id)
                print(f"创建患者 {patient_data['name']} (ID: {patient_id})")
            
            patient_ids.append(patient_id)
        
        # 为医生添加患者ID
        await db.users.update_one(
            {"_id": ObjectId(doctor_id)},
            {"$set": {"patients": patient_ids}}
        )
        
        print(f"已为医生 {doctor_name} 添加 {len(patient_ids)} 个测试患者")

async def main():
    try:
        await create_test_data()
        print("测试数据创建完成！")
    except Exception as e:
        print(f"创建测试数据时出错: {str(e)}")
    finally:
        await close_mongodb_connection()

if __name__ == "__main__":
    asyncio.run(main()) 