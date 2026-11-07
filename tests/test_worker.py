import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class WorkerTests(unittest.TestCase):
    def test_heartbeat_imports_legacy_tasks_and_reports_queue(self):
        with tempfile.TemporaryDirectory() as temp:
            data = Path(temp)
            tasks_file = data / "tasks.json"
            original = [{"id": "abc123", "title": "Example", "status": "queued"}]
            tasks_file.write_text(json.dumps(original), encoding="utf-8")
            env = dict(os.environ, NEOOS_DATA_DIR=temp)
            root = Path(__file__).resolve().parents[1]
            result = subprocess.run(
                [sys.executable, str(root / "worker.py")],
                cwd=root, env=env, capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("queued: 1", result.stdout)
            self.assertEqual(json.loads(tasks_file.read_text(encoding="utf-8")), original)
            db_path = data / "neoos.sqlite3"
            self.assertTrue(db_path.is_file())
            with sqlite3.connect(db_path) as conn:
                events = conn.execute("SELECT event FROM journal ORDER BY id").fetchall()
                tasks = conn.execute("SELECT id,title,status FROM tasks").fetchall()
            self.assertEqual(tasks, [("abc123", "Example", "queued")])
            self.assertEqual(events, [("worker_heartbeat",)])


if __name__ == "__main__":
    unittest.main()
