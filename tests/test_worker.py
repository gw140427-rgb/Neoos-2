import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class WorkerTests(unittest.TestCase):
    def test_heartbeat_reports_queue_without_changing_tasks(self):
        with tempfile.TemporaryDirectory() as temp:
            data = Path(temp)
            tasks_file = data / "tasks.json"
            original = [{"id": "abc123", "title": "Example", "status": "queued"}]
            tasks_file.write_text(json.dumps(original), encoding="utf-8")
            env = dict(os.environ, NEOOS_DATA_DIR=temp)
            root = Path(__file__).resolve().parents[1]
            result = subprocess.run(
                [sys.executable, str(root / "worker.py")],
                env=env, capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("queued: 1", result.stdout)
            self.assertEqual(json.loads(tasks_file.read_text(encoding="utf-8")), original)
            journal = (data / "journal.jsonl").read_text(encoding="utf-8")
            self.assertIn("worker_heartbeat", journal)

    def test_malformed_task_file_is_preserved_and_warns(self):
        with tempfile.TemporaryDirectory() as temp:
            data = Path(temp)
            tasks_file = data / "tasks.json"
            malformed = '{"id": "incomplete"'
            tasks_file.write_text(malformed, encoding="utf-8")
            env = dict(os.environ, NEOOS_DATA_DIR=temp)
            root = Path(__file__).resolve().parents[1]
            result = subprocess.run(
                [sys.executable, str(root / "worker.py")],
                env=env, capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("WARNING: task file could not be parsed", result.stdout)
            self.assertEqual(tasks_file.read_text(encoding="utf-8"), malformed)
            journal = (data / "journal.jsonl").read_text(encoding="utf-8")
            self.assertIn("worker_heartbeat", journal)


if __name__ == "__main__":
    unittest.main()
