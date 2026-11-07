"""REH02 契约测试：LLM 配置缺失/调用失败/响应解析失败时，
AgentService 与康复方案生成链不得返回模拟内容冒充成功，
必须抛出既定的业务异常（LLMConfigurationError / ExternalServiceException），
且不得向数据库写入任何"生成结果"。"""
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from pydantic import SecretStr

from app.core.config import settings
from app.core.exceptions import ExternalServiceException
from app.core.llm import LLMConfigurationError
from app.services.agent_service import AgentService
from app.services.rehabilitation_service import RehabilitationService

# _call_llm 旧回退路径中的模拟内容特征串，任何返回值/异常信息中都不应出现
MOCK_REHAB_PLAN_MARKERS = (
    "颈部伸展运动",
    "肩部环绕运动",
    "膝关节强化练习",
    "定制化康复计划",
)
MOCK_ASSESSMENT_ANALYSIS_MARKER = "系统无法解析评估结果"
MOCK_PROCESS_QUERY_MARKER = "抱歉，我在处理您的问题时遇到了技术问题"
SYNTHETIC_SECRET = "synthetic-test-only-secret"


class AgentServiceFailureContractTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db = MagicMock()
        for name in ("agent_interactions", "llm_generations", "rehab_plans"):
            getattr(self.db, name).insert_one = AsyncMock()
        # process_query 需要先通过 agent 查找才能到达 LLM 调用
        self.db.agents.find_one = AsyncMock(return_value={"_id": "507f1f77bcf86cd799439011"})
        self.base = AgentService(self.db)
        self.rehab = RehabilitationService(self.db)

    def assert_no_writes(self):
        for name in ("agent_interactions", "llm_generations", "rehab_plans"):
            getattr(self.db, name).insert_one.assert_not_awaited()

    async def test_call_llm_provider_outage_raises_and_never_returns_mock_plan(self):
        with patch.object(settings, "LLM_API_KEY", SecretStr(SYNTHETIC_SECRET)), \
                patch("openai.OpenAI", side_effect=RuntimeError("synthetic provider outage")):
            with self.assertRaises(ExternalServiceException) as result:
                await self.base._call_llm("Synthetic prompt")
            self.assertEqual(result.exception.error_code, "EXTERNAL_SERVICE_ERROR")
            self.assertEqual(result.exception.details.get("service_name"), "llm")
            for marker in MOCK_REHAB_PLAN_MARKERS:
                self.assertNotIn(marker, result.exception.message)

    async def test_call_llm_provider_returns_garbage_is_surfaced_not_faked(self):
        constructor = MagicMock()
        constructor.return_value.chat.completions.create.return_value.choices = []
        with patch.object(settings, "LLM_API_KEY", SecretStr(SYNTHETIC_SECRET)), \
                patch("openai.OpenAI", return_value=constructor.return_value):
            with self.assertRaises(ExternalServiceException):
                await self.base._call_llm("Synthetic prompt")

    async def test_process_query_provider_outage_raises_instead_of_apology_response(self):
        with patch.object(settings, "LLM_API_KEY", SecretStr(SYNTHETIC_SECRET)), \
                patch("openai.OpenAI", side_effect=RuntimeError("synthetic provider outage")):
            with self.assertRaises(ExternalServiceException) as result:
                # 必须使用合法 ObjectId，先通过 agent 查找、走到真正的 LLM 调用
                await self.base.process_query("507f1f77bcf86cd799439011", {"query": "Synthetic"})
            self.assertNotIn(MOCK_PROCESS_QUERY_MARKER, result.exception.message)
        self.assert_no_writes()

    async def test_generate_rehab_plan_outage_raises_and_writes_nothing(self):
        with patch.object(settings, "LLM_API_KEY", SecretStr(SYNTHETIC_SECRET)), \
                patch("openai.OpenAI", side_effect=RuntimeError("synthetic provider outage")):
            with self.assertRaises(ExternalServiceException):
                await self.base.generate_rehab_plan({"patient_id": "synthetic"})
        self.assert_no_writes()

    async def test_generate_rehab_plan_unparseable_llm_response_raises_not_empty_plan(self):
        constructor = MagicMock()
        constructor.return_value.chat.completions.create.return_value.choices[
            0].message.content = "not-json-at-all"
        with patch.object(settings, "LLM_API_KEY", SecretStr(SYNTHETIC_SECRET)), \
                patch("openai.OpenAI", return_value=constructor.return_value):
            with self.assertRaises(ExternalServiceException):
                await self.base.generate_rehab_plan({"patient_id": "synthetic"})
        self.db.llm_generations.insert_one.assert_not_awaited()

    async def test_generate_agent_parameters_unparseable_llm_response_raises_not_none(self):
        constructor = MagicMock()
        constructor.return_value.chat.completions.create.return_value.choices[
            0].message.content = "no json here"
        with patch.object(settings, "LLM_API_KEY", SecretStr(SYNTHETIC_SECRET)), \
                patch("openai.OpenAI", return_value=constructor.return_value):
            with self.assertRaises(ExternalServiceException):
                await self.base.generate_agent_parameters({})
        self.db.llm_generations.insert_one.assert_not_awaited()

    async def test_generate_assessment_analysis_unparseable_llm_response_raises_not_fallback(self):
        constructor = MagicMock()
        constructor.return_value.chat.completions.create.return_value.choices[
            0].message.content = "not-json-at-all"
        with patch.object(settings, "LLM_API_KEY", SecretStr(SYNTHETIC_SECRET)), \
                patch("openai.OpenAI", return_value=constructor.return_value):
            with self.assertRaises(ExternalServiceException) as result:
                await self.base.generate_assessment_analysis({})
            self.assertNotIn(MOCK_ASSESSMENT_ANALYSIS_MARKER, result.exception.message)
        self.db.llm_generations.insert_one.assert_not_awaited()

    async def test_rehab_plan_chain_outage_propagates_and_never_inserts_fallback_plan(self):
        """康复方案生成链：agent_service 抛出的失败不得被外层吞掉换成应急模拟计划"""
        with patch.object(settings, "LLM_API_KEY", SecretStr(SYNTHETIC_SECRET)), \
                patch("openai.OpenAI", side_effect=RuntimeError("synthetic provider outage")):
            with self.assertRaises(ExternalServiceException):
                await self.rehab.generate_rehab_plan_with_llm(
                    "synthetic", "Synthetic", "Synthetic", "Synthetic")
        self.db.rehab_plans.insert_one.assert_not_awaited()
        self.assert_no_writes()

    async def test_rehab_plan_chain_missing_configuration_still_raises_llm_configuration_error(self):
        """既有 503 语义不回退：未配置密钥时康复方案生成链仍抛 LLMConfigurationError"""
        with patch.object(settings, "LLM_API_KEY", None):
            with self.assertRaises(LLMConfigurationError):
                await self.rehab.generate_rehab_plan_with_llm(
                    "synthetic", "Synthetic", "Synthetic", "Synthetic")
        self.assert_no_writes()

    async def test_successful_llm_response_still_flows_through(self):
        """正常路径不受治理影响：LLM 成功返回时计划正常解析并记录生成过程"""
        constructor = MagicMock()
        constructor.return_value.chat.completions.create.return_value.choices[
            0].message.content = '{"name":"真实生成计划","exercises":[]}'
        with patch.object(settings, "LLM_API_KEY", SecretStr(SYNTHETIC_SECRET)), \
                patch("openai.OpenAI", return_value=constructor.return_value):
            plan = await self.base.generate_rehab_plan({"patient_id": "synthetic"})
        self.assertEqual(plan["name"], "真实生成计划")
        self.assertEqual(plan["metadata"]["generated_by"], "llm")
        self.db.llm_generations.insert_one.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
