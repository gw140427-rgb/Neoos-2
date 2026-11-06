import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import termux_ai

class TermuxAITests(unittest.TestCase):
    @patch.dict("os.environ", {"TERMUX_AI_API_KEY": "test-key"}, clear=True)
    @patch("termux_ai.urllib.request.urlopen")
    def test_chat_completion_parsing(self, mock_urlopen):
        response_data = {"choices": [{"message": {"content": "안녕!"}}]}
        class FakeResponse:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self): return json.dumps(response_data).encode()
        mock_urlopen.return_value = FakeResponse()
        result = termux_ai.ask_api({"base_url": "https://example.test/v1", "model": "test-model"}, [{"role": "user", "content": "안녕"}])
        self.assertEqual(result, "안녕!")
        request = mock_urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://example.test/v1/chat/completions")
        self.assertEqual(request.get_header("Authorization"), "Bearer test-key")

    @patch.dict("os.environ", {}, clear=True)
    def test_missing_api_key_is_reported(self):
        with self.assertRaisesRegex(RuntimeError, "API 키가 없어"):
            termux_ai.ask_api({"base_url": "https://example.test/v1", "model": "test"}, [])

if __name__ == "__main__":
    unittest.main()
