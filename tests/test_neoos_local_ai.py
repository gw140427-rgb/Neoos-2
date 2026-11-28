import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from neoos_local_ai import (
    LocalAIError,
    ROLE_PROMPTS,
    list_models,
    run_role_pipeline,
    validate_base_url,
)


class LocalModelHandler(BaseHTTPRequestHandler):
    calls = []

    def log_message(self, format, *args):
        return

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"data": [{"id": "tiny-local-model"}]}).encode())

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        request = json.loads(self.rfile.read(length))
        type(self).calls.append(request)
        body = {"choices": [{"message": {"content": f"report-{len(type(self).calls)}"}}]}
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())


class NeoOSLocalAITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), LocalModelHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}/v1"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def setUp(self):
        LocalModelHandler.calls = []

    def test_remote_hosts_are_rejected(self):
        with self.assertRaises(LocalAIError):
            validate_base_url("https://api.example.com/v1")

    def test_lan_hosts_are_rejected(self):
        with self.assertRaises(LocalAIError):
            validate_base_url("http://10.0.2.15:11434/v1")

    def test_credentials_in_url_are_rejected(self):
        with self.assertRaises(LocalAIError):
            validate_base_url("http://user:pass@127.0.0.1:11434/v1")

    def test_local_models_endpoint(self):
        self.assertEqual(list_models(self.base_url), ["tiny-local-model"])

    def test_five_roles_run_sequentially_on_same_local_model(self):
        result = run_role_pipeline(
            "Review the NeoOS worker architecture",
            model="tiny-local-model",
            base_url=self.base_url,
            timeout=5,
        )
        self.assertEqual(len(ROLE_PROMPTS), 5)
        self.assertEqual(len(result["reports"]), 5)
        self.assertEqual(len(LocalModelHandler.calls), 5)
        self.assertEqual(result["status"], "review_required")
        self.assertFalse(result["files_changed"])
        self.assertFalse(result["commands_executed"])
        self.assertFalse(result["deployed"])
        self.assertIn("not independent subagents", result["note"])

    def test_task_size_is_bounded_before_network_call(self):
        with self.assertRaises(ValueError):
            run_role_pipeline("x" * 4001, model="tiny-local-model", base_url=self.base_url)
        self.assertEqual(LocalModelHandler.calls, [])


if __name__ == "__main__":
    unittest.main()
