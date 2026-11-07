"""Create synthetic login accounts in a new, explicitly selected local demo DB."""
import argparse
import asyncio
from datetime import datetime, timezone
import re

from motor.motor_asyncio import AsyncIOMotorClient

from app.schemas.user import UserCreate
from app.services.user_service import UserService


DEMO_USERS = (
    ("System Admin", "admin@example.com", "Admin123!", "admin"),
    ("赵医生", "doctor@example.com", "Doctor123!", "doctor"),
    ("刘健康", "liujk@example.com", "Manager123!", "health_manager"),
    ("张三", "zhangsan@example.com", "Patient123!", "patient"),
    ("Test User", "test@example.com", "password123", "patient"),
)


def validate_target(mongo_url: str, database: str) -> None:
    # No credentials, DNS/SRV, seed lists or URI options that can redirect writes.
    match = re.fullmatch(r"mongodb://(?:127\.0\.0\.1|\[::1\]):([0-9]{1,5})/?", mongo_url)
    if match is None or not 1 <= int(match.group(1)) <= 65535:
        raise ValueError("Use an explicit literal-loopback MongoDB URL with a port and no options")
    if re.fullmatch(r"medicalassistant_demo_[a-z0-9_]{8,64}", database) is None:
        raise ValueError("Use a new database named medicalassistant_demo_<unique suffix of at least 8 characters>")


async def initialize_demo_database(mongo_url: str, database: str) -> int:
    """Refuse all existing databases; never reset users or migrate patient data."""
    validate_target(mongo_url, database)
    client = AsyncIOMotorClient(
        mongo_url, directConnection=True, serverSelectionTimeoutMS=4000,
        connectTimeoutMS=4000,
    )
    try:
        db = client[database]
        await db.command("ping")
        if await db.list_collection_names():
            raise ValueError("Database already has collections; no accounts were changed. Select a new demo database")
        # An explicit collection claim makes concurrent initialization fail before
        # creating users. A partial run remains visible and cannot be overwritten.
        manifest = await db.create_collection("demo_seed_manifest")
        await manifest.insert_one({
            "_id": "synthetic-demo-v1", "created_at": datetime.now(timezone.utc),
            "synthetic_only": True, "state": "initializing",
        })
        service = UserService(db)
        for name, email, password, role in DEMO_USERS:
            await service.create_user(UserCreate(name=name, email=email, password=password, role=role))
        await manifest.update_one({"_id": "synthetic-demo-v1"}, {"$set": {"state": "ready", "user_count": len(DEMO_USERS)}})
        return len(DEMO_USERS)
    finally:
        client.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mongo-url", required=True)
    parser.add_argument("--database", required=True)
    args = parser.parse_args()
    try:
        count = asyncio.run(initialize_demo_database(args.mongo_url, args.database))
    except Exception as exc:
        # Do not echo a potentially credential-bearing invalid URI or DB errors.
        parser.exit(1, f"Demo initialization refused or failed ({type(exc).__name__}). Check the local isolated target; existing accounts were not reset.\n")
    print(f"Created {count} synthetic demo accounts in {args.database}. Passwords use normal hash verification.")


if __name__ == "__main__":
    main()
