"""T40：标签唯一性约束隔离演练（副本集门控）。

对照开发计划 §14 工程基线缺口：标签创建「先查重再插入」存在查重-插入
竞态，并发可产生重复；实施约束前须先盘点历史数据、清零重复，再在
维护窗口手工建唯一索引（不进应用启动路径，app/db/indexes.py 不登记）。

本演练在一个独立临时库（uuid 后缀，teardown drop）上完整走一遍实施
顺序，验证端到端闭环：
1. 合造历史重复数据 → 盘点脚本 audit_database 报出重复组；
2. 清理重复 → 盘点归零；
3. 维护窗口手工建唯一索引 uniq_tag_name_category；
4. asyncio.gather 并发创建同名同类标签：恰好一胜，其余全部转换为
   既有 TAG_EXISTS 语义（409，错误码不变，测试断言不放松）；
5. 唯一索引不越界拦截：不同 (name, category) 创建不受影响。

门控：REHAB_TEST_TAGS_URI（mongodb://127.0.0.1:<port>/...?replicaSet=<name>），
未显式提供时回退沿用 REHAB_TEST_PATIENT_MIGRATION_URI（同一本机副本集
惯例），两者都缺省时全部跳过。每个用例使用独立临时库并只 drop 自己
创建的库，不触碰实例上的任何既有库。

运行：REHAB_TEST_TAGS_URI="mongodb://127.0.0.1:37021/?replicaSet=rehab_rs&directConnection=true" \
      DEBUG=false .venv/bin/python -m pytest tests/test_tag_uniqueness_replica.py -q
"""
import asyncio
import os
import unittest
from uuid import uuid4

from bson import ObjectId
from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ASCENDING

from app.directory.records import TAG_UNIQUE_INDEX_NAME, create_tag
from scripts.label_uniqueness_audit import audit_database

URI = (os.environ.get("REHAB_TEST_TAGS_URI")
       or os.environ.get("REHAB_TEST_PATIENT_MIGRATION_URI"))


@unittest.skipUnless(URI, "set REHAB_TEST_TAGS_URI to an isolated local replica set")
class TagUniquenessReplicaTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        if not URI.startswith(("mongodb://127.0.0.1:", "mongodb://localhost:")):
            self.fail("only an explicit loopback test URI is accepted")
        self.client = AsyncIOMotorClient(URI, serverSelectionTimeoutMS=3000)
        self.db = self.client["rehab_tags_" + uuid4().hex]

    async def asyncTearDown(self):
        await self.client.drop_database(self.db.name)
        self.client.close()

    async def seed_tags(self, docs):
        await self.db.tags.insert_many(dict(doc, _id=ObjectId()) for doc in docs)

    async def test_audit_reports_synthetic_duplicates_then_clean(self):
        """合造重复 → 盘点报出；清理 → 盘点归零。"""
        await self.seed_tags([
            {"name": "步行", "category": "康复", "color": ""},
            {"name": "步行", "category": "康复", "color": "#112233"},  # 重复
            {"name": "拉伸", "category": "康复", "color": ""},
        ])
        report = await audit_database(self.db)
        tags = report["tags"]
        self.assertEqual(tags["total_documents"], 3)
        self.assertEqual(tags["duplicate_key_groups"], 1)
        self.assertEqual(tags["duplicate_documents"], 2)
        self.assertEqual(tags["duplicate_examples"][0]["name"], "步行")
        dup_rows = await self.db.tags.find(
            {"name": "步行", "category": "康复"}).to_list(None)
        self.assertEqual(sorted(tags["duplicate_examples"][0]["ids"]),
                         sorted(str(row["_id"]) for row in dup_rows))
        self.assertEqual(tags["missing_name"], 0)
        self.assertEqual(tags["missing_category"], 0)

        # 清理：保留先创建的一条（与执行手册「保留最早 created_at」一致），
        # 删除重复的另一条，再盘点必须归零。
        duplicates = tags["duplicate_examples"][0]["ids"]
        await self.db.tags.delete_one({"_id": ObjectId(duplicates[-1])})
        report = await audit_database(self.db)
        self.assertEqual(report["tags"]["duplicate_key_groups"], 0)
        self.assertEqual(report["tags"]["total_documents"], 2)

    async def test_audit_reports_anomaly_shapes_for_index_gate(self):
        """name 缺失/null 属历史异常形状，按索引语义归组报出，建索引前须处置。"""
        await self.seed_tags([
            {"category": "康复"},                       # name 缺失
            {"name": None, "category": "康复", "color": ""},  # name null
        ])
        report = await audit_database(self.db)
        tags = report["tags"]
        self.assertEqual(tags["missing_name"], 1)
        self.assertEqual(tags["null_name"], 1)
        # 缺失与 null 在唯一索引上互撞：盘点必须把它们归入同一重复组
        self.assertEqual(tags["duplicate_key_groups"], 1)
        self.assertEqual(tags["duplicate_documents"], 2)
        self.assertEqual(tags["duplicate_examples"][0]["name"], "<missing>")

    async def test_drill_from_duplicate_to_unique_index_and_concurrent_create(self):
        """完整演练：重复 → 盘点报出 → 清零 → 建索引 → 并发创建仅一胜且语义正确。"""
        await self.seed_tags([
            {"name": "步行", "category": "康复", "color": ""},
            {"name": "步行", "category": "康复", "color": "#112233"},  # 历史重复
        ])
        before = await audit_database(self.db)
        self.assertEqual(before["tags"]["duplicate_key_groups"], 1)

        # 清零重复（保留一条）后盘点归零，才允许进入建索引步骤
        duplicates = before["tags"]["duplicate_examples"][0]["ids"]
        await self.db.tags.delete_one({"_id": ObjectId(duplicates[-1])})
        after = await audit_database(self.db)
        self.assertEqual(after["tags"]["duplicate_key_groups"], 0)

        # 维护窗口手工建唯一索引（不进应用启动路径）：幂等名，默认 collation
        await self.db.tags.create_index(
            [("name", ASCENDING), ("category", ASCENDING)],
            name=TAG_UNIQUE_INDEX_NAME, unique=True)

        # 并发创建一个库中尚不存在的新键：查重-插入竞态由唯一索引兜底。
        # 8 个协程同时起跳：恰好一个成功，其余全部 409 TAG_EXISTS
        # （友好查重命中或 11000 兜底转换，语义一致、错误码不变）。
        results = await asyncio.gather(
            *(create_tag(self.db, "按摩", "康复", "") for _ in range(8)),
            return_exceptions=True)
        created = [r for r in results if not isinstance(r, HTTPException)]
        rejected = [r for r in results if isinstance(r, HTTPException)]
        self.assertEqual(len(created), 1, results)
        self.assertEqual(len(rejected), 7, results)
        self.assertEqual(created[0]["name"], "按摩")
        self.assertEqual(created[0]["category"], "康复")
        for rejected_exc in rejected:
            self.assertEqual(rejected_exc.status_code, 409)
            self.assertEqual(rejected_exc.detail, {"code": "TAG_EXISTS"})
        rows = await self.db.tags.find({"name": "按摩", "category": "康复"}).to_list(None)
        self.assertEqual(len(rows), 1)

        # 保留的历史标签经索引创建后仍存在，重复创建仍 409（既有语义）
        with self.assertRaises(HTTPException) as raised:
            await create_tag(self.db, "步行", "康复", "")
        self.assertEqual(raised.exception.detail, {"code": "TAG_EXISTS"})

        # 唯一索引不越界：不同 (name, category) 创建不受影响
        other = await create_tag(self.db, "拉伸", "康复", "")
        self.assertEqual(other["name"], "拉伸")
        cross = await create_tag(self.db, "步行", "宣教", "")
        self.assertEqual(cross["category"], "宣教")
        report = await audit_database(self.db)
        self.assertEqual(report["tags"]["duplicate_key_groups"], 0)
        self.assertEqual(report["tags"]["total_documents"], 4)

    async def test_concurrent_create_without_index_keeps_historic_semantics(self):
        """对照：未建索引时历史行为不变——友好查重或竞态重复并存。

        单事件循环内 find_one 与 insert 的交错不保证必然产生重复（§14
        缺口是概率性竞态），但确定性约束是：不建索引时不存在 11000
        兜底路径，逃逸的失败只能是既有友好查重的 409 TAG_EXISTS，且
        每次成功对应恰好一条落库文档。
        """
        results = await asyncio.gather(
            *(create_tag(self.db, "步行", "康复", "") for _ in range(8)),
            return_exceptions=True)
        created = [r for r in results if not isinstance(r, Exception)]
        rejected = [r for r in results if isinstance(r, HTTPException)]
        self.assertGreaterEqual(len(created), 1, results)
        for rejected_exc in rejected:
            self.assertEqual(rejected_exc.status_code, 409)
            self.assertEqual(rejected_exc.detail, {"code": "TAG_EXISTS"})
        # 无索引时不应有任何其他异常形态（如裸 DuplicateKeyError）逃逸
        self.assertEqual(len(created) + len(rejected), len(results), results)
        rows = await self.db.tags.find({"name": "步行", "category": "康复"}).to_list(None)
        self.assertEqual(len(rows), len(created))


if __name__ == "__main__":
    unittest.main()
