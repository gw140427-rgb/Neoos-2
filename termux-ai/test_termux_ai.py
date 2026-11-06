import unittest

import termux_ai


class TermuxAITests(unittest.TestCase):
    def test_default_endpoint(self):
        self.assertEqual(
            termux_ai.endpoint_for("https://openrouter.ai/api/v1"),
            "https://openrouter.ai/api/v1/chat/completions",
        )

    def test_full_endpoint_is_normalized(self):
        self.assertEqual(
            termux_ai.endpoint_for("https://example.com/v1/chat/completions"),
            "https://example.com/v1/chat/completions",
        )

    def test_remote_plain_http_rejected(self):
        with self.assertRaises(ValueError):
            termux_ai.normalize_base_url("http://example.com/v1")

    def test_local_http_allowed(self):
        self.assertEqual(
            termux_ai.normalize_base_url("http://127.0.0.1:11434/v1"),
            "http://127.0.0.1:11434/v1",
        )

    def test_extract_text(self):
        self.assertEqual(
            termux_ai.extract_text({"choices": [{"message": {"content": "안녕하세요"}}]}),
            "안녕하세요",
        )


if __name__ == "__main__":
    unittest.main()
