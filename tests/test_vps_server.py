import http.client
import json
import os
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest.mock import patch

import vps_server


class VPSServerTests(unittest.TestCase):
    def setUp(self):
        self.old_env = dict(os.environ)
        os.environ["NEOOS_VPS_API_TOKEN"] = "t" * 40
        os.environ["NEOOS_ALLOWED_ORIGINS"] = "https://gw140427-rgb.github.io"
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), vps_server.VPSHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.host, self.port = self.server.server_address

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        os.environ.clear()
        os.environ.update(self.old_env)

    def request(self, method="GET", path="/api/status", headers=None):
        conn = http.client.HTTPConnection(self.host, self.port, timeout=3)
        conn.request(method, path, headers=headers or {})
        response = conn.getresponse()
        result = response.status, response.getheaders(), response.read()
        conn.close()
        return result

    def test_status_requires_bearer_token(self):
        status, _, body = self.request()
        self.assertEqual(status, 401)
        self.assertEqual(json.loads(body)["error"], "unauthorized")

    @patch("vps_server.subprocess.run")
    def test_authorized_status_lists_real_docker_names(self, run):
        run.return_value.stdout = "neoos-test\nredis-test\n"
        headers = {
            "Authorization": "Bearer " + "t" * 40,
            "Origin": "https://gw140427-rgb.github.io",
        }
        status, response_headers, body = self.request(headers=headers)
        payload = json.loads(body)
        self.assertEqual(status, 200)
        self.assertEqual(payload["list"], ["neoos-test", "redis-test"])
        self.assertEqual(payload["running_vps"], 2)
        self.assertEqual(payload["mode"], "read_only")
        self.assertIn(("Access-Control-Allow-Origin", "https://gw140427-rgb.github.io"), response_headers)
        run.assert_called_once()

    def test_unlisted_origin_is_rejected(self):
        status, headers, _ = self.request(
            method="OPTIONS",
            headers={"Origin": "https://attacker.example"},
        )
        self.assertEqual(status, 403)
        self.assertNotIn("Access-Control-Allow-Origin", dict(headers))

    def test_post_cannot_create_containers(self):
        status, _, body = self.request(
            method="POST",
            headers={"Authorization": "Bearer " + "t" * 40},
        )
        self.assertEqual(status, 405)
        self.assertEqual(json.loads(body)["error"], "read_only_api")


if __name__ == "__main__":
    unittest.main()
