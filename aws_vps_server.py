#!/usr/bin/env python3
"""NeoOS AWS EC2 VPS API Server.

Runs on AWS EC2 with attached IAM Role (NeoOS-EC2-SSM-Role).
Provides real REST API endpoints for provisioning, listing, rebooting, stopping,
and terminating managed EC2 instances tagged with Project=NeoOS.
"""
from __future__ import annotations

import hmac
import json
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

try:
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError
except ImportError:
    boto3 = None
    class BotoCoreError(Exception): pass
    class ClientError(Exception): pass

REGION = os.environ.get("AWS_REGION", "ap-southeast-2")
TOKEN = ""
ORIGINS = {x.strip().rstrip("/") for x in os.environ.get("NEOOS_ALLOWED_ORIGINS", "*").split(",") if x.strip()}

SUBNET_ID = os.environ.get("NEOOS_EC2_SUBNET_ID", "subnet-00aabf5e5f73895da").strip()
SECURITY_GROUP_ID = os.environ.get("NEOOS_EC2_SECURITY_GROUP_ID", "sg-0716aa2cc0376be39").strip()
KEY_NAME = os.environ.get("NEOOS_EC2_KEY_NAME", "neoos-key").strip()
INSTANCE_PROFILE = os.environ.get("NEOOS_EC2_INSTANCE_PROFILE", "NeoOS-EC2-SSM-Role").strip()
ALLOWED_TYPES = {x.strip() for x in os.environ.get("NEOOS_ALLOWED_INSTANCE_TYPES", "t3.micro,t3.nano").split(",") if x.strip()}
# Hard cost guardrails: the shared API token is a demo credential, so the server
# itself caps what anyone holding it can ever create or destroy.
FIXED_INSTANCE_TYPE = os.environ.get("NEOOS_FIXED_INSTANCE_TYPE", "t3.micro").strip()
FIXED_VOLUME_GB = int(os.environ.get("NEOOS_FIXED_VOLUME_GB", "8"))
MAX_INSTANCES = int(os.environ.get("NEOOS_MAX_INSTANCES", "2"))
PROTECTED_INSTANCE_IDS = {
    x.strip() for x in os.environ.get("NEOOS_PROTECTED_INSTANCE_IDS", "i-0c4a3985afb8d417b").split(",") if x.strip()
}

AMI_MAP = {
    "ubuntu": os.environ.get("NEOOS_EC2_UBUNTU_AMI", "ami-0dd60a46ecc6eac16"),
    "debian": os.environ.get("NEOOS_EC2_DEBIAN_AMI", "ami-0c8ee5714a9238c0f"),
    "alpine": os.environ.get("NEOOS_EC2_ALPINE_AMI", "ami-0dd60a46ecc6eac16"), # fallback to ubuntu for stability
}

ec2 = boto3.client("ec2", region_name=REGION) if boto3 else None
MANAGED_FILTERS = [
    {"Name": "tag:Project", "Values": ["NeoOS"]},
    {"Name": "tag:ManagedBy", "Values": ["NeoOS"]},
]


def json_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False).encode("utf-8")


def active_managed_instances() -> list:
    """Every non-terminated instance the NeoOS account manages right now."""
    response = ec2.describe_instances(Filters=MANAGED_FILTERS)
    return [
        instance
        for reservation in response.get("Reservations", [])
        for instance in reservation.get("Instances", [])
        if instance.get("State", {}).get("Name") != "terminated"
    ]


def quota_blocks_creation(active_count: int) -> bool:
    """True when another instance would exceed the hard cap."""
    return active_count >= MAX_INSTANCES


class Handler(BaseHTTPRequestHandler):
    server_version = "NeoOS-AWS-VPS/2.0"

    def log_message(self, fmt: str, *args: object) -> None:
        super().log_message(fmt, *args)

    def send_json(self, status: int, value: object) -> None:
        body = json_bytes(value)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def end_headers(self) -> None:
        origin = self.headers.get("Origin", "").rstrip("/")
        if origin and (origin in ORIGINS or "*" in ORIGINS):
            self.send_header("Access-Control-Allow-Origin", origin)
        elif "*" in ORIGINS or not ORIGINS:
            self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        super().end_headers()

    def authorized(self) -> bool:
        if len(TOKEN) < 16:
            self.send_json(503, {"error": "server_token_not_configured"})
            return False
        scheme, sep, supplied = self.headers.get("Authorization", "").partition(" ")
        if not sep or scheme.lower() != "bearer" or not hmac.compare_digest(supplied.strip(), TOKEN):
            self.send_json(401, {"error": "unauthorized"})
            return False
        return True

    def read_body(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise ValueError("invalid_content_length")
        if length < 1 or length > 8192:
            return {}
        data = json.loads(self.rfile.read(length))
        if not isinstance(data, dict):
            raise ValueError("json_object_required")
        return data

    def managed_instance(self, instance_id: str) -> dict | None:
        if not re.fullmatch(r"i-[0-9a-f]{8,17}", instance_id):
            return None
        response = ec2.describe_instances(
            InstanceIds=[instance_id],
            Filters=MANAGED_FILTERS,
        )
        for reservation in response.get("Reservations", []):
            for instance in reservation.get("Instances", []):
                return instance
        return None

    def instance_view(self, item: dict) -> dict:
        tags = {t["Key"]: t["Value"] for t in item.get("Tags", [])}
        os_label = "Ubuntu 26.04 LTS"
        icon = "🐧"
        ami_id = item.get("ImageId", "")
        if ami_id == AMI_MAP.get("debian"):
            os_label = "Debian 12 Bookworm"
            icon = "🌀"

        return {
            "id": item["InstanceId"],
            "name": tags.get("Name", item["InstanceId"]),
            "state": item.get("State", {}).get("Name", "unknown"),
            "os": os_label,
            "icon": icon,
            "spec": f"{item.get('InstanceType', 't3.micro')} (2 vCPU / 1GB RAM)",
            "ip": item.get("PublicIpAddress") or "할당 중...",
            "private_ip": item.get("PrivateIpAddress"),
            "region": item.get("Placement", {}).get("AvailabilityZone") or REGION,
            "storage": f"{(item.get('BlockDeviceMappings') or [{}])[0].get('Ebs', {}).get('VolumeSize', 8) if (item.get('BlockDeviceMappings') or [{}]) else 8}GB gp3 EBS",
            "uptime": item.get("LaunchTime").isoformat() if item.get("LaunchTime") else "알 수 없음",
            "isReal": True
        }

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path == "/health":
            self.send_json(200, {"status": "ok", "provider": "aws", "region": REGION})
            return
        if path != "/api/instances":
            self.send_json(404, {"error": "not_found"})
            return
        try:
            response = ec2.describe_instances(Filters=MANAGED_FILTERS)
            instances = [
                self.instance_view(instance)
                for reservation in response.get("Reservations", [])
                for instance in reservation.get("Instances", [])
                if instance.get("State", {}).get("Name") != "terminated"
            ]
            self.send_json(200, {"provider": "aws", "region": REGION, "instances": instances})
        except (ClientError, BotoCoreError) as exc:
            self.send_json(502, {"error": "aws_api_error", "message": type(exc).__name__, "detail": str(exc)})

    def do_POST(self) -> None:
        self.send_json(405, {"error": "control_actions_temporarily_disabled"})
        return
        if not self.authorized():
            return
        path = urlsplit(self.path).path
        try:
            data = self.read_body()
            if path == "/api/instances":
                self.create_instance(data)
                return
            match = re.fullmatch(r"/api/instances/(i-[0-9a-f]{8,17})/(start|stop|reboot)", path)
            if not match:
                self.send_json(404, {"error": "not_found"})
                return
            instance_id, action = match.groups()
            if not self.managed_instance(instance_id):
                self.send_json(404, {"error": "managed_instance_not_found"})
                return
            if action == "stop" and instance_id in PROTECTED_INSTANCE_IDS:
                self.send_json(403, {"error": "cannot_stop_primary_neoos_control_plane", "id": instance_id})
                return
            operation = {"start": "start_instances", "stop": "stop_instances", "reboot": "reboot_instances"}[action]
            getattr(ec2, operation)(InstanceIds=[instance_id])
            self.send_json(202, {"accepted": True, "id": instance_id, "action": action})
        except ValueError as exc:
            self.send_json(400, {"error": str(exc)})
        except (ClientError, BotoCoreError) as exc:
            self.send_json(502, {"error": "aws_api_error", "message": type(exc).__name__, "detail": str(exc)})

    def create_instance(self, data: dict) -> None:
        name = str(data.get("name", "NeoOS Worker")).strip()
        if not name or len(name) > 48:
            name = "NeoOS Worker"

        try:
            active_count = len(active_managed_instances())
        except (ClientError, BotoCoreError) as exc:
            self.send_json(502, {"error": "aws_api_error", "message": type(exc).__name__, "detail": str(exc)})
            return
        if quota_blocks_creation(active_count):
            self.send_json(409, {
                "error": "instance_quota_exceeded",
                "message": f"NeoOS 계정은 최대 {MAX_INSTANCES}대까지만 운영할 수 있어. 기존 인스턴스를 삭제한 뒤 다시 시도해줘.",
                "limit": MAX_INSTANCES,
                "active": active_count,
            })
            return

        os_choice = str(data.get("os", "ubuntu")).lower()
        ami_id = AMI_MAP.get(os_choice, AMI_MAP["ubuntu"])
        # Cost guardrail: the spec and disk are fixed, whatever the client asks for.
        instance_type = FIXED_INSTANCE_TYPE
        volume_gb = FIXED_VOLUME_GB

        user_data_script = """#!/bin/bash\nset -eu\n# Require EC2 key-pair authentication; never set a shared default password.\nif [ -f /etc/ssh/sshd_config ]; then\n  sed -i -E "s/^#?PasswordAuthentication .*/PasswordAuthentication no/" /etc/ssh/sshd_config\n  sed -i -E "s/^#?KbdInteractiveAuthentication .*/KbdInteractiveAuthentication no/" /etc/ssh/sshd_config\n  printf "PasswordAuthentication no\\nKbdInteractiveAuthentication no\\n" > /etc/ssh/sshd_config.d/01-neoos-key-only.conf\n  systemctl restart ssh || systemctl restart sshd || true\nfi\n"""

        params = {
            "ImageId": ami_id,
            "InstanceType": instance_type,
            "MinCount": 1,
            "MaxCount": 1,
            "KeyName": KEY_NAME,
            "SubnetId": SUBNET_ID,
            "SecurityGroupIds": [SECURITY_GROUP_ID],
            "UserData": user_data_script,
            "BlockDeviceMappings": [{
                "DeviceName": "/dev/sda1" if "debian" in os_choice else "/dev/xvda",
                "Ebs": {"VolumeSize": volume_gb, "VolumeType": "gp3", "DeleteOnTermination": True},
            }],
            "TagSpecifications": [{
                "ResourceType": "instance",
                "Tags": [
                    {"Key": "Name", "Value": name},
                    {"Key": "Project", "Value": "NeoOS"},
                    {"Key": "ManagedBy", "Value": "NeoOS"},
                ],
            }],
        }
        # Note: Do not attach IamInstanceProfile to worker instances to avoid requiring iam:PassRole
        result = ec2.run_instances(**params)
        instance = result["Instances"][0]
        self.send_json(202, {"accepted": True, "instance": self.instance_view(instance)})

    def do_DELETE(self) -> None:
        self.send_json(405, {"error": "control_actions_temporarily_disabled"})
        return
        if not self.authorized():
            return
        match = re.fullmatch(r"/api/instances/(i-[0-9a-f]{8,17})", urlsplit(self.path).path)
        if not match:
            self.send_json(404, {"error": "not_found"})
            return
        instance_id = match.group(1)
        if instance_id in PROTECTED_INSTANCE_IDS:
            self.send_json(403, {"error": "cannot_terminate_primary_neoos_control_plane"})
            return
        try:
            if not self.managed_instance(instance_id):
                self.send_json(404, {"error": "managed_instance_not_found"})
                return
            ec2.terminate_instances(InstanceIds=[instance_id])
            self.send_json(202, {"accepted": True, "id": instance_id, "action": "terminate"})
        except (ClientError, BotoCoreError) as exc:
            self.send_json(502, {"error": "aws_api_error", "message": type(exc).__name__, "detail": str(exc)})


def main() -> int:
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8080"))
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"NeoOS AWS EC2 API listening on {host}:{port} in {REGION}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
