"""Safe NeoOS heartbeat worker; reports queued tasks but executes none."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(os.environ.get("NEOOS_DATA_DIR", "data")).expanduser()
TASKS_FILE = DATA_DIR / "tasks.json"
JOURNAL_FILE = DATA_DIR / "journal.jsonl"
VALID_STATUSES = {"queued", "in_progress", "blocked", "done"}


def main() -> int:
    now = datetime.now(timezone.utc).isoformat()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tasks = []
    if TASKS_FILE.exists():
        try:
            loaded = json.loads(TASKS_FILE.read_text(encoding="utf-8"))
            if isinstance(loaded, list):
                tasks = loaded
        except (OSError, json.JSONDecodeError):
            print("WARNING: task file could not be parsed; no tasks were changed.")
    valid_tasks = [
        task for task in tasks
        if isinstance(task, dict) and task.get("status") in VALID_STATUSES
    ]
    queued = [task for task in valid_tasks if task.get("status") == "queued"]
    malformed_count = len(tasks) - len(valid_tasks)
    record = {
        "at": now,
        "event": "worker_heartbeat",
        "details": (
            f"Report-only heartbeat. total_tasks={len(tasks)}; "
            f"valid_records={len(valid_tasks)}; malformed_records={malformed_count}; "
            f"queued_tasks={len(queued)}; no tasks executed."
        ),
    }
    with JOURNAL_FILE.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"NeoOS heartbeat: {now}")
    print(
        f"Tasks total: {len(tasks)}; valid records: {len(valid_tasks)}; "
        f"malformed records: {malformed_count}; queued: {len(queued)}"
    )
    print("Mode: report-only; no shell commands or deployments executed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
