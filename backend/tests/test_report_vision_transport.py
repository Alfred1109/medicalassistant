"""Vision extraction uses the configured request without blocking other requests."""
import asyncio
import base64
import os
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.clinical.workspace import _image_excerpt


SETTINGS = {"VISION_API_KEY": "synthetic-vision-secret", "VISION_API_BASE_URL": "https://vision.invalid/v1",
            "VISION_API_MODEL": "synthetic-vision-model"}


def completion(text):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])


class ReportVisionTransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_concurrent_extractions_leave_the_event_loop_available(self):
        released = threading.Event()
        lock = threading.Lock()
        requests, clients = [], []
        event_loop_thread = threading.get_ident()

        def create(**arguments):
            with lock:
                requests.append((threading.get_ident(), arguments))
            if not released.wait(2):
                raise TimeoutError("synthetic provider waiting for unrelated work")
            return completion("  收缩压 120 mmHg  ")

        def constructor(**arguments):
            client = Mock()
            client.chat.completions.create.side_effect = create
            with lock:
                clients.append((arguments, client))
            return client

        with patch.dict(os.environ, SETTINGS), patch("openai.OpenAI", side_effect=constructor):
            tasks = [asyncio.create_task(_image_excerpt(content, "image/png"))
                     for content in (b"first synthetic image", b"second synthetic image")]
            try:
                # Both SDK requests must enter their blocking wait while this
                # unrelated coroutine continues to run on the application loop.
                async with asyncio.timeout(1):
                    while len(requests) != 2:
                        await asyncio.sleep(.001)
                released.set()
                results = await asyncio.gather(*tasks)
            finally:
                released.set()
                await asyncio.gather(*tasks, return_exceptions=True)
        self.assertEqual(results, ["收缩压 120 mmHg", "收缩压 120 mmHg"])
        self.assertTrue(all(thread != event_loop_thread for thread, _ in requests))
        self.assertEqual({request["model"] for _, request in requests}, {SETTINGS["VISION_API_MODEL"]})
        self.assertEqual({request["temperature"] for _, request in requests}, {0})
        self.assertEqual({request["messages"][0]["content"][1]["image_url"]["url"] for _, request in requests},
                         {"data:image/png;base64," + base64.b64encode(content).decode()
                          for content in (b"first synthetic image", b"second synthetic image")})
        self.assertTrue(all(request["messages"][0]["content"][0]["text"] ==
            "只摘录图片上能看清的文字，不要补充图片里没有的数值。看不清就只回复看不清。不超过800字。"
            for _, request in requests))
        for arguments, client in clients:
            self.assertEqual(arguments, {"api_key": SETTINGS["VISION_API_KEY"], "base_url": SETTINGS["VISION_API_BASE_URL"]})
            client.close.assert_called_once()

    async def test_provider_failure_remains_unparsed_and_closes_the_client(self):
        with patch.dict(os.environ, SETTINGS), patch("openai.OpenAI") as constructor:
            client = constructor.return_value
            client.chat.completions.create.side_effect = TimeoutError("synthetic secret and private file details")
            self.assertIsNone(await _image_excerpt(b"synthetic image", "image/jpeg"))
            client.close.assert_called_once()

    async def test_unreadable_and_long_output_keep_the_existing_result_rules(self):
        with patch.dict(os.environ, SETTINGS), patch("openai.OpenAI") as constructor:
            client = constructor.return_value
            for value in (None, "", " 看不清 "):
                client.chat.completions.create.return_value = completion(value)
                self.assertIsNone(await _image_excerpt(b"synthetic", "image/png"))
            client.chat.completions.create.return_value = completion("字" * 801)
            self.assertEqual(await _image_excerpt(b"synthetic", "image/png"), "字" * 800)
            self.assertEqual(client.close.call_count, 4)

    async def test_missing_configuration_does_not_call_a_provider(self):
        with patch.dict(os.environ, {**SETTINGS, "VISION_API_KEY": ""}), patch("openai.OpenAI") as constructor:
            self.assertIsNone(await _image_excerpt(b"synthetic", "image/png"))
            constructor.assert_not_called()
