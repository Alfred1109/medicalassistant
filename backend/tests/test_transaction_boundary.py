"""Domain errors and commit uncertainty survive shared transaction execution."""
from types import SimpleNamespace
import os
from uuid import uuid4
import unittest
from unittest.mock import AsyncMock

from pymongo.errors import OperationFailure
from motor.motor_asyncio import AsyncIOMotorClient

from app.core.exceptions import AppBaseException
from app.db.transactions import run_followup_transaction
from app.services.rehab_publication_service import run_rehab_transaction
from app.services.quality_issue_service import transaction as run_quality_transaction


class TransactionBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_domains_preserve_errors_and_unknown_commit_receipt(self):
        for runner, code in ((run_followup_transaction, "FOLLOWUP_TRANSACTION_UNAVAILABLE"),
                             (run_rehab_transaction, "REHAB_TRANSACTION_UNAVAILABLE"),
                             (run_quality_transaction, "QUALITY_TRANSACTION_UNAVAILABLE")):
            with self.subTest(domain=code):
                driver_error = OperationFailure("synthetic", details={
                    "errorLabels": ["UnknownTransactionCommitResult"]})
                session = AsyncMock()
                session.__aenter__.return_value = session
                session.with_transaction.side_effect = driver_error
                db = SimpleNamespace(client=SimpleNamespace(start_session=AsyncMock(return_value=session)))
                with self.assertRaises(AppBaseException) as caught:
                    await runner(db, AsyncMock())
                self.assertEqual(caught.exception.error_code, code)
                self.assertEqual(caught.exception.status_code, 503)
                self.assertTrue(caught.exception.details["commit_result_unknown"])
                self.assertIs(caught.exception.__cause__, driver_error)
                options = session.with_transaction.call_args.kwargs
                self.assertEqual(options["read_concern"].document, {"level": "snapshot"})
                self.assertEqual(options["write_concern"].document, {"w": "majority"})

    async def test_business_conflicts_are_not_rewritten_as_database_errors(self):
        conflict = AppBaseException("review changed", status_code=409, error_code="REVIEW_CHANGED")
        session = AsyncMock()
        session.__aenter__.return_value = session
        session.with_transaction.side_effect = conflict
        db = SimpleNamespace(client=SimpleNamespace(start_session=AsyncMock(return_value=session)))
        for runner in (run_followup_transaction, run_rehab_transaction, run_quality_transaction):
            with self.assertRaises(AppBaseException) as caught:
                await runner(db, AsyncMock())
            self.assertIs(caught.exception, conflict)

    async def test_missing_transaction_client_never_runs_callback(self):
        for runner in (run_followup_transaction, run_rehab_transaction, run_quality_transaction):
            callback = AsyncMock()
            with self.assertRaises(AppBaseException) as caught:
                await runner(SimpleNamespace(), callback)
            self.assertEqual(caught.exception.status_code, 503)
            callback.assert_not_called()

    @unittest.skipUnless(os.environ.get("REHAB_TEST_TRANSACTION_MONGO_URI"), "isolated replica URI required")
    async def test_real_domain_transactions_roll_back_business_conflict(self):
        uri = os.environ["REHAB_TEST_TRANSACTION_MONGO_URI"]
        if not uri.startswith("mongodb://127.0.0.1:"):
            self.fail("explicit loopback test instance required")
        client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5000)
        db = client["rehab_transaction_boundary_" + uuid4().hex]
        try:
            self.assertTrue((await client.admin.command("hello")).get("setName"))
            for runner in (run_followup_transaction, run_rehab_transaction, run_quality_transaction):
                async def mutate(session):
                    await db.receipts.insert_one({"_id": "must-roll-back"}, session=session)
                    raise AppBaseException("synthetic conflict", status_code=409, error_code="CONFLICT")
                with self.assertRaises(AppBaseException):
                    await runner(db, mutate)
                self.assertEqual(await db.receipts.count_documents({}), 0)
        finally:
            await client.drop_database(db.name)
            client.close()

    @unittest.skipUnless(os.environ.get("REHAB_TEST_TRANSACTION_STANDALONE_URI"), "isolated standalone URI required")
    async def test_real_standalone_refuses_atomic_writes(self):
        uri = os.environ["REHAB_TEST_TRANSACTION_STANDALONE_URI"]
        if not uri.startswith("mongodb://127.0.0.1:"):
            self.fail("explicit loopback test instance required")
        client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5000)
        db = client["rehab_transaction_boundary_" + uuid4().hex]
        try:
            self.assertFalse((await client.admin.command("hello")).get("setName"))
            for runner in (run_followup_transaction, run_rehab_transaction, run_quality_transaction):
                async def mutate(session):
                    await db.receipts.insert_one({"_id": "must-not-commit"}, session=session)
                with self.assertRaises(AppBaseException) as caught:
                    await runner(db, mutate)
                self.assertEqual(caught.exception.status_code, 503)
                self.assertFalse(caught.exception.details["commit_result_unknown"])
                self.assertEqual(await db.receipts.count_documents({}), 0)
        finally:
            await client.drop_database(db.name)
            client.close()
