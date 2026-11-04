#!/usr/bin/env python3
"""NeoOS AWS EC2 VPS API.

Runs with an attached AWS IAM role (no access keys in source or browser).
Only instances tagged Project=NeoOS and ManagedBy=NeoOS are visible/manageable.
"""
from __future__ import annotations

import hmac
import json
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

import boto3
from botocore.exceptions import BotoCoreError, ClientError

REGION = os.environ.get("AWS_REGION", "ap-northeast-2")
TOKEN = os.environ.get("NEOOS_VPS_API_TOKEN", "").strip()
ORIGINS = {x.strip().rstrip("/") for x in os.environ.get("NEOOS_ALLOWED_ORIGINS", "").split(",") if x.strip()}
AMI_ID = os.environ.get("NEOOS_EC2_AMI_ID", "").strip()
SUBNET_ID = os.environ.get("NEOOS_EC2_SUBNET_ID", "").strip()
SECURITY_GROUP_ID = os.environ.get("NEOOS_EC2_SECURITY_GROUP_ID", "").strip()
KEY_NAME = os.environ.get("NEOOS_EC2_KEY_NAME", "").strip()
INSTANCE_PROFILE = os.environ.get("NEOOS_EC2_INSTANCE_PROFILE", "").strip()
ALLOWED_TYPES = {x.strip() for x in os.environ.get("NEOOS_ALLOWED_INSTANCE_TYPES", "t3.micro").split(",") if x.strip()}
MAX_VOLUME_GB = int(os.environ.get("NEOOS_MAX_VOLUME_GB", "20"))
ec2 = boto3.client("ec2", region_name=REGION)
MANAGED_FILTERS = [
    {"Name": "tag:Project", "Values": ["NeoOS"]},
    {"Name": "tag:ManagedBy", "Values": ["NeoOS"]},
]


def json_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False).encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    server_version = "NeoOS-AWS-VPS/1.0"

    def log_message(self, fmt: str, *args: object) -> None:
        # Never log request headers (which may contain the bearer token).
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
        if origin and origin in ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        super().end_headers()

    def authorized(self) -> bool:
        if len(TOKEN) < 32:
            self.send_json(503, {"error": "server_token_not_configured"})
            return False
        origin = self.headers.get("Origin", "").rstrip("/")
        if origin and origin not in ORIGINS:
            self.send_json(403, {"error": "origin_not_allowed"})
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
            raise ValueError("request_body_must_be_1_to_8192_bytes")
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
        return {
            "id": item["InstanceId"],
            "name": tags.get("Name", item["InstanceId"]),
            "state": item.get("State", {}).get("Name", "unknown"),
            "type": item.get("InstanceType", ""),
            "public_ip": item.get("PublicIpAddress"),
            "private_ip": item.get("PrivateIpAddress"),
            "az": item.get("Placement", {}).get("AvailabilityZone"),
            "created": item.get("LaunchTime").isoformat() if item.get("LaunchTime") else None,
        }

    def do_OPTIONS(self) -> None:
        origin = self.headers.get("Origin", "").rstrip("/")
        if origin and origin not in ORIGINS:
            self.send_json(403, {"error": "origin_not_allowed"})
            return
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
        if not self.authorized():
            return
        try:
            response = ec2.describe_instances(Filters=MANAGED_FILTERS)
            instances = [
                self.instance_view(instance)
                for reservation in response.get("Reservations", [])
                for instance in reservation.get("Instances", [])
            ]
            self.send_json(200, {"provider": "aws", "region": REGION, "instances": instances})
        except (ClientError, BotoCoreError) as exc:
            self.send_json(502, {"error": "aws_api_error", "message": type(exc).__name__})

    def do_POST(self) -> None:
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
            operation = {"start": "start_instances", "stop": "stop_instances", "reboot": "reboot_instances"}[action]
            getattr(ec2, operation)(InstanceIds=[instance_id])
            self.send_json(202, {"accepted": True, "id": instance_id, "action": action})
        except ValueError as exc:
            self.send_json(400, {"error": str(exc)})
        except (ClientError, BotoCoreError) as exc:
            self.send_json(502, {"error": "aws_api_error", "message": type(exc).__name__})

    def create_instance(self, data: dict) -> None:
        # Fail closed until the operator has explicitly configured the network,
        # Debian AMI, and SSH key pair. The API never creates permissive security groups.
        missing = [key for key, value in {
            "NEOOS_EC2_AMI_ID": AMI_ID,
            "NEOOS_EC2_SUBNET_ID": SUBNET_ID,
            "NEOOS_EC2_SECURITY_GROUP_ID": SECURITY_GROUP_ID,
            "NEOOS_EC2_KEY_NAME": KEY_NAME,
        }.items() if not value]
        if missing:
            self.send_json(503, {"error": "aws_vps_not_configured", "missing": missing})
            return
        name = str(data.get("name", "NeoOS Debian")).strip()
        if not name or len(name) > 48 or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 ._-]*", name):
            raise ValueError("name_must_be_1_to_48_safe_characters")
        instance_type = str(data.get("instance_type", "t3.micro"))
        if instance_type not in ALLOWED_TYPES:
            raise ValueError("instance_type_not_allowed")
        try:
            volume_gb = int(data.get("volume_gb", 12))
        except (TypeError, ValueError):
            raise ValueError("volume_gb_must_be_an_integer")
        if not 8 <= volume_gb <= MAX_VOLUME_GB:
            raise ValueError(f"volume_gb_must_be_between_8_and_{MAX_VOLUME_GB}")
        params = {
            "ImageId": AMI_ID,
            "InstanceType": instance_type,
            "MinCount": 1,
            "MaxCount": 1,
            "KeyName": KEY_NAME,
            "SubnetId": SUBNET_ID,
            "SecurityGroupIds": [SECURITY_GROUP_ID],
            "BlockDeviceMappings": [{
                "DeviceName": "/dev/xvda",
                "Ebs": {"VolumeSize": volume_gb, "VolumeType": "gp3", "Encrypted": True, "DeleteOnTermination": True},
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
        if INSTANCE_PROFILE:
            params["IamInstanceProfile"] = {"Name": INSTANCE_PROFILE}
        result = ec2.run_instances(**params)
        instance = result["Instances"][0]
        self.send_json(202, {"accepted": True, "instance": self.instance_view(instance)})

    def do_DELETE(self) -> None:
        if not self.authorized():
            return
        match = re.fullmatch(r"/api/instances/(i-[0-9a-f]{8,17})", urlsplit(self.path).path)
        if not match:
            self.send_json(404, {"error": "not_found"})
            return
        instance_id = match.group(1)
        try:
            if not self.managed_instance(instance_id):
                self.send_json(404, {"error": "managed_instance_not_found"})
                return
            ec2.terminate_instances(InstanceIds=[instance_id])
            self.send_json(202, {"accepted": True, "id": instance_id, "action": "terminate"})
        except (ClientError, BotoCoreError) as exc:
            self.send_json(502, {"error": "aws_api_error", "message": type(exc).__name__})


def main() -> int:
    if len(TOKEN) < 32:
        raise SystemExit("Set NEOOS_VPS_API_TOKEN to a random secret of at least 32 characters.")
    if not ORIGINS:
        raise SystemExit("Set NEOOS_ALLOWED_ORIGINS to the exact dashboard origin.")
    if MAX_VOLUME_GB < 8 or MAX_VOLUME_GB > 100:
        raise SystemExit("NEOOS_MAX_VOLUME_GB must be between 8 and 100.")
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8080"))
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"NeoOS AWS EC2 API listening on {host}:{port} in {REGION}")
    print("Uses the attached IAM role; only NeoOS-tagged instances are managed.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
