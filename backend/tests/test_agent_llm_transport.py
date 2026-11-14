"""Mainline Agent requests must not block unrelated event-loop work."""
import asyncio
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from pydantic import SecretStr
from app.core.config import settings
from app.core.exceptions import ExternalServiceException
from app.services.agent_service import AgentService


class AgentLlmTransportTests(unittest.IsolatedAsyncioTestCase):
    def service(self):
        db = SimpleNamespace(agents=Mock(), agent_interactions=SimpleNamespace(insert_one=AsyncMock()))
        service = AgentService(db)
        service.get_agent_by_id = AsyncMock(return_value={'system_prompt': 'existing prompt', 'model': 'legacy-selection'})
        return service, db

    async def test_two_requests_and_other_coroutines_progress_while_sdk_waits(self):
        service, db = self.service()
        release = threading.Event()
        started = []
        guard = threading.Lock()
        completion = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='answer'))])
        def call(**kwargs):
            with guard:
                started.append(kwargs)
            if not release.wait(2):
                raise RuntimeError('event loop could not progress')
            return completion
        clients = []
        def constructor(**kwargs):
            client = Mock()
            client.chat.completions.create.side_effect = call
            clients.append(client)
            return client
        with patch.object(settings, 'LLM_API_KEY', SecretStr('synthetic-only')), patch('openai.OpenAI', side_effect=constructor):
            tasks = [asyncio.create_task(service.process_query('agent', {'query': 'question'})),
                     asyncio.create_task(service._call_llm('existing clinical prompt'))]
            try:
                async with asyncio.timeout(1):
                    while len(started) != 2:
                        await asyncio.sleep(.001)
                release.set()
                query, clinical = await asyncio.gather(*tasks)
            finally:
                release.set()
                await asyncio.gather(*tasks, return_exceptions=True)
        self.assertEqual(query['response'], 'answer')
        self.assertEqual(clinical, 'answer')
        self.assertTrue(all(value['model'] == settings.LLM_API_MODEL for value in started))
        self.assertEqual(sorted(value['max_tokens'] for value in started), [1500, 2000])
        self.assertEqual(next(value for value in started if value['max_tokens'] == 1500)['messages'][0]['content'], 'existing prompt')
        self.assertEqual(db.agent_interactions.insert_one.await_count, 1)
        for client in clients:
            client.close.assert_called_once()

    async def test_provider_failure_is_explicit_and_never_recorded_as_success(self):
        service, db = self.service()
        with patch.object(settings, 'LLM_API_KEY', SecretStr('synthetic-only')), patch('openai.OpenAI') as constructor:
            constructor.return_value.chat.completions.create.side_effect = TimeoutError('synthetic provider timeout')
            with self.assertRaises(ExternalServiceException):
                await service.process_query('agent', {'query': 'question'})
            with self.assertRaises(ExternalServiceException):
                await service._call_llm('prompt')
            self.assertEqual(db.agent_interactions.insert_one.await_count, 0)
            self.assertEqual(constructor.return_value.close.call_count, 2)
