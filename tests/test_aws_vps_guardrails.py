"""Read-only safety tests for the NeoOS AWS VPS API."""
import json
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

import aws_vps_server

PROTECTED = "i-0c4a3985afb8d417b"
GOOD_TOKEN = "t" * 40
LEAK = "arn:aws:iam::123456789012:role/NeoOS-Secret-Detail"


def instance(instance_id, state="running"):
    return {
        "InstanceId": instance_id,
        "State": {"Name": state},
        "ImageId": "ami-0dd60a46ecc6eac16",
        "InstanceType": "t3.micro",
        "PrivateIpAddress": "10.0.1.23",
        "Tags": [{"Key": "Name", "Value": instance_id}],
        "BlockDeviceMappings": [{"Ebs": {"VolumeSize": 8}}],
        "Placement": {"AvailabilityZone": "ap-southeast-2c"},
    }


class FakeEc2:
    def __init__(self, instances, error=None):
        self.instances = instances
        self.calls = []
        self.error = error

    def describe_instances(self, **kwargs):
        self.calls.append(("describe_instances", kwargs))
        if self.error:
            raise self.error
        return {"Reservations": [{"Instances": self.instances}]}


def aws_client_error():
    try:
        from botocore.exceptions import ClientError
        return ClientError({"Error": {"Code": "AccessDenied", "Message": LEAK}}, "DescribeInstances")
    except ImportError:
        return aws_vps_server.ClientError({"Error": {"Code": "AccessDenied", "Message": LEAK}})


class TestAwsVpsReadOnlySafety(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = aws_vps_server.ThreadingHTTPServer(("127.0.0.1", 18089), aws_vps_server.Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def request(self, path, method="GET", body=None, token=None, headers=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request("http://127.0.0.1:18089" + path, data=data, method=method)
        if token:
            req.add_header("Authorization", "Bearer " + token)
        for name, value in (headers or {}).items():
            req.add_header(name, value)
        try:
            with urllib.request.urlopen(req) as res:
                return res.status, res.read(), dict(res.headers)
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read(), dict(exc.headers)

    def authed(self, path, method="GET", body=None, fake=None):
        with mock.patch.object(aws_vps_server, "TOKEN", GOOD_TOKEN):
            return self.request(path, method, body, token=GOOD_TOKEN)

    def test_health_endpoint_needs_no_token(self):
        status, body, _ = self.request("/health")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["status"], "ok")

    def test_instance_listing_requires_the_bearer_token(self):
        fake = FakeEc2([instance(PROTECTED)])
        with mock.patch.object(aws_vps_server, "TOKEN", GOOD_TOKEN), \
                mock.patch.object(aws_vps_server, "ec2", fake):
            for token in (None, "wrong-token"):
                status, body, _ = self.request("/api/instances", token=token)
                self.assertEqual(status, 401, token)
                self.assertEqual(json.loads(body)["error"], "unauthorized")
            self.assertEqual(fake.calls, [])
            status, body, _ = self.request("/api/instances", token=GOOD_TOKEN)
        self.assertEqual(status, 200)
        self.assertEqual([item["id"] for item in json.loads(body)["instances"]], [PROTECTED])
        self.assertEqual([call[0] for call in fake.calls], ["describe_instances"])

    def test_listing_hides_private_ip(self):
        fake = FakeEc2([instance(PROTECTED), instance("i-0123456789abcdef0", "stopped")])
        with mock.patch.object(aws_vps_server, "TOKEN", GOOD_TOKEN), \
                mock.patch.object(aws_vps_server, "ec2", fake):
            status, body, _ = self.request("/api/instances", token=GOOD_TOKEN)
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual({item["id"] for item in data["instances"]}, {PROTECTED, "i-0123456789abcdef0"})
        for item in data["instances"]:
            self.assertNotIn("private_ip", item)
            self.assertNotIn("PrivateIpAddress", item)
        self.assertNotIn("10.0.1.23", body.decode())

    def test_missing_or_short_server_token_fails_closed(self):
        fake = FakeEc2([instance(PROTECTED)])
        for token in ("", "short-token"):
            with self.subTest(token_length=len(token)), \
                    mock.patch.object(aws_vps_server, "TOKEN", token), \
                    mock.patch.object(aws_vps_server, "ec2", fake):
                status, body, _ = self.request("/api/instances", token="anything-else-entirely")
                self.assertEqual(status, 503)
                self.assertEqual(json.loads(body)["error"], "server_token_not_configured")
                status, body, _ = self.request("/api/instances")
                self.assertEqual(status, 503)
                self.assertEqual(json.loads(body)["error"], "server_token_not_configured")
        self.assertEqual(fake.calls, [])

    def test_aws_error_text_is_not_returned_to_clients(self):
        fake = FakeEc2([instance(PROTECTED)], error=aws_client_error())
        with mock.patch.object(aws_vps_server, "TOKEN", GOOD_TOKEN), \
                mock.patch.object(aws_vps_server, "ec2", fake):
            status, body, _ = self.authed("/api/instances")
        text = body.decode()
        self.assertEqual(status, 502)
        self.assertEqual(json.loads(body)["error"], "aws_api_error")
        self.assertNotIn(LEAK, text)
        self.assertNotIn("AccessDenied", text)
        self.assertNotIn("detail", json.loads(body))

    def test_cors_echoes_only_configured_origins(self):
        allowed = "https://neoos-2.vercel.app"
        fake = FakeEc2([instance(PROTECTED)])
        with mock.patch.object(aws_vps_server, "TOKEN", GOOD_TOKEN), \
                mock.patch.object(aws_vps_server, "ORIGINS", {allowed}), \
                mock.patch.object(aws_vps_server, "ec2", fake):
            status, _, headers = self.request("/api/instances", token=GOOD_TOKEN,
                                              headers={"Origin": allowed})
            self.assertEqual(status, 200)
            self.assertEqual(headers.get("Access-Control-Allow-Origin"), allowed)
            self.assertEqual(headers.get("Vary"), "Origin")
            status, _, headers = self.request("/api/instances", token=GOOD_TOKEN,
                                              headers={"Origin": "https://evil.example"})
            self.assertNotIn("Access-Control-Allow-Origin", headers)
            status, body, headers = self.request("/api/instances", "OPTIONS",
                                                 headers={"Origin": "https://evil.example"})
            self.assertEqual(status, 403)
            self.assertEqual(json.loads(body)["error"], "origin_not_allowed")
            self.assertNotIn("Access-Control-Allow-Origin", headers)

    def test_wildcard_cors_is_not_the_default(self):
        self.assertTrue(not aws_vps_server.ORIGINS or "*" not in aws_vps_server.ORIGINS)
        status, _, headers = self.request("/api/instances", token=None,
                                          headers={"Origin": "https://anything.example"})
        self.assertNotIn("Access-Control-Allow-Origin", headers)

    def test_create_is_disabled_without_calling_aws(self):
        fake = FakeEc2([instance(PROTECTED)])
        with mock.patch.object(aws_vps_server, "TOKEN", GOOD_TOKEN), \
                mock.patch.object(aws_vps_server, "ec2", fake):
            status, body, _ = self.authed("/api/instances", "POST", {"name": "worker"})
        self.assertEqual(status, 405)
        self.assertEqual(json.loads(body)["error"], "control_actions_temporarily_disabled")
        self.assertEqual(fake.calls, [])

    def test_start_stop_reboot_are_disabled(self):
        fake = FakeEc2([instance("i-0123456789abcdef0")])
        with mock.patch.object(aws_vps_server, "TOKEN", GOOD_TOKEN), \
                mock.patch.object(aws_vps_server, "ec2", fake):
            for action in ("start", "stop", "reboot"):
                status, body, _ = self.authed(f"/api/instances/i-0123456789abcdef0/{action}", "POST", {})
                self.assertEqual(status, 405)
                self.assertEqual(json.loads(body)["error"], "control_actions_temporarily_disabled")
        self.assertEqual(fake.calls, [])

    def test_delete_is_disabled(self):
        fake = FakeEc2([instance("i-0123456789abcdef0")])
        with mock.patch.object(aws_vps_server, "TOKEN", GOOD_TOKEN), \
                mock.patch.object(aws_vps_server, "ec2", fake):
            status, body, _ = self.authed("/api/instances/i-0123456789abcdef0", "DELETE")
        self.assertEqual(status, 405)
        self.assertEqual(json.loads(body)["error"], "control_actions_temporarily_disabled")
        self.assertEqual(fake.calls, [])

    def test_quota_guardrail_still_caps_at_two(self):
        self.assertFalse(aws_vps_server.quota_blocks_creation(0))
        self.assertFalse(aws_vps_server.quota_blocks_creation(1))
        self.assertTrue(aws_vps_server.quota_blocks_creation(2))
        self.assertTrue(aws_vps_server.quota_blocks_creation(5))

    def test_no_embedded_credentials_or_hardcoded_backend(self):
        root = Path(__file__).resolve().parents[1]
        sources = [
            root / "aws_vps_server.py",
            root / "api" / "instances.js",
            root / "docs" / "api" / "instances.js",
            root / "docs" / "cloud" / "index.html",
            root / "README.md",
        ]
        combined = "\n".join(path.read_text(encoding="utf-8") for path in sources)
        self.assertNotIn("neoos2026" + "!", combined)
        self.assertNotIn("3.27.117.86", combined)
        self.assertNotIn("neoos-vps-api-token", combined)
        self.assertNotIn("DEFAULT_TOKEN", combined)
        self.assertNotIn("PasswordAuthentication yes", combined)
        self.assertNotIn('"private_ip"', combined)


if __name__ == "__main__":
    unittest.main()
