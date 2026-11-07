"""Policy-gated, local-first NeoOS development runner.

This is an execution controller, not an LLM or a security sandbox. It accepts
plans containing named actions only; arbitrary shell commands are never read
from a plan. Execution requires an explicit CLI approval flag.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

VERSION = 1
MAX_STEPS = 20
MAX_RETRIES = 3
MAX_PLAN_RUNTIME_SECONDS = 24 * 60 * 60
MAX_STEP_TIMEOUT_SECONDS = 600
ALLOWED_ACTIONS = {"compile", "test", "git_status"}


def policy() -> dict[str, Any]:
    return {
        "version": VERSION,
        "mode": "local-first, approval-gated",
        "allowed_actions": sorted(ALLOWED_ACTIONS),
        "max_steps": MAX_STEPS,
        "max_retries_per_step": MAX_RETRIES,
        "max_total_runtime_seconds": MAX_PLAN_RUNTIME_SECONDS,
        "max_step_timeout_seconds": MAX_STEP_TIMEOUT_SECONDS,
        "arbitrary_shell": False,
        "automatic_deploy": False,
        "automatic_delete": False,
        "requires_explicit_execution_approval": True,
    }


def validate_plan(data: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["plan must be a JSON object"]
    if isinstance(data.get("version"), bool) or data.get("version") != VERSION:
        errors.append(f"version must be {VERSION}")
    name = data.get("name")
    if not isinstance(name, str) or not name.strip() or len(name) > 120:
        errors.append("name must contain 1–120 characters")
    steps = data.get("steps")
    if not isinstance(steps, list) or not steps:
        errors.append("steps must be a non-empty list")
        return errors
    if len(steps) > MAX_STEPS:
        errors.append(f"steps must contain at most {MAX_STEPS} items")
    seen: set[str] = set()
    for index, step in enumerate(steps):
        prefix = f"steps[{index}]"
        if not isinstance(step, dict):
            errors.append(f"{prefix} must be an object")
            continue
        step_id = step.get("id")
        if not isinstance(step_id, str) or not step_id.strip() or len(step_id) > 64:
            errors.append(f"{prefix}.id must contain 1–64 characters")
        elif step_id in seen:
            errors.append(f"{prefix}.id must be unique")
        else:
            seen.add(step_id)
        action = step.get("action")
        if not isinstance(action, str) or action not in ALLOWED_ACTIONS:
            errors.append(f"{prefix}.action must be one of: {', '.join(sorted(ALLOWED_ACTIONS))}")
        retries = step.get("retries", 0)
        if not isinstance(retries, int) or isinstance(retries, bool) or not 0 <= retries <= MAX_RETRIES:
            errors.append(f"{prefix}.retries must be an integer from 0 to {MAX_RETRIES}")
        timeout = step.get("timeout_seconds", 120)
        if not isinstance(timeout, int) or isinstance(timeout, bool) or not 1 <= timeout <= MAX_STEP_TIMEOUT_SECONDS:
            errors.append(f"{prefix}.timeout_seconds must be an integer from 1 to {MAX_STEP_TIMEOUT_SECONDS}")
    budget = data.get("max_runtime_seconds", 1800)
    if not isinstance(budget, int) or isinstance(budget, bool) or not 1 <= budget <= MAX_PLAN_RUNTIME_SECONDS:
        errors.append(f"max_runtime_seconds must be an integer from 1 to {MAX_PLAN_RUNTIME_SECONDS}")
    return errors


def _command_for(action: str) -> list[str]:
    """Map an action identifier to a fixed argv; never use shell=True."""
    if action == "compile":
        return [sys.executable, "-m", "compileall", "-q", "neoos_mcp.py", "worker.py", "neoos_autodev.py", "tests"]
    if action == "test":
        return [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"]
    if action == "git_status":
        return ["git", "status", "--short"]
    raise ValueError(f"unsupported action: {action}")


def run_action(action: str, repo_root: Path, timeout_seconds: int) -> dict[str, Any]:
    if action not in ALLOWED_ACTIONS:
        raise ValueError(f"unsupported action: {action}")
    root = repo_root.resolve()
    if not root.is_dir():
        raise ValueError("repo_root must be an existing directory")
    env = {"PATH": os.environ.get("PATH", ""), "PYTHONIOENCODING": "utf-8"}
    try:
        completed = subprocess.run(
            _command_for(action), cwd=root, env=env, capture_output=True,
            text=True, timeout=timeout_seconds, check=False, shell=False,
        )
        return {
            "action": action,
            "returncode": completed.returncode,
            "stdout": completed.stdout[-12000:],
            "stderr": completed.stderr[-12000:],
            "timed_out": False,
        }
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode("utf-8", "replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        return {"action": action, "returncode": None, "stdout": stdout[-12000:], "stderr": stderr[-12000:], "timed_out": True}


def execute_plan(
    data: dict[str, Any], repo_root: Path, *, approved: bool = False,
    runner: Callable[[str, Path, int], dict[str, Any]] = run_action,
) -> dict[str, Any]:
    errors = validate_plan(data)
    if errors:
        return {"status": "invalid", "errors": errors, "steps": []}
    if not approved:
        return {"status": "approval_required", "errors": [], "steps": []}

    start = time.monotonic()
    budget = data.get("max_runtime_seconds", 1800)
    results: list[dict[str, Any]] = []
    overall_ok = True
    for step in data["steps"]:
        elapsed = time.monotonic() - start
        remaining = budget - elapsed
        if remaining <= 0:
            results.append({"id": step["id"], "status": "skipped", "reason": "plan runtime budget exhausted", "attempts": 0})
            overall_ok = False
            break
        attempts = 0
        last: dict[str, Any] = {}
        max_attempts = step.get("retries", 0) + 1
        while attempts < max_attempts:
            remaining = budget - (time.monotonic() - start)
            if remaining <= 0:
                break
            attempts += 1
            timeout = min(step.get("timeout_seconds", 120), MAX_STEP_TIMEOUT_SECONDS, max(1, int(remaining)))
            last = runner(step["action"], repo_root, timeout)
            if last.get("returncode") == 0 and not last.get("timed_out"):
                break
        success = last.get("returncode") == 0 and not last.get("timed_out")
        results.append({"id": step["id"], "status": "passed" if success else "failed", "attempts": attempts, "result": last})
        if not success:
            overall_ok = False
            break
    return {
        "status": "completed" if overall_ok else "failed",
        "plan": data["name"],
        "elapsed_seconds": round(time.monotonic() - start, 3),
        "steps": results,
    }


def _read_plan(path: Path) -> dict[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Cannot read plan: {exc}") from exc
    return loaded


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="NeoOS approval-gated local development runner")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("policy", help="print execution policy")
    validate_parser = sub.add_parser("validate", help="validate a plan without executing it")
    validate_parser.add_argument("plan", type=Path)
    run_parser = sub.add_parser("run", help="run approved allowlisted plan steps")
    run_parser.add_argument("plan", type=Path)
    run_parser.add_argument("--approve-execution", action="store_true", help="explicitly approve running the plan")
    run_parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args(argv)

    if args.command == "policy":
        print(json.dumps(policy(), ensure_ascii=False, indent=2))
        return 0
    data = _read_plan(args.plan)
    if args.command == "validate":
        errors = validate_plan(data)
        print(json.dumps({"valid": not errors, "errors": errors}, ensure_ascii=False, indent=2))
        return 0 if not errors else 2
    result = execute_plan(data, args.repo_root, approved=args.approve_execution)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] in {"completed", "approval_required"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
