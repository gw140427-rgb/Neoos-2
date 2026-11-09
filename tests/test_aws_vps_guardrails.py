"""Read-only safety tests for the NeoOS AWS VPS API."""
import json
import threading
import time
import unittest
import urllib.error
import urllib.request
from unittest import mock

import aws_vps_server

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
        self.calls.append(("describe_instances", kwargs))
        return {"Reservations": [{"Instances": self.instances}]}


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

    def request(self, path, method="GET", body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request("http://127.0.0.1:18089" + path, data=data, method=method)
        try:
            with urllib.request.urlopen(req) as res:
                return res.status, res.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read()

    def test_instance_listing_is_read_only_and_does_not_require_client_secret(self):
        fake = FakeEc2([instance(PROTECTED), instance("i-0123456789abcdef0", "stopped")])
        with mock.patch.object(aws_vps_server, "ec2", fake):
            status, body = self.request("/api/instances")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual({item["id"] for item in data["instances"]}, {PROTECTED, "i-0123456789abcdef0"})
        self.assertEqual([call[0] for call in fake.calls], ["describe_instances"])

    def test_create_is_disabled_without_calling_aws(self):
        fake = FakeEc2([instance(PROTECTED)])
        with mock.patch.object(aws_vps_server, "ec2", fake):
            status, body = self.request("/api/instances", "POST", {"name": "worker"})
        self.assertEqual(status, 405)
        self.assertEqual(json.loads(body)["error"], "control_actions_temporarily_disabled")
        self.assertEqual(fake.calls, [])

    def test_start_stop_reboot_are_disabled(self):
        fake = FakeEc2([instance("i-0123456789abcdef0")])
        with mock.patch.object(aws_vps_server, "ec2", fake):
            for action in ("start", "stop", "reboot"):
                status, body = self.request(f"/api/instances/i-0123456789abcdef0/{action}", "POST", {})
                self.assertEqual(status, 405)
                self.assertEqual(json.loads(body)["error"], "control_actions_temporarily_disabled")
        self.assertEqual(fake.calls, [])

    def test_delete_is_disabled(self):
        fake = FakeEc2([instance("i-0123456789abcdef0")])
        with mock.patch.object(aws_vps_server, "ec2", fake):
            status, body = self.request("/api/instances/i-0123456789abcdef0", "DELETE")
        self.assertEqual(status, 405)
        self.assertEqual(json.loads(body)["error"], "control_actions_temporarily_disabled")
        self.assertEqual(fake.calls, [])

    def test_quota_guardrail_still_caps_at_two(self):
        self.assertFalse(aws_vps_server.quota_blocks_creation(0))
        self.assertFalse(aws_vps_server.quota_blocks_creation(1))
        self.assertTrue(aws_vps_server.quota_blocks_creation(2))
        self.assertTrue(aws_vps_server.quota_blocks_creation(5))


if __name__ == "__main__":
    unittest.main()
