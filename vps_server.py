#!/usr/bin/env python3
"""NeoOS Podroid status API (read-only, bearer-token protected)."""
from __future__ import annotations

import hmac
import json
import os
import socket
import subprocess
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit


def configured_origins() -> set[str]:
    raw = os.environ.get("NEOOS_ALLOWED_ORIGINS", "")
    return {item.strip().rstrip("/") for item in raw.split(",") if item.strip()}


def configured_token() -> str:
    return os.environ.get("NEOOS_VPS_API_TOKEN", "").strip()


def running_containers() -> list[str]:
    """Return running Docker container names without invoking a shell."""
    result = subprocess.run(
        ["docker", "ps", "--format", "{{.Names}}"],
        check=True,
        capture_output=True,
        text=True,
        timeout=5,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


class VPSHandler(BaseHTTPRequestHandler):
    server_version = "NeoOS-VPS-Status/2.0"

    def log_message(self, fmt: str, *args: object) -> None:
        # Keep logs useful without echoing request headers or bearer tokens.
        super().log_message(fmt, *args)

    def _send_json(self, status: int, payload: dict[str, object]) -> None:
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
        origin = self.headers.get("Origin", "").rstrip("/")
        allowed = configured_origins()
        if origin and origin in allowed:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
            if self.headers.get("Access-Control-Request-Private-Network", "").lower() == "true":
                self.send_header("Access-Control-Allow-Private-Network", "true")
        super().end_headers()

    def do_OPTIONS(self) -> None:
        origin = self.headers.get("Origin", "").rstrip("/")
        if origin and origin not in configured_origins():
            self._send_json(403, {"error": "origin_not_allowed"})
            return
        self.send_response(204)
        self.send_header("Content-Length", "0")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def _authorized(self) -> bool:
        expected = configured_token()
        if len(expected) < 32:
            self._send_json(503, {"error": "server_token_not_configured", "message": "Set NEOOS_VPS_API_TOKEN to at least 32 characters."})
            return False

        authorization = self.headers.get("Authorization", "")
        scheme, separator, supplied = authorization.partition(" ")
        if not separator or scheme.lower() != "bearer" or not hmac.compare_digest(supplied.strip(), expected):
            self._send_json(401, {"error": "unauthorized"})
            return False
        return True

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path == "/health":
            self._send_json(200, {"status": "ok", "service": "neoos-vps-status"})
            return
        if path not in {"/", "/api/status"}:
            self._send_json(404, {"error": "not_found"})
            return
        if not self._authorized():
            return
        try:
            names = running_containers()
        except (OSError, subprocess.SubprocessError) as exc:
            self._send_json(503, {
                "error": "docker_unavailable",
                "message": f"Docker status could not be read ({type(exc).__name__}).",
            })
            return

        self._send_json(200, {
            "node": os.environ.get("NEOOS_NODE_NAME", socket.gethostname()),
            "engine": "Docker",
            "running_vps": len(names),
            "list": names,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "mode": "read_only",
        })

    def do_POST(self) -> None:
        self._send_json(405, {"error": "read_only_api", "message": "This API does not create, stop, or delete containers."})

    def do_PUT(self) -> None:
        self._send_json(405, {"error": "method_not_allowed"})

    def do_DELETE(self) -> None:
        self._send_json(405, {"error": "method_not_allowed"})


def main() -> int:
    token = configured_token()
    if len(token) < 32:
        raise SystemExit("Set NEOOS_VPS_API_TOKEN to a random secret of at least 32 characters before starting the server.")
    origins = configured_origins()
    if not origins:
        raise SystemExit("Set NEOOS_ALLOWED_ORIGINS to the exact HTTPS origin of the NeoOS dashboard (no path).")
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8080"))
    server = ThreadingHTTPServer((host, port), VPSHandler)
    print(f"NeoOS read-only VPS status API listening on {host}:{port}")
    print(f"Allowed browser origins: {', '.join(sorted(origins))}")
    print("Container creation/deletion and shell execution are disabled.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping NeoOS VPS status API.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
