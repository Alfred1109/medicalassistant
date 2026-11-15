"""Nonblocking boundary for the configured text provider.

The existing SDK timeout/retry policy and request arguments stay unchanged.
Callers retain ownership of prompts, clinical interpretation and error mapping.
"""
import asyncio
from typing import Any

from app.core.config import settings
from app.core.llm import require_llm_api_key


async def complete_text(*, messages: list[dict[str, str]], model: str, **parameters: Any) -> Any:
    # Capture settings in the requesting task, before entering a worker thread.
    key = require_llm_api_key()
    base_url = settings.LLM_API_BASE_URL

    return await _complete(messages=messages, model=model, key=key, base_url=base_url, **parameters)


async def complete_vision(*, messages: list[dict[str, Any]], configuration, **parameters: Any) -> Any:
    key, base_url, model = configuration
    return await _complete(messages=messages, model=model, key=key, base_url=base_url, **parameters)


async def _complete(*, messages, model, key, base_url, **parameters):
    def request():
        from openai import OpenAI
        client = OpenAI(base_url=base_url, api_key=key)
        try:
            return client.chat.completions.create(model=model, messages=messages, **parameters)
        finally:
            client.close()

    return await asyncio.to_thread(request)
