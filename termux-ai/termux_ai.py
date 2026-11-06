#!/usr/bin/env python3
"""Termux AI: a small OpenAI-compatible chat client for Termux and Python."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

APP_NAME = "Termux AI"
DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "openrouter/free"
CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "termux-ai"
CONFIG_FILE = CONFIG_DIR / "config.json"
MAX_HISTORY_MESSAGES = 20
TIMEOUT_SECONDS = 90


def normalize_base_url(value: str) -> str:
    """Validate and normalize an OpenAI-compatible API base URL."""
    value = value.strip().rstrip("/")
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme not in {"https", "http"} or not parsed.netloc:
        raise ValueError("URL은 https:// 또는 로컬 http:// 주소로 입력해 주세요.")
    if parsed.username or parsed.password:
        raise ValueError("URL에 사용자 이름이나 비밀번호를 넣지 마세요.")
    if parsed.path.endswith("/chat/completions"):
        value = value[: -len("/chat/completions")]
        parsed = urllib.parse.urlparse(value)
    local_hosts = {"localhost", "127.0.0.1", "::1"}
    if parsed.scheme == "http" and (parsed.hostname or "").lower() not in local_hosts:
        raise ValueError("보안을 위해 HTTPS 주소만 허용합니다. HTTP는 localhost에서만 사용할 수 있어요.")
    return value


def endpoint_for(base_url: str) -> str:
    base_url = normalize_base_url(base_url)
    return base_url + "/chat/completions"


def save_config(config: dict[str, str]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(CONFIG_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(config, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        raise
    try:
        CONFIG_FILE.chmod(0o600)
    except OSError:
        pass


def load_config() -> dict[str, str]:
    if not CONFIG_FILE.exists():
        raise FileNotFoundError("설정이 없습니다. 먼저 'termux-ai setup'을 실행해 주세요.")
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"설정 파일을 읽을 수 없습니다: {exc}") from exc
    base_url = normalize_base_url(str(data.get("base_url", DEFAULT_BASE_URL)))
    model = str(data.get("model", DEFAULT_MODEL)).strip()
    api_key = str(data.get("api_key", "")).strip()
    if not model:
        raise ValueError("모델 이름이 비어 있습니다. 'termux-ai setup'으로 다시 설정해 주세요.")
    if "openrouter.ai" in urllib.parse.urlparse(base_url).hostname and model != "openrouter/free" and not model.endswith(":free"):
        raise ValueError("무료 전용 설정입니다. OpenRouter에서는 openrouter/free 또는 :free 모델만 사용할 수 있어요.")
    host = (urllib.parse.urlparse(base_url).hostname or "").lower()
    is_local = host in {"localhost", "127.0.0.1", "::1"}
    if not api_key and not is_local:
        raise ValueError("API 키가 없습니다. 'termux-ai setup'으로 설정해 주세요.")
    return {"base_url": base_url, "model": model, "api_key": api_key}


def setup() -> None:
    print(f"\n{APP_NAME} 설정\n" + "─" * 28)
    print("기본값은 OpenRouter 무료 모델 라우터입니다.")
    base_input = input(f"API 주소 [{DEFAULT_BASE_URL}]: ").strip() or DEFAULT_BASE_URL
    base_url = normalize_base_url(base_input)
    model_default = DEFAULT_MODEL if base_url == DEFAULT_BASE_URL else ""
    model = input(f"모델 이름 [{model_default or '직접 입력'}]: ").strip() or model_default
    if not model:
        raise ValueError("모델 이름을 입력해 주세요.")
    if "openrouter.ai" in urllib.parse.urlparse(base_url).hostname and model != "openrouter/free" and not model.endswith(":free"):
        raise ValueError("무료 전용 설정입니다. openrouter/free 또는 :free 모델을 선택해 주세요.")

    host = (urllib.parse.urlparse(base_url).hostname or "").lower()
    is_local = host in {"localhost", "127.0.0.1", "::1"}
    if is_local:
        api_key = getpass.getpass("API 키 (로컬 서버라면 비워도 됨): ").strip()
    else:
        api_key = getpass.getpass("API 키 (입력 내용은 화면에 표시되지 않음): ").strip()
        if not api_key:
            raise ValueError("HTTPS API를 사용하려면 API 키가 필요합니다.")

    save_config({"base_url": base_url, "model": model, "api_key": api_key})
    print(f"\n설정 저장 완료: {CONFIG_FILE}")
    print("키 파일 권한은 가능한 환경에서 소유자 전용(600)으로 설정했어요.")


def extract_text(payload: dict[str, Any]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("서버 응답에 choices 항목이 없습니다.")
    message = choices[0].get("message", {})
    content = message.get("content", "")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "\n".join(parts).strip()
    return str(content).strip()


def request_chat(config: dict[str, str], messages: list[dict[str, str]]) -> str:
    body = {
        "model": config["model"],
        "messages": messages,
        "stream": False,
        "temperature": 0.7,
        "max_tokens": 1200,
    }
    headers = {"Content-Type": "application/json", "User-Agent": "termux-ai/1.0"}
    if config["api_key"]:
        headers["Authorization"] = "Bearer " + config["api_key"]
    if "openrouter.ai" in urllib.parse.urlparse(config["base_url"]).hostname:
        headers["X-Title"] = "Termux AI"

    request = urllib.request.Request(
        endpoint_for(config["base_url"]),
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            raw = response.read().decode("utf-8", errors="replace")
        return extract_text(json.loads(raw))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1200]
        try:
            parsed = json.loads(detail)
            detail = parsed.get("error", {}).get("message", detail)
        except (json.JSONDecodeError, AttributeError):
            pass
        raise RuntimeError(f"서버 오류 HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"네트워크 연결 실패: {exc.reason}") from exc
    except TimeoutError as exc:
        raise RuntimeError("요청 시간이 초과됐어요. 잠시 후 다시 시도해 주세요.") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("서버가 올바른 JSON 응답을 보내지 않았어요.") from exc


def print_help() -> None:
    print("\n명령어")
    print("  /help    도움말 보기")
    print("  /reset   현재 대화 내용 초기화")
    print("  /model   현재 모델 표시")
    print("  /exit    종료")
    print("\n대화를 시작하려면 메시지를 입력하세요.\n")


def chat(config: dict[str, str]) -> None:
    history: list[dict[str, str]] = []
    print(f"\n{APP_NAME} 1.0  |  모델: {config['model']}")
    print("종료: /exit  ·  도움말: /help\n")
    while True:
        try:
            user_text = input("나 > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nTermux AI를 종료합니다.")
            break
        if not user_text:
            continue
        command = user_text.lower()
        if command in {"/exit", "/quit"}:
            print("Termux AI를 종료합니다.")
            break
        if command == "/help":
            print_help()
            continue
        if command == "/reset":
            history.clear()
            print("대화 문맥을 초기화했어요.\n")
            continue
        if command == "/model":
            print(f"현재 모델: {config['model']}\n")
            continue

        history.append({"role": "user", "content": user_text})
        history = history[-MAX_HISTORY_MESSAGES:]
        print("AI > 생각 중...", flush=True)
        try:
            answer = request_chat(config, history)
        except (RuntimeError, ValueError) as exc:
            history.pop()
            print(f"오류: {exc}\n")
            continue
        history.append({"role": "assistant", "content": answer})
        history = history[-MAX_HISTORY_MESSAGES:]
        print("\rAI > " + (answer or "(응답 내용이 비어 있어요.)") + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Termux용 가벼운 AI 채팅 프로그램")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("setup", help="API 주소, 모델, 키 설정")
    subparsers.add_parser("chat", help="대화 시작")
    ask_parser = subparsers.add_parser("ask", help="한 번 질문하고 답변 받기")
    ask_parser.add_argument("prompt", nargs="+", help="질문 내용")
    args = parser.parse_args()

    try:
        if args.command == "setup":
            setup()
            return 0
        config = load_config()
        if args.command == "ask":
            print(request_chat(config, [{"role": "user", "content": " ".join(args.prompt)}]))
        else:
            chat(config)
        return 0
    except (FileNotFoundError, ValueError, OSError) as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\n취소했어요.", file=sys.stderr)
        return 130
    except RuntimeError as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
