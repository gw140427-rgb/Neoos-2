"""Safe NeoOS heartbeat worker; reports queued tasks but executes none."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(os.environ.get("NEOOS_DATA_DIR", "data")).expanduser()
TASKS_FILE = DATA_DIR / "tasks.json"
JOURNAL_FILE = DATA_DIR / "journal.jsonl"


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
    queued = [t for t in tasks if isinstance(t, dict) and t.get("status") == "queued"]
    record = {
        "at": now,
        "event": "worker_heartbeat",
        "details": f"Report-only heartbeat. queued_tasks={len(queued)}; no tasks executed.",
    }
    with JOURNAL_FILE.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"NeoOS heartbeat: {now}")
    print(f"Tasks total: {len(tasks)}; queued: {len(queued)}")
    print("Mode: report-only; no shell commands or deployments executed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
