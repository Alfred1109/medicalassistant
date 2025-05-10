from app.db.mongodb import get_db, connect_to_mongodb, close_mongodb_connection
import asyncio

async def check_users():
    print("正在连接到数据库...")
    await connect_to_mongodb()
    
    print("获取数据库连接...")
    db = await get_db()
    
    print("查询用户集合...")
    users = await db.users.find().to_list(length=10)
    
    print(f"找到用户数量: {len(users)}")
    
    if users:
        print("用户示例:")
        for user in users:
            print(f"  - Email: {user.get('email')}, 角色: {user.get('role')}, 激活状态: {user.get('is_active', True)}")
    else:
        print("没有找到用户数据")
    
    print("关闭数据库连接...")
    await close_mongodb_connection()

async def main():
    try:
        await check_users()
    except Exception as e:
        print(f"发生错误: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main()) 