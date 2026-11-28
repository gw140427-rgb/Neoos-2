"""NeoOS AI chat backend. Serves the locally created Ollama models over HTTP."""

import collections
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

MODELS = {
    "neo-1-plus": "neo-1-plus:latest",
    "neo-1": "neo-1:latest",
}
DEFAULT_MODEL = "neo-1-plus"
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434/api/chat")
TIMEOUT = int(os.environ.get("NEO_TIMEOUT", "50"))
MAX_MESSAGES = 12
RATE_LIMIT = int(os.environ.get("NEO_RATE_LIMIT", "40"))
RATE_WINDOW = int(os.environ.get("NEO_RATE_WINDOW", "600"))

_busy = threading.Lock()
_rate_lock = threading.Lock()
_rate_hits = collections.defaultdict(collections.deque)


def rate_limited(ip):
    now = time.monotonic()
    with _rate_lock:
        hits = _rate_hits[ip]
        while hits and now - hits[0] > RATE_WINDOW:
            hits.popleft()
        if len(hits) >= RATE_LIMIT:
            return True
        hits.append(now)
        if len(_rate_hits) > 1000:
            for key in [key for key, value in _rate_hits.items() if not value]:
                del _rate_hits[key]
        return False


def valid_messages(raw):
    if not isinstance(raw, list) or not raw or len(raw) > MAX_MESSAGES:
        return None
    result = []
    for item in raw:
        if not isinstance(item, dict):
            return None
        role = item.get("role")
        content = item.get("content")
        if role not in ("user", "assistant", "system") or not isinstance(content, str):
            return None
        if not content.strip():
            return None
        result.append({"role": role, "content": content[:4000]})
    return result


def generate(model, messages):
    payload = json.dumps({
        "model": MODELS[model],
        "messages": messages,
        "stream": False,
    }).encode("utf-8")
    request = Request(OLLAMA_URL, data=payload, headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=TIMEOUT) as response:
        body = json.loads(response.read().decode("utf-8"))
    text = (body.get("message") or {}).get("content", "").strip()
    if "</think>" in text:
        text = text.split("</think>", 1)[1].strip()
    return text


class Handler(BaseHTTPRequestHandler):
    server_version = "NeoAI/2.0"

    def log_message(self, fmt, *args):
        pass

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Cache-Control", "no-store")

    def _json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/health":
            self._json(200, {"ok": True, "models": list(MODELS), "model": DEFAULT_MODEL})
        elif path == "/":
            self._json(200, {"ok": True, "name": "NeoOS AI"})
        else:
            self._json(404, {"error": "not_found"})

    def do_POST(self):
        if urlparse(self.path).path != "/chat":
            self._json(404, {"error": "not_found"})
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0 or length > 100000:
                self._json(400, {"error": "bad_request"})
                return
            data = json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            self._json(400, {"error": "bad_request"})
            return
        model = data.get("model", DEFAULT_MODEL)
        if model not in MODELS:
            self._json(400, {"error": "unknown_model"})
            return
        messages = valid_messages(data.get("messages"))
        if messages is None:
            self._json(400, {"error": "bad_messages"})
            return
        if rate_limited(self.client_address[0]):
            self._json(429, {"error": "rate_limited"})
            return
        if not _busy.acquire(blocking=False):
            self._json(429, {"error": "busy"})
            return
        started = time.monotonic()
        try:
            reply = generate(model, messages)
            self._json(200, {"reply": reply, "model": model, "elapsed": round(time.monotonic() - started, 2)})
        except HTTPError as exc:
            code = 503 if exc.code == 404 else 502
            self._json(code, {"error": "model_unavailable" if code == 503 else "backend_error"})
        except (URLError, TimeoutError, OSError, ValueError, KeyError):
            self._json(502, {"error": "backend_unreachable"})
        finally:
            _busy.release()


def main():
    host = os.environ.get("NEO_HOST", "0.0.0.0")
    port = int(os.environ.get("NEO_PORT", "8091"))
    server = ThreadingHTTPServer((host, port), Handler)
    print("Neo AI backend on %s:%d (models: %s)" % (host, port, ", ".join(MODELS)), flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
