"""
测试健康管理师数据生成脚本
用于向MongoDB数据库添加模拟健康管理师数据
"""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings
from app.models.user import HealthManager
from app.services.user_service import UserService
from app.schemas.user import UserCreate
from datetime import datetime, timedelta

# 模拟健康管理师数据
MOCK_HEALTH_MANAGERS = [
    {
        "name": "刘健康",
        "email": "liujk@example.com",
        "password": "Manager123!",
        "phone": "13866667777",
        "specialty_areas": ["营养管理", "运动康复"],
        "certification": "高级健康管理师",
        "education": {
            "degree": "硕士",
            "major": "营养学",
            "school": "北京大学",
            "graduation_year": "2018"
        },
        "organization_id": None,
        "status": "在职",
        "join_date": (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
    },
    {
        "name": "陈康复",
        "email": "chenkf@example.com",
        "password": "Manager123!",
        "phone": "13877778888",
        "specialty_areas": ["慢病管理", "心脏康复"],
        "certification": "中级健康管理师",
        "education": {
            "degree": "学士",
            "major": "护理学",
            "school": "复旦大学",
            "graduation_year": "2020"
        },
        "organization_id": None,
        "status": "在职",
        "join_date": (datetime.now() - timedelta(days=180)).strftime("%Y-%m-%d")
    },
    {
        "name": "张健",
        "email": "zhangj@example.com",
        "password": "Manager123!",
        "phone": "13888889999",
        "specialty_areas": ["睡眠健康", "体重管理"],
        "certification": "健康管理师",
        "education": {
            "degree": "学士",
            "major": "运动科学",
            "school": "北京体育大学",
            "graduation_year": "2019"
        },
        "organization_id": None,
        "status": "在职",
        "join_date": (datetime.now() - timedelta(days=270)).strftime("%Y-%m-%d")
    }
]

async def create_test_health_managers():
    """创建测试健康管理师数据"""
    print("开始创建测试健康管理师数据...")
    
    # 连接数据库
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    db = client[settings.MONGODB_DB_NAME]
    user_service = UserService(db)
    
    # 获取组织机构ID（如果有）
    org_cursor = db.organizations.find({})
    org_ids = []
    async for org in org_cursor:
        org_ids.append(str(org["_id"]))
    
    # 插入或更新每个健康管理师
    for i, manager_data in enumerate(MOCK_HEALTH_MANAGERS):
        # 检查健康管理师是否已存在
        existing_manager = await user_service.get_user_by_email(manager_data["email"])
        
        if existing_manager:
            print(f"健康管理师已存在: {manager_data['name']} ({manager_data['email']})")
            continue
        
        # 分配组织机构ID（如果有）
        if org_ids and i < len(org_ids):
            manager_data["organization_id"] = org_ids[i]
        
        # 创建新健康管理师
        user_create = UserCreate(
            email=manager_data["email"],
            password=manager_data["password"],
            name=manager_data["name"],
            role="health_manager"
        )
        
        # 创建基础用户
        new_manager = await user_service.create_user(user_create)
        
        if not new_manager:
            print(f"创建健康管理师失败: {manager_data['name']}")
            continue
        
        # 添加健康管理师特定数据
        manager_update = {
            "certification": manager_data["certification"],
            "specialty_areas": manager_data["specialty_areas"],
            "organization_id": manager_data["organization_id"],
            "education": manager_data["education"],
            "metadata": {
                "phone": manager_data["phone"],
                "status": manager_data["status"],
                "join_date": manager_data["join_date"]
            }
        }
        
        # 更新健康管理师记录
        await db.users.update_one(
            {"_id": new_manager.id},
            {"$set": manager_update}
        )
        
        print(f"成功创建健康管理师: {manager_data['name']} ({manager_data['email']})")
    
    # 关闭数据库连接
    client.close()
    print("测试健康管理师数据创建完成！")

if __name__ == "__main__":
    asyncio.run(create_test_health_managers()) 