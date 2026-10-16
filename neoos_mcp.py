"""NeoOS rebuild MCP server: safe local task tracking only."""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("neoos-rebuild")
DATA_DIR = Path(os.environ.get("NEOOS_DATA_DIR", "data")).expanduser().resolve()
TASKS_FILE = DATA_DIR / "tasks.json"
JOURNAL_FILE = DATA_DIR / "journal.jsonl"
VALID_STATUSES = {"queued", "in_progress", "blocked", "done"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_tasks() -> list[dict[str, Any]]:
    if not TASKS_FILE.exists():
        return []
    try:
        value = json.loads(TASKS_FILE.read_text(encoding="utf-8"))
        return value if isinstance(value, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def _write_tasks(tasks: list[dict[str, Any]]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    temp = TASKS_FILE.with_suffix(".tmp")
    temp.write_text(json.dumps(tasks, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(TASKS_FILE)


def _journal(event: str, details: str) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    record = {"at": now_iso(), "event": event, "details": details[:500]}
    with JOURNAL_FILE.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, ensure_ascii=False) + "\n")


@mcp.tool()
def neoos_status() -> dict[str, Any]:
    """Return basic status of the NeoOS rebuild workspace."""
    return {
        "project": "NeoOS Rebuild",
        "status": "starter",
        "data_directory": str(DATA_DIR),
        "tasks_file_exists": TASKS_FILE.exists(),
        "task_count": len(_read_tasks()),
        "worker_mode": "report-only; no command execution",
        "checked_at": now_iso(),
    }


@mcp.tool()
def list_tasks(status: str = "") -> list[dict[str, Any]]:
    """List tasks, optionally filtered by a valid status."""
    if status and status not in VALID_STATUSES:
        raise ValueError(f"status must be one of: {', '.join(sorted(VALID_STATUSES))}")
    tasks = _read_tasks()
    return [task for task in tasks if not status or task.get("status") == status]


@mcp.tool()
def add_task(title: str, details: str = "") -> dict[str, Any]:
    """Add a task to the local queue; this does not execute the task."""
    title = title.strip()
    if not title or len(title) > 160:
        raise ValueError("title must contain 1–160 characters")
    if len(details) > 2000:
        raise ValueError("details must be at most 2000 characters")
    tasks = _read_tasks()
    task = {
        "id": str(uuid.uuid4())[:8],
        "title": title,
        "details": details,
        "status": "queued",
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    tasks.append(task)
    _write_tasks(tasks)
    _journal("task_added", f'{task["id"]}: {title}')
    return task


@mcp.tool()
def update_task_status(task_id: str, status: str) -> dict[str, Any]:
    """Update a task status; allowed values are queued, in_progress, blocked, done."""
    if status not in VALID_STATUSES:
        raise ValueError(f"status must be one of: {', '.join(sorted(VALID_STATUSES))}")
    tasks = _read_tasks()
    for task in tasks:
        if task.get("id") == task_id:
            task["status"] = status
            task["updated_at"] = now_iso()
            _write_tasks(tasks)
            _journal("task_status_updated", f"{task_id}: {status}")
            return task
    raise ValueError(f"task not found: {task_id}")


@mcp.tool()
def read_journal(limit: int = 20) -> list[dict[str, Any]]:
    """Read recent journal entries. Limit is clamped to 1–100."""
    limit = max(1, min(int(limit), 100))
    if not JOURNAL_FILE.exists():
        return []
    lines = JOURNAL_FILE.read_text(encoding="utf-8").splitlines()[-limit:]
    result = []
    for line in lines:
        try:
            result.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return result


if __name__ == "__main__":
    mcp.run(transport="stdio")
