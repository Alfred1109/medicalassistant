from app.db.mongodb import connect_to_mongodb, close_mongodb_connection
from app.services.user_service import UserService
import asyncio
import logging

# 设置日志级别
logging.basicConfig(level=logging.DEBUG)

async def test_login():
    print("正在连接到数据库...")
    await connect_to_mongodb()
    
    print("初始化用户服务...")
    from app.db.mongodb import get_db
    db = await get_db()
    user_service = UserService(db)
    await user_service.initialize()
    
    print("测试管理员登录...")
    try:
        admin_user = await user_service.authenticate_user("admin@example.com", "Admin123!")
        if admin_user:
            print(f"管理员登录成功: {admin_user.get('email')}, 角色: {admin_user.get('role')}")
            token = await user_service.create_token(admin_user)
            print(f"生成的Token类型: {type(token)}")
            print(f"Token数据: {token.model_dump()}")
        else:
            print("管理员登录失败: 用户名或密码错误")
    except Exception as e:
        print(f"管理员登录过程中发生错误: {str(e)}")
    
    print("测试医生登录...")
    try:
        doctor_user = await user_service.authenticate_user("doctor@example.com", "Doctor123!")
        if doctor_user:
            print(f"医生登录成功: {doctor_user.get('email')}, 角色: {doctor_user.get('role')}")
        else:
            print("医生登录失败: 用户名或密码错误")
    except Exception as e:
        print(f"医生登录过程中发生错误: {str(e)}")
    
    print("关闭数据库连接...")
    await close_mongodb_connection()

async def main():
    try:
        await test_login()
    except Exception as e:
        print(f"发生错误: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main()) 