#!/usr/bin/env python3
"""Lightweight OpenAI-compatible terminal chat client for Termux and Linux."""
from __future__ import annotations
import getpass, json, os, urllib.error, urllib.request
from pathlib import Path
from typing import Any

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "openrouter/free"
SYSTEM_PROMPT = "You are a helpful, clear, friendly AI assistant. Reply in the user's language."

def config_dir() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "termux-ai"

def data_dir() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "termux-ai"

def config_path() -> Path:
    return config_dir() / "config.json"

def load_config() -> dict[str, Any]:
    p = config_path()
    if p.exists():
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(obj, dict):
                return obj
        except (OSError, json.JSONDecodeError):
            print(f"설정 파일을 읽지 못했어: {p}")
    return {}

def save_config(cfg: dict[str, Any]) -> None:
    p = config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        p.chmod(0o600)
    except OSError:
        pass

def setup_wizard(cfg: dict[str, Any]) -> dict[str, Any]:
    print("\nOpenAI 호환 API 설정이야. 기본 주소는 OpenRouter야.")
    print("기본 모델은 무료 라우터(openrouter/free)지만 무료 제공량 제한이 있을 수 있어.")
    base = input(f"API 주소 [{cfg.get('base_url', DEFAULT_BASE_URL)}]: ").strip()
    model = input(f"모델 [{cfg.get('model', DEFAULT_MODEL)}]: ").strip()
    key = getpass.getpass("API 키 (입력 내용은 화면에 표시되지 않아): ").strip()
    cfg.update({"base_url": (base or cfg.get("base_url") or DEFAULT_BASE_URL).rstrip("/"),
                "model": model or cfg.get("model") or DEFAULT_MODEL,
                "api_key": key or cfg.get("api_key", ""),
                "system_prompt": cfg.get("system_prompt", SYSTEM_PROMPT),
                "max_history_messages": 24})
    save_config(cfg)
    print(f"설정 저장 완료: {config_path()}\n")
    return cfg

def load_history() -> list[dict[str, str]]:
    p = data_dir() / "history.json"
    if not p.exists():
        return []
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            return [m for m in raw if isinstance(m, dict) and m.get("role") in {"user", "assistant"} and isinstance(m.get("content"), str)]
    except (OSError, json.JSONDecodeError):
        pass
    return []

def save_history(messages: list[dict[str, str]]) -> None:
    folder = data_dir()
    folder.mkdir(parents=True, exist_ok=True)
    p = folder / "history.json"
    p.write_text(json.dumps(messages[-80:], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        p.chmod(0o600)
    except OSError:
        pass

def ask_api(cfg: dict[str, Any], messages: list[dict[str, str]]) -> str:
    key = os.environ.get("TERMUX_AI_API_KEY") or os.environ.get("OPENROUTER_API_KEY") or cfg.get("api_key", "")
    if not key:
        raise RuntimeError("API 키가 없어. /setup 또는 환경 변수로 설정해 줘.")
    base = str(cfg.get("base_url", DEFAULT_BASE_URL)).rstrip("/")
    endpoint = base if base.endswith("/chat/completions") else base + "/chat/completions"
    payload = {"model": cfg.get("model", DEFAULT_MODEL), "messages": messages, "temperature": 0.7}
    req = urllib.request.Request(endpoint, data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                 "HTTP-Referer": "https://github.com/gw140427-rgb/Neoos-2",
                 "X-Title": "Termux AI"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=90) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1200]
        raise RuntimeError(f"API 오류 HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"네트워크 연결 오류: {exc.reason}") from exc
    except TimeoutError as exc:
        raise RuntimeError("요청 시간이 초과됐어. 잠시 후 다시 시도해 줘.") from exc
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("API 응답 형식을 확인할 수 없어: " + json.dumps(data, ensure_ascii=False)[:800]) from exc
    if isinstance(content, list):
        content = "\n".join(str(x.get("text", "")) if isinstance(x, dict) else str(x) for x in content)
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("AI가 빈 답변을 반환했어.")
    return content.strip()

def print_help() -> None:
    print("""명령어
  /help           도움말
  /model 이름     모델 변경
  /system 문장    시스템 안내문 변경
  /clear          현재 대화 초기화
  /setup          API 주소·모델·키 설정
  /save           대화 기록 저장
  /exit           종료""")

def main() -> int:
    cfg = load_config()
    if not cfg.get("base_url") or not cfg.get("model") or not (cfg.get("api_key") or os.environ.get("TERMUX_AI_API_KEY") or os.environ.get("OPENROUTER_API_KEY")):
        cfg = setup_wizard(cfg)
    system = str(cfg.get("system_prompt") or SYSTEM_PROMPT)
    messages = [{"role": "system", "content": system}] + load_history()[-int(cfg.get("max_history_messages", 24)):]
    print("\033[1;36m╭──────────────────────────────╮\033[0m")
    print("\033[1;36m│          TERMUX AI           │\033[0m")
    print("\033[1;36m╰──────────────────────────────╯\033[0m")
    print(f"모델: {cfg.get('model', DEFAULT_MODEL)} | /help 로 명령어 확인\n")
    while True:
        try:
            prompt = input("\033[1;32m나 > \033[0m").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n대화를 저장하고 종료할게.")
            break
        if not prompt:
            continue
        if prompt == "/exit":
            break
        if prompt == "/help":
            print_help(); continue
        if prompt == "/setup":
            cfg = setup_wizard(cfg); continue
        if prompt == "/save":
            save_history([m for m in messages if m["role"] != "system"])
            print("대화 기록을 저장했어."); continue
        if prompt == "/clear":
            messages = [{"role": "system", "content": system}]
            print("현재 대화를 초기화했어."); continue
        if prompt.startswith("/model "):
            model = prompt[7:].strip()
            if model:
                cfg["model"] = model; save_config(cfg); print(f"모델 변경: {model}")
            continue
        if prompt.startswith("/system "):
            system = prompt[8:].strip() or SYSTEM_PROMPT
            cfg["system_prompt"] = system; save_config(cfg)
            messages = [{"role": "system", "content": system}]
            print("시스템 안내문을 변경했어."); continue
        messages.append({"role": "user", "content": prompt})
        print("\033[1;33mAI가 답변 중...\033[0m")
        try:
            answer = ask_api(cfg, messages)
            messages.append({"role": "assistant", "content": answer})
            print(f"\033[1;36mAI >\033[0m {answer}\n")
            messages = [messages[0]] + messages[1:][-max(2, int(cfg.get("max_history_messages", 24))):]
        except (RuntimeError, ValueError) as exc:
            print(f"\033[1;31m오류:\033[0m {exc}\n")
    save_history([m for m in messages if m["role"] != "system"])
    print(f"기록 위치: {data_dir() / 'history.json'}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
