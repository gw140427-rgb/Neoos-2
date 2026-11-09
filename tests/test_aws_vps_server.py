import unittest
import urllib.request
import urllib.error
import threading
import time
import aws_vps_server


class TestAwsVpsServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
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

    def test_instance_mutation_is_disabled(self):
        req = urllib.request.Request("http://127.0.0.1:18088/api/instances", data=b"{}", method="POST")
        try:
            urllib.request.urlopen(req)
            self.fail("Expected 405")
        except urllib.error.HTTPError as exc:
            self.assertEqual(exc.code, 405)


if __name__ == "__main__":
    unittest.main()
