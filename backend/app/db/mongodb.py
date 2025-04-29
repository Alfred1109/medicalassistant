from motor.motor_asyncio import AsyncIOMotorClient
from typing import AsyncGenerator
from app.core.config import settings

class Database:
    client: AsyncIOMotorClient = None
    
db = Database()

async def get_database() -> AsyncGenerator:
    """Get database connection."""
    return db.client[settings.MONGODB_DB_NAME]

async def connect_to_mongodb():
    """Connect to MongoDB."""
    db.client = AsyncIOMotorClient(settings.MONGODB_URL)
    
async def close_mongodb_connection():
    """Close MongoDB connection."""
    if db.client:
        db.client.close() 