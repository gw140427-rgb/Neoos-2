"""Tests for the local Ollama-backed Neo AI chat server."""

import importlib.util
import json
import re
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("neo_ai_server", ROOT / "neo_ai_server.py")
neo_ai = importlib.util.module_from_spec(spec)
spec.loader.exec_module(neo_ai)


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.body).encode("utf-8")


class ModelConfigTests(unittest.TestCase):
    def test_every_picker_model_has_a_backend(self):
        html = (ROOT / "docs/ai/index.html").read_text(encoding="utf-8")
        for model in re.findall(r'data-model="([^"]+)"', html):
            self.assertIn(model, neo_ai.MODELS)
            self.assertTrue(neo_ai.MODELS[model].endswith(":latest"))

    def test_default_model_is_available(self):
        self.assertIn(neo_ai.DEFAULT_MODEL, neo_ai.MODELS)

    def test_no_client_key_is_required(self):
        self.assertFalse(hasattr(neo_ai, "API_KEY"))
        self.assertNotIn("X-Neo-Key", neo_ai.Handler.__dict__.get("_cors").__code__.co_consts)


class RateLimitTests(unittest.TestCase):
    def test_requests_are_capped_per_ip(self):
        original = neo_ai.RATE_LIMIT
        neo_ai.RATE_LIMIT = 2
        neo_ai._rate_hits.clear()
        try:
            self.assertFalse(neo_ai.rate_limited("127.0.0.1"))
            self.assertFalse(neo_ai.rate_limited("127.0.0.1"))
            self.assertTrue(neo_ai.rate_limited("127.0.0.1"))
            self.assertFalse(neo_ai.rate_limited("127.0.0.2"))
        finally:
            neo_ai.RATE_LIMIT = original
            neo_ai._rate_hits.clear()


class MessageTests(unittest.TestCase):
    def test_valid_messages_are_normalized(self):
        raw = [
            {"role": "user", "content": " 안녕 "},
            {"role": "assistant", "content": "안녕하세요"},
        ]
        self.assertEqual(neo_ai.valid_messages(raw), raw)

    def test_bad_messages_are_rejected(self):
        for raw in (None, [], "hello", [{"role": "robot", "content": "x"}], [{"role": "user", "content": ""}]):
            self.assertIsNone(neo_ai.valid_messages(raw))

    def test_message_count_is_capped(self):
        raw = [{"role": "user", "content": "x"}] * (neo_ai.MAX_MESSAGES + 1)
        self.assertIsNone(neo_ai.valid_messages(raw))


class GenerateTests(unittest.TestCase):
    def test_request_uses_the_selected_model_and_returns_the_reply(self):
        response = FakeResponse({"message": {"content": "서울입니다."}})
        with mock.patch.object(neo_ai, "urlopen", return_value=response) as call:
            reply = neo_ai.generate("neo-2-mini", [{"role": "user", "content": "수도?"}])
        self.assertEqual(reply, "서울입니다.")
        request = call.call_args[0][0]
        self.assertEqual(json.loads(request.data)["model"], "neo-2-mini:latest")


if __name__ == "__main__":
    unittest.main()
