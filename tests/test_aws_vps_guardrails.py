"""Cost guardrail tests: the shared demo token must never be able to run up a bill."""
import json
import os
import threading
import time
import unittest
import urllib.error
import urllib.request
from unittest import mock

import aws_vps_server

AUTH = {"Authorization": "Bearer test-token-1234567890-secure-testing-token", "Content-Type": "application/json"}
PROTECTED = "i-0c4a3985afb8d417b"


def instance(instance_id, state="running"):
    return {
        "InstanceId": instance_id,
        "State": {"Name": state},
        "ImageId": "ami-0dd60a46ecc6eac16",
        "InstanceType": "t3.micro",
        "Tags": [{"Key": "Name", "Value": instance_id}],
        "BlockDeviceMappings": [{"Ebs": {"VolumeSize": 8}}],
        "Placement": {"AvailabilityZone": "ap-southeast-2c"},
    }


class FakeEc2:
    def __init__(self, instances):
        self.instances = instances
        self.calls = []

    def describe_instances(self, **kwargs):
        return {"Reservations": [{"Instances": self.instances}]}

    def run_instances(self, **kwargs):
        self.calls.append(("run_instances", kwargs))
        return {"Instances": [instance("i-0123456789abcdef0", "pending")]}

    def start_instances(self, InstanceIds):
        self.calls.append(("start_instances", InstanceIds))

    def stop_instances(self, InstanceIds):
        self.calls.append(("stop_instances", InstanceIds))

    def reboot_instances(self, InstanceIds):
        self.calls.append(("reboot_instances", InstanceIds))

    def terminate_instances(self, InstanceIds):
        self.calls.append(("terminate_instances", InstanceIds))


class TestAwsVpsGuardrails(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        aws_vps_server.TOKEN = "test-token-1234567890-secure-testing-token"
        cls.server = aws_vps_server.ThreadingHTTPServer(("127.0.0.1", 18089), aws_vps_server.Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def request(self, path, method="GET", body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request("http://127.0.0.1:18089" + path, data=data, headers=AUTH, method=method)
        try:
            with urllib.request.urlopen(req) as res:
                return res.status, res.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read()

    def test_cap_allows_second_instance_and_blocks_third(self):
        self.assertEqual(aws_vps_server.MAX_INSTANCES, 2)
        self.assertFalse(aws_vps_server.quota_blocks_creation(0))
        self.assertFalse(aws_vps_server.quota_blocks_creation(1))
        self.assertTrue(aws_vps_server.quota_blocks_creation(2))
        self.assertTrue(aws_vps_server.quota_blocks_creation(5))

    def test_creation_rejected_when_cap_reached(self):
        fake = FakeEc2([instance(PROTECTED), instance("i-0123456789abcdef0")])
        with mock.patch.object(aws_vps_server, "ec2", fake):
            status, body = self.request("/api/instances", "POST", {"name": "extra"})
        self.assertEqual(status, 409)
        self.assertEqual(json.loads(body)["error"], "instance_quota_exceeded")
        self.assertEqual(fake.calls, [])

    def test_creation_forces_cheap_spec_and_small_disk(self):
        fake = FakeEc2([instance(PROTECTED)])
        with mock.patch.object(aws_vps_server, "ec2", fake):
            status, _ = self.request(
                "/api/instances",
                "POST",
                {"name": "worker", "instance_type": "t3.xlarge", "volume_gb": 500},
            )
        self.assertEqual(status, 202)
        params = fake.calls[0][1]
        self.assertEqual(params["InstanceType"], "t3.micro")
        self.assertEqual(params["BlockDeviceMappings"][0]["Ebs"]["VolumeSize"], 8)
        self.assertNotIn("UserData", params)
        self.assertNotIn("PasswordAuthentication", str(params))

    def test_control_plane_cannot_be_stopped(self):
        fake = FakeEc2([instance(PROTECTED)])
        with mock.patch.object(aws_vps_server, "ec2", fake):
            status, body = self.request(f"/api/instances/{PROTECTED}/stop", "POST", {})
        self.assertEqual(status, 403)
        self.assertEqual(json.loads(body)["error"], "cannot_stop_primary_neoos_control_plane")
        self.assertEqual(fake.calls, [])

    def test_control_plane_cannot_be_terminated(self):
        fake = FakeEc2([instance(PROTECTED)])
        with mock.patch.object(aws_vps_server, "ec2", fake):
            status, _ = self.request(f"/api/instances/{PROTECTED}", "DELETE")
        self.assertEqual(status, 403)
        self.assertEqual(fake.calls, [])

    def test_worker_can_still_be_stopped_and_terminated(self):
        worker = "i-0123456789abcdef0"
        fake = FakeEc2([instance(worker)])
        with mock.patch.object(aws_vps_server, "ec2", fake):
            status, _ = self.request(f"/api/instances/{worker}/stop", "POST", {})
            self.assertEqual(status, 202)
            status, _ = self.request(f"/api/instances/{worker}", "DELETE")
            self.assertEqual(status, 202)
        self.assertEqual([c[0] for c in fake.calls], ["stop_instances", "terminate_instances"])


    def test_missing_or_short_server_token_fails_closed(self):
        for token in ("", "short"):

            with self.subTest(token_length=len(token)), mock.patch.object(aws_vps_server, "TOKEN", token):
                status, body = self.request("/api/instances")
                self.assertEqual(status, 503)
                self.assertEqual(json.loads(body)["error"], "server_token_not_configured")

    def test_no_embedded_credentials_or_password_bootstrap_remain(self):
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        sources = [
            root / "aws_vps_server.py",
            root / "api" / "instances.js",
            root / "docs" / "api" / "instances.js",
            root / "docs" / "vps" / "aws.html",
        ]
        combined = "\n".join(path.read_text(encoding="utf-8") for path in sources)
        self.assertNotIn('os.environ.get("NEOOS_VPS_API_TOKEN", DEFAULT_TOKEN)', combined)
        self.assertNotIn("process.env.NEOOS_API_TOKEN ||", combined)
        self.assertNotIn("neoos2026" + "!", combined)
        self.assertNotIn("PasswordAuthentication yes", combined)
        self.assertNotIn("DEFAULT_TOKEN", combined)

    def test_wildcard_cors_is_not_enabled_by_default(self):
        self.assertNotIn("*", aws_vps_server.ORIGINS)
if __name__ == "__main__":
    unittest.main()
