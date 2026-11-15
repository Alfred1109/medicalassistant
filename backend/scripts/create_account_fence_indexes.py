#!/usr/bin/env python3
"""account_fences 唯一索引声明（部署侧维护脚本，迁移窗口手动执行）。

登记 app/core/fences.create_account_fence_indexes 的调用点（2026-11-15
冗余审查批次 1 收尾项）。该索引声明此前只有定义、没有任何启动或脚本
路径调用——按 fences.py 的惯例约束，任何应用启动路径都不得调用它
（create_index 会隐式建集合），必须由本脚本在启用栅栏新载体前、切换
窗口内显式执行。

这是写操作：会在 account_fences 集合不存在时隐式建集合。因此：
  1. 只应在发布/迁移窗口内执行，不要在业务运行高峰执行；
  2. 缺省 dry-run（只连接、只打印将执行的动作），传 --apply 才真正
     create_index；
  3. 索引声明幂等（同名同参 create_index 为 no-op），可重复执行。

连接串经 --uri 参数或 MONGODB_URL 环境变量提供。

运行方式（在 backend/ 目录下）：
    .venv/bin/python -m scripts.create_account_fence_indexes            # dry-run
    .venv/bin/python -m scripts.create_account_fence_indexes --apply \
        --uri mongodb://localhost:27017 --db rehab_assistant
"""
import argparse
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from motor.motor_asyncio import AsyncIOMotorClient

from app.core.config import settings
from app.core.fences import (
    ACCOUNT_FENCES,
    ACCOUNT_FENCE_INDEX_NAME,
    create_account_fence_indexes,
)


async def run(uri: str, database: str, apply: bool) -> None:
    client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5000)
    try:
        db = client[database]
        names = await db.list_collection_names()
        exists = ACCOUNT_FENCES in names
        print(f"database={database}")
        print(f"collection={ACCOUNT_FENCES} exists={exists}")
        print(f"index={ACCOUNT_FENCE_INDEX_NAME} "
              f"keys=[('account_id', 1), ('fence_name', 1)] unique=True")
        if not apply:
            print("dry-run: 未执行 create_index（传 --apply 实建）")
            return
        await create_account_fence_indexes(db)
        print("done: create_account_fence_indexes 已执行")
    finally:
        client.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uri", default=settings.MONGODB_URL,
                        help="MongoDB 连接串（缺省 MONGODB_URL）")
    parser.add_argument("--db", default=settings.MONGODB_DB_NAME,
                        help="数据库名（缺省 MONGODB_DB_NAME）")
    parser.add_argument("--apply", action="store_true",
                        help="实际执行 create_index（缺省 dry-run）")
    args = parser.parse_args()
    asyncio.run(run(args.uri, args.db, args.apply))


if __name__ == "__main__":
    main()
