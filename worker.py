"""Safe NeoOS heartbeat worker; reports queued SQLite tasks but executes none."""
from __future__ import annotations

from neoos_store import list_tasks, record_event


def main() -> int:
    tasks = list_tasks()
    queued = [task for task in tasks if task.get("status") == "queued"]
    record_event(
        "worker_heartbeat",
        f"Report-only heartbeat. queued_tasks={len(queued)}; no tasks executed.",
    )
    print(f"Tasks total: {len(tasks)}; queued: {len(queued)}")
    print("Mode: report-only; no shell commands or deployments executed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
