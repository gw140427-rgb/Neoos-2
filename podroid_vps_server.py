#!/usr/bin/env python3
"""NeoOS Podroid VPS API.

A small Pterodactyl-style panel backend for the phone: it drives the Docker
daemon that runs inside Podroid and exposes the container list, creation,
start/stop/reboot/delete, live CPU/RAM numbers, published ports and a one-shot
web terminal over plain HTTP.

Safety rules kept in this file:
  * Docker is always invoked with an argument list. No shell is ever spawned
    for container management, and the web terminal only reaches Docker through
    ``docker exec <container> sh -c <cmd>``.
  * Container names and ids are validated against strict patterns before they
    reach Docker, so no option/flag injection is possible.
  * Guest containers are isolated (``--cap-drop=ALL``, no-new-privileges),
    capped (memory/CPU/PID limits, fixed slot count) and short-lived: they
    carry ``neoos.managed=guest`` plus ``neoos.expires_at`` and a reaper thread
    removes them once the TTL passes.
  * Containers NeoOS did not create (``neoos.managed`` is not ``guest``), the
    control plane (``PROTECTED_CONTAINERS``, default ``box``) and anything
    named with ``user-vps-`` are never stopped, deleted or expired.
  * Only the Python standard library is used.
"""
from __future__ import annotations

import hmac
import json
import os
import re
import socket
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TOKEN = os.environ.get("NEOOS_API_TOKEN", "").strip()
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8080"))
NODE_NAME = os.environ.get("NEOOS_NODE_NAME", "Podroid").strip() or "Podroid"

MAX_CONTAINERS = int(os.environ.get("MAX_CONTAINERS", "4"))
TTL_SECONDS = int(os.environ.get("NEOOS_TTL_SECONDS", "1800"))
REAPER_INTERVAL = int(os.environ.get("NEOOS_REAPER_INTERVAL", "60"))

PROTECTED_CONTAINERS = {
    item.strip()
    for item in os.environ.get("PROTECTED_CONTAINERS", "box").split(",")
    if item.strip()
}
PROTECTED_PREFIXES = tuple(
    item.strip()
    for item in os.environ.get("PROTECTED_PREFIXES", "user-vps-").split(",")
    if item.strip()
)
# Only containers carrying this label are NeoOS guests; everything else is
# treated as somebody else's workload and left alone.
MANAGED_LABEL = "neoos.managed"
MANAGED_VALUE = "guest"
EXPIRES_LABEL = "neoos.expires_at"

# Browser origins that may call this API directly. The deployed console lives on
# Vercel; local previews run on localhost/127.0.0.1 on any port.
BASE_ORIGINS = {"https://neoos-2.vercel.app"}
EXTRA_ORIGINS = {
    item.strip().rstrip("/")
    for item in os.environ.get("NEOOS_ALLOWED_ORIGINS", "").split(",")
    if item.strip()
}
LOCAL_ORIGIN_RE = re.compile(r"^https?://(localhost|127\.0\.0\.1)(:\d{1,5})?$")

# Docker container names: alphanumeric first character, 2..31 characters total.
NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{1,30}$")
# Any container id or name accepted in a URL path segment.
REF_RE = re.compile(r"^[a-zA-Z0-9_.-]{2,64}$")

OS_IMAGES = {
    "alpine": "alpine:latest",
    "ubuntu": "ubuntu:24.04",
    "debian": "debian:bookworm-slim",
    "busybox": "busybox:1.36",
    "node": "node:22-alpine",
    "python": "python:3.13-alpine",
    "nginx": "nginx:alpine",
}
OS_LABELS = {
    "alpine": ("Alpine Linux", "🏔️"),
    "ubuntu": ("Ubuntu 24.04 LTS", "🐧"),
    "debian": ("Debian 12 Bookworm", "🌀"),
    "busybox": ("BusyBox Linux", "📦"),
    "node": ("Node.js 22 Alpine", "🟩"),
    "python": ("Python 3.13 Alpine", "🐍"),
    "nginx": ("Nginx Alpine", "🌐"),
}

MEMORY_LIMIT = "256m"
MEMORY_LABEL = "256MB"
CPU_LIMIT = "0.5"
PIDS_LIMIT = "64"
CONTAINER_PORT = 80
PORT_RANGE = range(8101, 8200)

EXEC_TIMEOUT = 10
EXEC_MAX_OUTPUT = 8192
EXEC_MAX_COMMAND = 512

PS_FORMAT = (
    "{{.ID}}|{{.Names}}|{{.State}}|{{.Image}}|{{.RunningFor}}|{{.Status}}|{{.Ports}}|{{.Labels}}"
)
STATS_FORMAT = "{{.ID}}|{{.CPUPerc}}|{{.MemUsage}}"

STATE_MAP = {
    "running": "running",
    "restarting": "running",
    "paused": "paused",
    "created": "stopped",
    "exited": "stopped",
    "dead": "stopped",
    "removing": "stopped",
}

PORT_MAPPING_RE = re.compile(r"(\d+)->(\d+)/(tcp|udp)")
ACTION_PATTERN = "start|stop|reboot|pause|unpause|exec"
ACTIONS = {
    "start": "start",
    "stop": "stop",
    "reboot": "restart",
    "pause": "pause",
    "unpause": "unpause",
}


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def origin_allowed(origin: str) -> bool:
    """True only for the console origin and local previews (never '*')."""
    candidate = (origin or "").strip().rstrip("/")
    if not candidate:
        return False
    if candidate in BASE_ORIGINS or candidate in EXTRA_ORIGINS:
        return True
    return bool(LOCAL_ORIGIN_RE.fullmatch(candidate))


def docker(args: list, timeout: int = 20) -> subprocess.CompletedProcess:
    """Run one docker command with an argument list (never a shell)."""
    return subprocess.run(
        ["docker", *args],
        check=True,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def parse_labels(raw: str) -> dict:
    """`neoos.managed=guest,neoos.expires_at=17..` -> dict."""
    labels = {}
    for item in (raw or "").split(","):
        key, separator, value = item.partition("=")
        key = key.strip()
        if separator and key:
            labels[key] = value.strip()
    return labels


def normalize_ports(raw: str) -> str:
    """`0.0.0.0:8101->80/tcp, :::8101->80/tcp` -> `8101->80/tcp`."""
    seen = []
    for host_port, container_port, proto in PORT_MAPPING_RE.findall(raw or ""):
        item = f"{host_port}->{container_port}/{proto}"
        if item not in seen:
            seen.append(item)
    return ", ".join(seen)


def parse_ps(output: str) -> list:
    """Split `docker ps --format` rows into field lists."""
    rows = []
    for line in (output or "").splitlines():
        if not line.strip():
            continue
        parts = line.split("|")
        if len(parts) < 7:
            continue
        rows.append([part.strip() for part in parts[:8]])
    return rows


def list_containers() -> list:
    """Every container on the phone, running or not."""
    result = docker(["ps", "-a", "--format", PS_FORMAT], timeout=20)
    return parse_ps(result.stdout)


def container_stats() -> dict:
    """Live CPU/RAM per container id.

    `docker stats` can fail or be slow while a container is starting, so a
    failure here degrades to empty numbers instead of breaking the list.
    """
    try:
        result = docker(
            ["stats", "--no-stream", "--format", STATS_FORMAT],
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return {}
    stats = {}
    for line in (result.stdout or "").splitlines():
        parts = line.split("|")
        if len(parts) != 3:
            continue
        container_id = parts[0].strip()
        if not container_id:
            continue
        stats[container_id] = {
            "cpu": parts[1].strip() or "—",
            "mem": parts[2].strip() or "—",
        }
    return stats


def row_labels(row: list) -> dict:
    return parse_labels(row[7] if len(row) > 7 else "")


def used_host_ports(rows: list) -> set:
    ports = set()
    for row in rows:
        for host_port, _container_port, _proto in PORT_MAPPING_RE.findall(row[6] if len(row) > 6 else ""):
            ports.add(int(host_port))
    return ports


def pick_host_port(used: set) -> int | None:
    """First free host port in 8101..8199 (free in Docker and on the host)."""
    for port in PORT_RANGE:
        if port in used:
            continue
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            # No SO_REUSEPORT: an active listener must make the bind fail.
            probe.bind(("127.0.0.1", port))
        except OSError:
            continue
        finally:
            probe.close()
        return port
    return None


def protection_reason(row: list) -> str | None:
    """Why this container must not be stopped, deleted or expired (or None)."""
    name = row[1]
    if name in PROTECTED_CONTAINERS:
        return "protected_container"
    if PROTECTED_PREFIXES and name.startswith(PROTECTED_PREFIXES):
        return "protected_prefix"
    if row_labels(row).get(MANAGED_LABEL) != MANAGED_VALUE:
        return "unmanaged_container"
    return None


def expires_at(row: list) -> int | None:
    raw = row_labels(row).get(EXPIRES_LABEL, "")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def instance_view(row: list, stats: dict, now: float | None = None) -> dict:
    now = time.time() if now is None else now
    container_id, name, state, image, running_for, status, ports = row[:7]
    labels = row_labels(row)
    image_key = (image or "").split(":")[0].split("/")[-1]
    os_label, icon = OS_LABELS.get(image_key, (image or "Linux", "🧱"))
    metrics = stats.get(container_id, {})
    deadline = expires_at(row)
    ttl_left = max(0, int(deadline - now)) if deadline else None
    return {
        "id": container_id,
        "name": name,
        "state": STATE_MAP.get((state or "").lower(), "unknown"),
        "docker_state": state,
        "os": os_label,
        "icon": icon,
        "spec": f"{CPU_LIMIT} vCPU / {MEMORY_LABEL} RAM",
        "ip": "할당 없음 (Podroid 로컬)",
        "ports": normalize_ports(ports) or "—",
        "region": NODE_NAME,
        "storage": "컨테이너 레이어",
        "uptime": running_for or status or "알 수 없음",
        "cpu": metrics.get("cpu", "—"),
        "mem": metrics.get("mem", "—"),
        "managed": labels.get(MANAGED_LABEL, ""),
        "expires_at": deadline,
        "ttl_seconds": ttl_left,
        "protected": protection_reason(row) is not None,
        "isReal": True,
    }


def resolve_container(rows: list, ref: str) -> list | None:
    """Find one container by exact name or by a unique id prefix."""
    by_name = [row for row in rows if row[1] == ref]
    if by_name:
        return by_name[0]
    by_id = [row for row in rows if row[0] == ref or row[0].startswith(ref)]
    if len(by_id) == 1:
        return by_id[0]
    return None


def clip_output(text) -> tuple:
    """Cap terminal output at EXEC_MAX_OUTPUT characters."""
    value = text or ""
    if isinstance(value, bytes):
        value = value.decode("utf-8", "replace")
    if len(value) <= EXEC_MAX_OUTPUT:
        return value, False
    return value[:EXEC_MAX_OUTPUT] + "\n…(출력 8192자 초과로 잘림)", True


def cleanup_expired_containers(now: float | None = None) -> list:
    """Remove guest containers whose TTL has passed; returns removed names."""
    now = time.time() if now is None else now
    removed = []
    try:
        rows = list_containers()
    except (OSError, subprocess.SubprocessError):
        return removed
    for row in rows:
        deadline = expires_at(row)
        if deadline is None or deadline > now:
            continue
        if row_labels(row).get(MANAGED_LABEL) != MANAGED_VALUE:
            continue
        if protection_reason(row) is not None:
            continue
        try:
            docker(["rm", "-f", row[1]], timeout=45)
        except (OSError, subprocess.SubprocessError):
            continue
        removed.append(row[1])
    return removed


def reaper_loop(interval: int = REAPER_INTERVAL) -> None:
    """Background janitor: expired guest containers never outlive their TTL."""
    while True:
        time.sleep(interval)
        try:
            removed = cleanup_expired_containers()
        except Exception:  # a janitor must never take the API down
            continue
        for name in removed:
            print(f"[neoos] ttl_expired: removed {name}")


# --------------------------------------------------------------------------- #
# HTTP handler
# --------------------------------------------------------------------------- #
class Handler(BaseHTTPRequestHandler):
    server_version = "NeoOS-Podroid-VPS/3.1"

    def log_message(self, fmt: str, *args: object) -> None:
        # Keep logs useful without echoing request headers or bearer tokens.
        super().log_message(fmt, *args)

    # -- response helpers ---------------------------------------------------
    def send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(body)

    def end_headers(self) -> None:
        # Echo an allowed origin only; never answer with "*".
        origin = self.headers.get("Origin", "").rstrip("/")
        if origin and origin_allowed(origin):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        super().end_headers()

    def request_path(self) -> str:
        path = (self.path or "/").split("?", 1)[0]
        return path.rstrip("/") or "/"

    def docker_failed(self, exc: Exception) -> None:
        """Log the Docker failure on the phone; answer with a generic message."""
        detail = ""
        stderr = getattr(exc, "stderr", "") or ""
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", "replace")
        if stderr.strip():
            detail = stderr.strip().splitlines()[-1][:300]
        self.log_error("docker_error: %s: %s", type(exc).__name__, detail or "(no stderr)")
        payload = {
            "error": "docker_error",
            "message": "도커 명령을 실행하지 못했어. Podroid에서 Docker가 켜져 있는지 확인해 줘.",
            "reason": type(exc).__name__,
        }
        returncode = getattr(exc, "returncode", None)
        if isinstance(returncode, int):
            payload["exit_code"] = returncode
        if detail:
            payload["detail"] = detail
        self.send_json(500, payload)

    def authorized(self) -> bool:
        """Fail closed unless a strong server-side bearer token is configured."""
        if len(TOKEN) < 32:
            self.send_json(
                503,
                {
                    "error": "server_token_not_configured",
                    "message": "Set NEOOS_API_TOKEN to a random secret of at least 32 characters.",
                },
            )
            return False
        scheme, separator, supplied = self.headers.get("Authorization", "").partition(" ")
        if (
            not separator
            or scheme.lower() != "bearer"
            or not hmac.compare_digest(supplied.strip(), TOKEN)
        ):
            self.send_json(401, {"error": "unauthorized"})
            return False
        return True

    def read_body(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise ValueError("invalid_content_length")
        if length < 1:
            return {}
        if length > 16384:
            raise ValueError("body_too_large")
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ValueError("invalid_json")
        if not isinstance(data, dict):
            raise ValueError("json_object_required")
        return data

    # -- routes -------------------------------------------------------------
    def do_OPTIONS(self) -> None:
        origin = self.headers.get("Origin", "").rstrip("/")
        if origin and not origin_allowed(origin):
            self.send_json(403, {"error": "origin_not_allowed"})
            return
        self.send_response(204)
        self.send_header("Content-Length", "0")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def do_GET(self) -> None:
        path = self.request_path()
        if path == "/health":
            # Public on purpose: only says that the panel process is alive.
            self.send_json(200, {"status": "ok", "provider": "podroid"})
            return
        logs_match = re.fullmatch(r"/api/instances/([^/]+)/logs", path)
        if logs_match:
            if not self.authorized():
                return
            self.container_logs(logs_match.group(1))
            return
        if path != "/api/instances":
            self.send_json(404, {"error": "not_found"})
            return
        if not self.authorized():
            return
        try:
            rows = list_containers()
        except (OSError, subprocess.SubprocessError) as exc:
            self.docker_failed(exc)
            return
        stats = container_stats()
        now = time.time()
        guests = [row for row in rows if row_labels(row).get(MANAGED_LABEL) == MANAGED_VALUE]
        self.send_json(
            200,
            {
                "provider": "podroid",
                "node": NODE_NAME,
                "region": NODE_NAME,
                "max_containers": MAX_CONTAINERS,
                # Slots count guest containers only: the phone's own containers
                # must not eat a visitor's slot.
                "capacity": {"used": len(guests), "max": MAX_CONTAINERS},
                "containers": len(rows),
                "instances": [instance_view(row, stats, now) for row in rows],
            },
        )

    def do_POST(self) -> None:
        path = self.request_path()
        if path == "/api/instances":
            if not self.authorized():
                return
            self.create_container()
            return
        match = re.fullmatch(r"/api/instances/([^/]+)/(" + ACTION_PATTERN + r")", path)
        if not match:
            if re.fullmatch(r"/api/instances/[^/]+", path):
                self.send_json(405, {"error": "method_not_allowed"})
            else:
                self.send_json(404, {"error": "not_found"})
            return
        if not self.authorized():
            return
        ref, action = match.groups()
        if action == "exec":
            self.exec_in_container(ref)
        else:
            self.container_action(ref, action)

    def do_DELETE(self) -> None:
        path = self.request_path()
        if path == "/api/instances":
            self.send_json(405, {"error": "method_not_allowed"})
            return
        match = re.fullmatch(r"/api/instances/([^/]+)", path)
        if not match:
            self.send_json(404, {"error": "not_found"})
            return
        if not self.authorized():
            return
        self.delete_container(match.group(1))

    def do_PUT(self) -> None:
        self.send_json(405, {"error": "method_not_allowed"})

    def do_PATCH(self) -> None:
        self.send_json(405, {"error": "method_not_allowed"})

    # -- operations ---------------------------------------------------------
    def create_container(self) -> None:
        try:
            data = self.read_body()
        except ValueError as exc:
            self.send_json(400, {"error": str(exc)})
            return

        name = str(data.get("name", "")).strip()
        if not NAME_RE.fullmatch(name):
            self.send_json(
                400,
                {
                    "error": "invalid_name",
                    "message": "이름은 영문/숫자로 시작하는 2~31자(영문·숫자·_ . -)여야 해.",
                },
            )
            return

        os_choice = str(data.get("os", "ubuntu")).strip().lower()
        image = OS_IMAGES.get(os_choice)
        if not image:
            self.send_json(
                400,
                {
                    "error": "unsupported_os",
                    "message": "지원 OS: alpine, ubuntu, debian",
                    "supported": sorted(OS_IMAGES),
                },
            )
            return

        # This is a Docker container, not a full VM disk. Its writable layer
        # persists across stop/start but is removed with the container.
        try:
            rows = list_containers()
        except (OSError, subprocess.SubprocessError) as exc:
            self.docker_failed(exc)
            return

        guests = [row for row in rows if row_labels(row).get(MANAGED_LABEL) == MANAGED_VALUE]
        if len(guests) >= MAX_CONTAINERS:
            # Slot model: every visitor shares a fixed number of guests.
            self.send_json(
                429,
                {
                    "error": "capacity_full",
                    "message": "현재 서버 슬롯이 가득 찼습니다. 잠시 후 다시 시도해 주세요.",
                    "capacity": {"used": len(guests), "max": MAX_CONTAINERS},
                },
            )
            return
        if any(row[1] == name for row in rows):
            self.send_json(
                409,
                {"error": "container_name_taken", "name": name, "message": "이미 같은 이름의 컨테이너가 있어."},
            )
            return

        host_port = pick_host_port(used_host_ports(rows))
        if host_port is None:
            self.send_json(
                409,
                {"error": "no_free_port", "message": "8101~8199 사이에 남는 포트가 없어."},
            )
            return

        expires = int(time.time()) + TTL_SECONDS
        # Fixed limits and isolation: the phone's kernel is shared with the
        # guest's neighbours, so capabilities are dropped entirely.
        command = [
            "run",
            "-d",
            "--name",
            name,
            "-p",
            f"127.0.0.1:{host_port}:{CONTAINER_PORT}",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            f"--memory={MEMORY_LIMIT}",
            f"--cpus={CPU_LIMIT}",
            f"--pids-limit={PIDS_LIMIT}",
            "--label",
            f"{MANAGED_LABEL}={MANAGED_VALUE}",
            "--label",
            f"{EXPIRES_LABEL}={expires}",
            image,
            *(
                ["nginx", "-g", "daemon off;"]
                if os_choice == "nginx"
                else ["sh", "-c", "while true; do sleep 3600; done"]
            ),
        ]
        try:
            docker(command, timeout=180)
        except (OSError, subprocess.SubprocessError) as exc:
            self.docker_failed(exc)
            return

        # Report what Docker actually shows, so ports and state are real.
        try:
            reloaded = list_containers()
        except (OSError, subprocess.SubprocessError):
            reloaded = []
        fresh = [row for row in reloaded if row[1] == name]
        used = len([row for row in reloaded if row_labels(row).get(MANAGED_LABEL) == MANAGED_VALUE]) or len(guests) + 1
        if fresh:
            view = instance_view(fresh[0], container_stats())
        else:
            os_label, icon = OS_LABELS[os_choice]
            view = {
                "id": name,
                "name": name,
                "state": "running",
                "docker_state": "running",
                "os": os_label,
                "icon": icon,
                "spec": f"{CPU_LIMIT} vCPU / {MEMORY_LABEL} RAM",
                "ip": "할당 없음 (Podroid 로컬)",
                "ports": f"{host_port}->{CONTAINER_PORT}/tcp",
                "region": NODE_NAME,
                "storage": "컨테이너 레이어",
                "uptime": "방금 시작",
                "cpu": "—",
                "mem": "—",
                "managed": MANAGED_VALUE,
                "expires_at": expires,
                "ttl_seconds": TTL_SECONDS,
                "protected": False,
                "isReal": True,
            }
        self.send_json(
            202,
            {
                "accepted": True,
                "provider": "podroid",
                "instance": view,
                "storage": "컨테이너 쓰기 레이어 (삭제 시 함께 삭제)",
                "ttl_seconds": TTL_SECONDS,
                "capacity": {"used": used, "max": MAX_CONTAINERS},
            },
        )

    def container_action(self, ref: str, action: str) -> None:
        if not REF_RE.fullmatch(ref):
            self.send_json(400, {"error": "invalid_container_id"})
            return
        try:
            rows = list_containers()
        except (OSError, subprocess.SubprocessError) as exc:
            self.docker_failed(exc)
            return
        target = resolve_container(rows, ref)
        if target is None:
            self.send_json(404, {"error": "container_not_found", "id": ref})
            return
        name = target[1]
        reason = protection_reason(target)
        if reason is not None:
            self.send_json(
                403,
                {
                    "error": "protected_container",
                    "id": name,
                    "reason": reason,
                    "message": "NeoOS가 관리하는 게스트 컨테이너만 조작할 수 있어.",
                },
            )
            return
        try:
            docker([ACTIONS[action], name], timeout=45)
        except (OSError, subprocess.SubprocessError) as exc:
            self.docker_failed(exc)
            return
        self.send_json(
            202,
            {"accepted": True, "id": name, "action": action, "container_id": target[0]},
        )

    def exec_in_container(self, ref: str) -> None:
        if not REF_RE.fullmatch(ref):
            self.send_json(400, {"error": "invalid_container_id"})
            return
        try:
            data = self.read_body()
        except ValueError as exc:
            self.send_json(400, {"error": str(exc)})
            return
        command = str(data.get("cmd", "")).strip()
        if not command:
            self.send_json(400, {"error": "invalid_command", "message": "cmd가 비어 있어."})
            return
        if len(command) > EXEC_MAX_COMMAND:
            self.send_json(
                400,
                {"error": "command_too_long", "message": f"cmd는 {EXEC_MAX_COMMAND}자까지야."},
            )
            return
        if "\x00" in command:
            self.send_json(400, {"error": "invalid_command"})
            return

        try:
            rows = list_containers()
        except (OSError, subprocess.SubprocessError) as exc:
            self.docker_failed(exc)
            return
        target = resolve_container(rows, ref)
        if target is None:
            self.send_json(404, {"error": "container_not_found", "id": ref})
            return
        name = target[1]
        reason = protection_reason(target)
        if reason is not None:
            self.send_json(
                403,
                {"error": "protected_container", "id": name, "reason": reason},
            )
            return
        if STATE_MAP.get((target[2] or "").lower()) != "running":
            self.send_json(409, {"error": "container_not_running", "id": name})
            return

        # `sh -c` keeps shell features (pipes, env, &&) working like a terminal.
        # Guest containers mount nothing from the phone, so a command's reach
        # stops at the container boundary.
        try:
            result = docker(["exec", name, "sh", "-c", command], timeout=EXEC_TIMEOUT)
            code = result.returncode
            raw_out, raw_err = result.stdout, result.stderr
        except subprocess.CalledProcessError as exc:
            code = exc.returncode
            raw_out, raw_err = exc.stdout, exc.stderr
        except subprocess.TimeoutExpired as exc:
            stdout, stdout_cut = clip_output(exc.stdout)
            stderr, stderr_cut = clip_output(exc.stderr)
            self.send_json(
                504,
                {
                    "error": "exec_timeout",
                    "message": f"{EXEC_TIMEOUT}초 안에 끝나지 않았어. 긴 작업은 백그라운드로 돌려 줘.",
                    "id": name,
                    "cmd": command,
                    "exit_code": None,
                    "stdout": stdout,
                    "stderr": stderr,
                    "truncated": stdout_cut or stderr_cut,
                },
            )
            return
        except (OSError, subprocess.SubprocessError) as exc:
            self.docker_failed(exc)
            return

        stdout, stdout_cut = clip_output(raw_out)
        stderr, stderr_cut = clip_output(raw_err)
        self.send_json(
            200,
            {
                "id": name,
                "cmd": command,
                "exit_code": code,
                "stdout": stdout,
                "stderr": stderr,
                "truncated": stdout_cut or stderr_cut,
            },
        )

    def container_logs(self, ref: str) -> None:
        """Return recent logs from one NeoOS-managed guest only."""
        if not REF_RE.fullmatch(ref):
            self.send_json(400, {"error": "invalid_container_id"})
            return
        try:
            rows = list_containers()
        except (OSError, subprocess.SubprocessError) as exc:
            self.docker_failed(exc)
            return
        target = resolve_container(rows, ref)
        if target is None:
            self.send_json(404, {"error": "container_not_found", "id": ref})
            return
        reason = protection_reason(target)
        if reason is not None:
            self.send_json(403, {"error": "protected_container", "id": target[1], "reason": reason})
            return
        try:
            result = docker(["logs", "--tail", "100", target[1]], timeout=15)
        except (OSError, subprocess.SubprocessError) as exc:
            self.docker_failed(exc)
            return
        stdout, stdout_cut = clip_output(result.stdout)
        stderr, stderr_cut = clip_output(result.stderr)
        combined = stdout
        if stderr:
            combined = (combined + "\\n" + stderr).strip()
        logs, cut = clip_output(combined)
        self.send_json(
            200,
            {"id": target[1], "logs": logs, "truncated": stdout_cut or stderr_cut or cut},
        )

    def delete_container(self, ref: str) -> None:
        if not REF_RE.fullmatch(ref):
            self.send_json(400, {"error": "invalid_container_id"})
            return
        try:
            rows = list_containers()
        except (OSError, subprocess.SubprocessError) as exc:
            self.docker_failed(exc)
            return
        target = resolve_container(rows, ref)
        if target is None:
            self.send_json(404, {"error": "container_not_found", "id": ref})
            return
        name = target[1]
        reason = protection_reason(target)
        if reason is not None:
            # Hard guard: the control plane and anything NeoOS did not create.
            self.send_json(
                403,
                {
                    "error": "protected_container",
                    "id": name,
                    "reason": reason,
                    "message": "NeoOS가 관리하는 게스트 컨테이너만 삭제할 수 있어.",
                },
            )
            return
        try:
            docker(["rm", "-f", name], timeout=45)
        except (OSError, subprocess.SubprocessError) as exc:
            self.docker_failed(exc)
            return
        self.send_json(
            202,
            {"accepted": True, "id": name, "action": "delete", "container_id": target[0]},
        )


def main() -> int:
    if len(TOKEN) < 32:
        raise SystemExit(
            "Set NEOOS_API_TOKEN to a random secret of at least 32 characters before starting the server."
        )
    print(f"NeoOS Podroid VPS API listening on {HOST}:{PORT} (node: {NODE_NAME})")
    print(
        f"Slots: {MAX_CONTAINERS} · guest TTL: {TTL_SECONDS}s · "
        f"protected: {', '.join(sorted(PROTECTED_CONTAINERS)) or 'none'}"
        + (f" · prefixes: {', '.join(PROTECTED_PREFIXES)}" if PROTECTED_PREFIXES else "")
    )
    janitor = threading.Thread(target=reaper_loop, name="neoos-ttl-reaper", daemon=True)
    janitor.start()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping NeoOS Podroid VPS API.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
