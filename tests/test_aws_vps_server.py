import unittest
import urllib.request
import threading
import time
import os
import aws_vps_server

class TestAwsVpsServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["NEOOS_VPS_API_TOKEN"] = "test-token-1234567890-secure-testing-token"
        aws_vps_server.TOKEN = "test-token-1234567890-secure-testing-token"
        cls.server = aws_vps_server.ThreadingHTTPServer(("127.0.0.1", 18088), aws_vps_server.Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_health_endpoint(self):
        req = urllib.request.Request("http://127.0.0.1:18088/health")
        with urllib.request.urlopen(req) as res:
            self.assertEqual(res.status, 200)

    def test_instances_unauthorized(self):
        req = urllib.request.Request("http://127.0.0.1:18088/api/instances")
        try:
            urllib.request.urlopen(req)
            self.fail("Expected 401")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 401)

if __name__ == "__main__":
    unittest.main()
