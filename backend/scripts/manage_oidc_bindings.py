#!/usr/bin/env python3
"""Default read-only. Run as a privileged operator AFTER independent human verification.

No name/email matching, password migration, role assignment or account creation.
Evidence must refer to an access-controlled verification record, not contain PII.
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings
from app.integrations.identity.bindings import manage_binding
from app.integrations.identity.service import ensure_identity_indexes


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("bind", "disable", "review-role"))
    parser.add_argument("--issuer", required=True)
    parser.add_argument("--subject", required=True)
    parser.add_argument("--actor-id", required=True)
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--evidence-reference", required=True)
    parser.add_argument("--approved-role", choices=("admin", "doctor", "health_manager", "patient"),
                        help="Required for bind/review-role; must match the independently reviewed current local role")
    parser.add_argument("--apply", action="store_true")
    args = vars(parser.parse_args())
    client = AsyncIOMotorClient(settings.MONGODB_URL, serverSelectionTimeoutMS=5000)
    try:
        db = client[settings.MONGODB_DB_NAME]
        if args["apply"]:
            await ensure_identity_indexes(db)
        print(json.dumps(await manage_binding(db, **args), ensure_ascii=False, indent=2))
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(main())
