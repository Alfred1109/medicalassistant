"""Missing provider credentials must not become clinical or streaming success."""
import unittest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from jose import jwt
from pydantic import SecretStr

from app.core.config import Settings, settings
from app.core.dependencies import get_agent_service, get_rehabilitation_service
from app.core.llm import LLMConfigurationError, require_llm_api_key
from app.db.mongodb import get_database
from app.main import app
from app.schemas.user import UserResponse
from app.services.agent_optimized_service import AgentOptimizedService
from app.services.agent_service import AgentService
from app.services.rehabilitation_service import RehabilitationService, recommendations_from_model
from app.services.user_service import UserService

SYNTHETIC_OPERATOR_ID = "507f1f77bcf86cd799439011"


class LLMConfigurationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db = MagicMock()
        for name in ("agent_interactions", "llm_generations", "rehab_plans"):
            getattr(self.db, name).insert_one = AsyncMock()
        self.base = AgentService(self.db)
        self.optimized = AgentOptimizedService(self.db)
        self.rehab = RehabilitationService(self.db)

    def assert_no_writes(self):
        for name in ("agent_interactions", "llm_generations", "rehab_plans"):
            getattr(self.db, name).insert_one.assert_not_awaited()

    async def test_default_has_no_credential_and_secret_representation_is_redacted(self):
        self.assertIsNone(Settings.model_fields["LLM_API_KEY"].default)
        config = Settings(LLM_API_KEY="synthetic-test-only-secret", DEBUG=False, _env_file=None)
        self.assertNotIn("synthetic-test-only-secret", repr(config))
        self.assertNotIn("synthetic-test-only-secret", config.model_dump_json())
        for value in (None, SecretStr(""), SecretStr("  ")):
            with patch.object(settings, "LLM_API_KEY", value):
                with self.assertRaises(LLMConfigurationError) as result:
                    require_llm_api_key()
                self.assertEqual(result.exception.status_code, 503)
                self.assertEqual(result.exception.error_code, "LLM_NOT_CONFIGURED")

    async def test_all_base_llm_entries_fail_before_network_or_storage(self):
        calls = [lambda: self.base.process_query("synthetic", {"query": "Synthetic"}),
                 lambda: self.base.generate_agent_parameters({}),
                 lambda: self.base.generate_rehab_plan({}),
                 lambda: self.base.generate_assessment_analysis({}),
                 lambda: self.base._call_llm("Synthetic")]
        with patch.object(settings, "LLM_API_KEY", None), patch("openai.OpenAI") as client:
            for call in calls:
                with self.assertRaises(LLMConfigurationError):
                    await call()
            client.assert_not_called()
        self.assert_no_writes()

    async def test_optimized_cache_and_streaming_cannot_report_success_without_configuration(self):
        self.optimized._get_cache = AsyncMock(return_value={"response": "stale synthetic response"})
        with patch.object(settings, "LLM_API_KEY", None), patch("openai.OpenAI") as client, \
                patch("app.services.agent_optimized_service.asyncio.create_task") as task:
            for streaming in (False, True):
                with self.assertRaises(LLMConfigurationError):
                    await self.optimized.process_query("synthetic", {"query": "Synthetic"}, streaming=streaming)
            with self.assertRaises(LLMConfigurationError):
                await self.optimized.generate_agent_parameters({})
            with self.assertRaises(LLMConfigurationError):
                await self.optimized._streaming_llm_call("synthetic", "query", "prompt", "model", .7, 1, "q")
            task.assert_not_called()
            client.assert_not_called()
        self.optimized._get_cache.assert_not_awaited()
        self.assertTrue(self.optimized.response_queue.empty())
        self.assert_no_writes()

    async def test_recommendations_use_configured_model_text_and_fail_closed(self):
        parsed = recommendations_from_model(
            '[{"name":"踝泵","description":"卧位勾脚","difficulty":"easy","duration_minutes":5,"body_part":"踝"}]',
            "synthetic-model",
        )
        self.assertEqual(parsed[0]["name"], "踝泵")
        self.assertEqual(parsed[0]["source"], "configured_model")
        prose = recommendations_from_model("先由医生确认负重。", "synthetic-model")
        self.assertEqual(prose[0]["name"], "模型建议")
        with patch.object(settings, "LLM_API_KEY", None), patch("openai.OpenAI") as client:
            with self.assertRaises(LLMConfigurationError):
                await self.rehab.get_recommendations("synthetic")
            client.assert_not_called()

    async def test_rehabilitation_outer_fallback_does_not_swallow_missing_configuration(self):
        with patch.object(settings, "LLM_API_KEY", None):
            with self.assertRaises(LLMConfigurationError):
                await self.rehab.generate_rehab_plan_with_llm("synthetic", "Synthetic", "Synthetic", "Synthetic")
        self.assert_no_writes()

    async def test_configured_provider_receives_injected_secret_and_preserves_response(self):
        with patch.object(settings, "LLM_API_KEY", SecretStr("synthetic-test-only-secret")), \
                patch("openai.OpenAI") as constructor:
            completion = constructor.return_value.chat.completions.create.return_value
            completion.choices[0].message.content = '{"synthetic":true}'
            result = await self.base._call_llm("Synthetic")
            self.assertEqual(result, '{"synthetic":true}')
            self.assertEqual(constructor.call_args.kwargs["api_key"], "synthetic-test-only-secret")

    async def test_real_routes_return_actionable_503_instead_of_generated_content(self):
        previous = app.dependency_overrides.copy()
        app.dependency_overrides[get_agent_service] = lambda: self.base
        app.dependency_overrides[get_rehabilitation_service] = lambda: self.rehab
        # 路由已收敛为要求登录；按 test_rehab_agent_auth_contract 的模式打桩认证链
        operator = UserResponse(id=SYNTHETIC_OPERATOR_ID, email="actor@example.com",
                                name="Synthetic Operator", role="doctor", is_active=True,
                                createdAt=datetime.utcnow(), updatedAt=datetime.utcnow())
        get_user_mock = AsyncMock(return_value=operator)

        # AUTH01 对象级授权：/plans/generate 会校验患者归属，按契约测试模式
        # 打桩 db.users.find_one 返回带该操作者归属的患者文档
        patient_db = MagicMock()
        patient_db.users.find_one = AsyncMock(return_value={
            "_id": "synthetic", "role": "patient", "practitioners": [SYNTHETIC_OPERATOR_ID]})

        async def fake_database():
            yield patient_db

        try:
            app.dependency_overrides[get_database] = fake_database
            with patch.object(settings, "LLM_API_KEY", None), patch("openai.OpenAI") as client, \
                    patch.object(UserService, "get_user_by_id", new=get_user_mock):
                token = jwt.encode({"sub": operator.id, "token_type": "access",
                                    "exp": datetime.utcnow() + timedelta(minutes=5)},
                                   settings.SECRET_KEY, algorithm=settings.ALGORITHM)
                headers = {"Authorization": f"Bearer {token}"}
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http:
                    requests = [
                        ("/api/agents/synthetic/query", {"query": "Synthetic"}),
                        ("/api/agents/generate-parameters", {}),
                        ("/api/rehabilitation/plans/generate", {"patient_id": "synthetic", "patient_name": "Synthetic",
                                                               "condition": "Synthetic", "goal": "Synthetic"}),
                    ]
                    for path, payload in requests:
                        response = await http.post(path, json=payload, headers=headers)
                        self.assertEqual(response.status_code, 503, response.text)
                        self.assertEqual(response.json()["error"], "LLM_NOT_CONFIGURED")
                        self.assertNotIn("exercises", response.json())
                client.assert_not_called()
        finally:
            app.dependency_overrides.clear()
            app.dependency_overrides.update(previous)
        self.assert_no_writes()
