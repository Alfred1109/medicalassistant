"""
运行健康档案服务测试

此脚本用于直接运行健康档案服务的测试。
"""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

from app.core.config import settings
from test_health_record_service import (
    test_create_health_record,
    test_update_health_record,
    test_create_followup_record,
    test_complete_followup,
    test_create_health_data,
    test_get_medical_timeline
)

async def main():
    # 连接测试数据库
    print(f"连接到测试数据库: {settings.MONGODB_URL}/{settings.MONGODB_DB}_test")
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    db = client[settings.MONGODB_DB + "_test"]
    
    # 运行测试
    try:
        print("\n----- 开始测试健康档案服务 -----\n")
        
        await test_create_health_record(db)
        print("✅ 测试通过: 创建健康档案")
        
        await test_update_health_record(db)
        print("✅ 测试通过: 更新健康档案")
        
        await test_create_followup_record(db)
        print("✅ 测试通过: 创建随访记录")
        
        await test_complete_followup(db)
        print("✅ 测试通过: 完成随访")
        
        await test_create_health_data(db)
        print("✅ 测试通过: 创建健康数据")
        
        await test_get_medical_timeline(db)
        print("✅ 测试通过: 获取医疗时间线")
        
        print("\n----- 所有测试通过 -----\n")
    except Exception as e:
        print(f"\n❌ 测试失败: {str(e)}")
        raise
    finally:
        # 清理测试数据
        print("清理测试数据...")
        collections = ['health_records', 'followup_records', 'health_data', 'medical_timelines']
        for collection in collections:
            await db[collection].delete_many({})
        
        # 关闭连接
        print("关闭数据库连接...")
        client.close()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main()) 