from app.services.user_service import UserService
from app.schemas.user import UserCreate
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings

async def create_test_users():
    # 显式连接数据库
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    db = client[settings.MONGODB_DB_NAME]
    user_service = UserService(db)
    
    # 创建测试管理员
    admin_data = UserCreate(
        email='admin@example.com',
        password='Admin123!',
        name='系统管理员',
        role='admin'
    )
    
    # 创建测试医生
    doctor_data = UserCreate(
        email='doctor@example.com',
        password='Doctor123!',
        name='张医生',
        role='doctor'
    )
    
    # 检查用户是否已存在
    exist_admin = await user_service.get_user_by_email('admin@example.com')
    exist_doctor = await user_service.get_user_by_email('doctor@example.com')
    
    if not exist_admin:
        admin = await user_service.create_user(admin_data)
        print(f'创建管理员成功: {admin}')
    else:
        print('管理员已存在')
        
    if not exist_doctor:
        doctor = await user_service.create_user(doctor_data)
        print(f'创建医生成功: {doctor}')
    else:
        print('医生已存在')
    
    # 关闭数据库连接
    client.close()

if __name__ == "__main__":
    asyncio.run(create_test_users()) 