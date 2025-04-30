"""
测试医疗机构数据生成脚本
用于向MongoDB数据库添加模拟医疗机构数据
"""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings
from datetime import datetime
from bson import ObjectId

# 模拟医疗机构数据
MOCK_ORGANIZATIONS = [
    {
        "name": "北京康复医院",
        "type": "specialized",
        "level": "三级",
        "address": "北京市海淀区学院路30号",
        "contact": {
            "phone": "010-12345678",
            "email": "contact@bjkfyy.com",
            "website": "http://www.bjkfyy.com"
        },
        "departments": ["骨科", "神经内科", "康复科", "心脏科", "呼吸科"],
        "beds": 500,
        "established_year": 1990,
        "description": "北京地区专业康复医疗机构，提供全面的康复医疗服务。",
        "specialties": ["骨科康复", "神经康复", "心脏康复"]
    },
    {
        "name": "上海康复中心",
        "type": "clinic",
        "level": "专科",
        "address": "上海市浦东新区张江路500号",
        "contact": {
            "phone": "021-87654321",
            "email": "info@shkfzx.com",
            "website": "http://www.shkfzx.com"
        },
        "departments": ["康复科", "理疗科", "中医科"],
        "beds": 120,
        "established_year": 2005,
        "description": "专注于运动损伤和慢性疾病康复的专业康复中心。",
        "specialties": ["运动损伤康复", "中医康复", "慢病管理"]
    },
    {
        "name": "广州康健医院",
        "type": "general",
        "level": "二级",
        "address": "广州市天河区天河路200号",
        "contact": {
            "phone": "020-98765432",
            "email": "service@gzkjyy.com",
            "website": "http://www.gzkjyy.com"
        },
        "departments": ["内科", "外科", "康复科", "儿科", "妇科"],
        "beds": 300,
        "established_year": 2000,
        "description": "综合性医院，设有专业康复部门，提供全方位医疗服务。",
        "specialties": ["儿童康复", "术后康复", "老年康复"]
    }
]

async def create_test_organizations():
    """创建测试医疗机构数据"""
    print("开始创建测试医疗机构数据...")
    
    # 连接数据库
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    db = client[settings.MONGODB_DB_NAME]
    
    # 确保集合存在
    if "organizations" not in await db.list_collection_names():
        await db.create_collection("organizations")
    
    # 插入或更新每个机构
    for org_data in MOCK_ORGANIZATIONS:
        # 检查机构是否已存在
        existing_org = await db.organizations.find_one({"name": org_data["name"]})
        
        if existing_org:
            print(f"机构已存在: {org_data['name']}")
            continue
        
        # 添加创建时间和更新时间
        now = datetime.utcnow()
        org_data["created_at"] = now
        org_data["updated_at"] = now
        
        # 插入新机构
        result = await db.organizations.insert_one(org_data)
        
        print(f"成功创建医疗机构: {org_data['name']} (ID: {result.inserted_id})")
    
    # 关闭数据库连接
    client.close()
    print("测试医疗机构数据创建完成！")

if __name__ == "__main__":
    asyncio.run(create_test_organizations()) 