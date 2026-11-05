"""SQLite-backed persistent storage for NeoOS tasks and journal entries.

The database defaults to data/neoos.sqlite3. On an EC2 VPS, set
NEOOS_DB_PATH=/var/lib/neoos/neoos.sqlite3 on a persistent EBS volume.
Legacy tasks.json and journal.jsonl files are imported once and never deleted.
"""
from __future__ import annotations

import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

VALID_STATUSES = {"queued", "in_progress", "blocked", "done"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_database_path() -> Path:
    data_dir = Path(os.environ.get("NEOOS_DATA_DIR", "data")).expanduser()
    configured = os.environ.get("NEOOS_DB_PATH", "").strip()
    return Path(configured).expanduser() if configured else data_dir / "neoos.sqlite3"


def _legacy_data_dir() -> Path:
    return Path(os.environ.get("NEOOS_DATA_DIR", "data")).expanduser()


def _initialize(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            details TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL CHECK(status IN ('queued','in_progress','blocked','done')),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS journal (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            at TEXT NOT NULL,
            event TEXT NOT NULL,
            details TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    conn.execute("BEGIN IMMEDIATE")
    try:
        legacy_dir = _legacy_data_dir()
        tasks_marker = conn.execute(
            "SELECT value FROM schema_meta WHERE key = 'imported_tasks_json'"
        ).fetchone()
        if tasks_marker is None:
            legacy_tasks = legacy_dir / "tasks.json"
            if legacy_tasks.is_file():
                try:
                    loaded = json.loads(legacy_tasks.read_text(encoding="utf-8"))
                    if isinstance(loaded, list):
                        for item in loaded:
                            if not isinstance(item, dict) or not item.get("id") or not item.get("title"):
                                continue
                            status = item.get("status", "queued")
                            if status not in VALID_STATUSES:
                                status = "queued"
                            created = item.get("created_at") or now_iso()
                            updated = item.get("updated_at") or created
                            conn.execute(
                                """INSERT OR IGNORE INTO tasks
                                   (id,title,details,status,created_at,updated_at)
                                   VALUES (?,?,?,?,?,?)""",
                                (str(item["id"]), str(item["title"])[:160],
                                 str(item.get("details", ""))[:2000], status,
                                 str(created), str(updated)),
                            )
                except (OSError, json.JSONDecodeError):
                    pass
            conn.execute(
                "INSERT OR REPLACE INTO schema_meta(key,value) VALUES ('imported_tasks_json',?)",
                (now_iso(),),
            )

        journal_marker = conn.execute(
            "SELECT value FROM schema_meta WHERE key = 'imported_journal_jsonl'"
        ).fetchone()
        if journal_marker is None:
            legacy_journal = legacy_dir / "journal.jsonl"
            if legacy_journal.is_file():
                try:
                    for line in legacy_journal.read_text(encoding="utf-8").splitlines():
                        try:
                            item = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if isinstance(item, dict) and item.get("event"):
                            conn.execute(
                                "INSERT INTO journal(at,event,details) VALUES (?,?,?)",
                                (str(item.get("at") or now_iso()),
                                 str(item["event"])[:100],
                                 str(item.get("details", ""))[:500]),
                            )
                except OSError:
                    pass
            conn.execute(
                "INSERT OR REPLACE INTO schema_meta(key,value) VALUES ('imported_journal_jsonl',?)",
                (now_iso(),),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


@contextmanager
def database() -> Iterator[sqlite3.Connection]:
    path = get_database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=15)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA busy_timeout=15000")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA journal_mode=WAL")
        _initialize(conn)
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def list_tasks(status: str = "") -> list[dict[str, Any]]:
    if status and status not in VALID_STATUSES:
        raise ValueError(f"status must be one of: {', '.join(sorted(VALID_STATUSES))}")
    with database() as conn:
        if status:
            rows = conn.execute(
                "SELECT id,title,details,status,created_at,updated_at FROM tasks WHERE status=? ORDER BY created_at,id",
                (status,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id,title,details,status,created_at,updated_at FROM tasks ORDER BY created_at,id"
            ).fetchall()
        return [dict(row) for row in rows]


def add_task(title: str, details: str = "") -> dict[str, Any]:
    title = title.strip()
    if not title or len(title) > 160:
        raise ValueError("title must contain 1–160 characters")
    if len(details) > 2000:
        raise ValueError("details must be at most 2000 characters")
    now = now_iso()
    task = {
        "id": str(uuid.uuid4())[:8],
        "title": title,
        "details": details,
        "status": "queued",
        "created_at": now,
        "updated_at": now,
    }
    with database() as conn:
        conn.execute(
            "INSERT INTO tasks(id,title,details,status,created_at,updated_at) VALUES (?,?,?,?,?,?)",
            (task["id"], task["title"], task["details"], task["status"], now, now),
        )
        conn.execute(
            "INSERT INTO journal(at,event,details) VALUES (?,?,?)",
            (now, "task_added", f'{task["id"]}: {title}'[:500]),
        )
    return task


def update_task_status(task_id: str, status: str) -> dict[str, Any] | None:
    if status not in VALID_STATUSES:
        raise ValueError(f"status must be one of: {', '.join(sorted(VALID_STATUSES))}")
    now = now_iso()
    with database() as conn:
        cursor = conn.execute(
            "UPDATE tasks SET status=?, updated_at=? WHERE id=?",
            (status, now, task_id),
        )
        if cursor.rowcount == 0:
            return None
        row = conn.execute(
            "SELECT id,title,details,status,created_at,updated_at FROM tasks WHERE id=?",
            (task_id,),
        ).fetchone()
        conn.execute(
            "INSERT INTO journal(at,event,details) VALUES (?,?,?)",
            (now, "task_status_updated", f"{task_id}: {status}"),
        )
        return dict(row) if row else None


def record_event(event: str, details: str) -> None:
    with database() as conn:
        conn.execute(
            "INSERT INTO journal(at,event,details) VALUES (?,?,?)",
            (now_iso(), event[:100], details[:500]),
        )


def read_journal(limit: int = 20) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit), 100))
    with database() as conn:
        rows = conn.execute(
            "SELECT at,event,details FROM journal ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(row) for row in reversed(rows)]


def task_count() -> int:
    with database() as conn:
        row = conn.execute("SELECT COUNT(*) AS count FROM tasks").fetchone()
        return int(row["count"]) if row else 0
