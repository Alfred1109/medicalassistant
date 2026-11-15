"""Removed legacy rehabilitation progress statistics routes."""
import unittest

import httpx

from app.main import app


class RemovedRehabStatisticsRoutesTests(unittest.IsolatedAsyncioTestCase):
    async def test_legacy_plan_statistics_and_trends_routes_are_gone(self):
        async with httpx.AsyncClient(app=app, base_url="http://test") as client:
            for path in (
                "/api/rehabilitation/plans/507f1f77bcf86cd799439011/statistics",
                "/api/rehabilitation/plans/507f1f77bcf86cd799439011/trends",
            ):
                response = await client.get(path)
                self.assertEqual(response.status_code, 404, response.text)
