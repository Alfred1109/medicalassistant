"""
模拟数据创建脚本
用于初始化系统所有模拟数据，包括用户、医生、患者、康复计划、健康记录等
"""
import asyncio
import os
import sys
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings

# 导入各个模拟数据创建模块
from create_test_users import create_test_users
from create_test_doctors import create_test_doctors 
from create_test_patients import create_test_patients
from create_test_health_managers import create_test_health_managers
from create_test_rehab_plans import create_test_rehab_plans
from create_test_health_records import create_test_health_records
from create_test_devices import create_test_devices
from create_test_organizations import create_test_organizations

async def create_all_mock_data():
    """创建所有模拟数据"""
    print("=== 开始创建模拟数据 ===")
    
    # 连接数据库
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    db = client[settings.MONGODB_DB_NAME]
    
    # 按照依赖顺序创建数据
    print("\n--- 步骤1: 创建基础用户账号 ---")
    await create_test_users()
    
    print("\n--- 步骤2: 创建医疗机构数据 ---")
    await create_test_organizations()
    
    print("\n--- 步骤3: 创建医生数据 ---")
    await create_test_doctors()
    
    print("\n--- 步骤4: 创建健康管理师数据 ---")
    await create_test_health_managers()
    
    print("\n--- 步骤5: 创建患者数据 ---")
    await create_test_patients()
    
    print("\n--- 步骤6: 创建康复计划数据 ---")
    await create_test_rehab_plans()
    
    print("\n--- 步骤7: 创建健康记录数据 ---")
    await create_test_health_records()
    
    print("\n--- 步骤8: 创建设备数据 ---")
    await create_test_devices()
    
    # 关闭数据库连接
    client.close()
    
    print("\n=== 所有模拟数据创建完成 ===")

if __name__ == "__main__":
    print("模拟数据初始化工具")
    print("-------------------")
    asyncio.run(create_all_mock_data()) 