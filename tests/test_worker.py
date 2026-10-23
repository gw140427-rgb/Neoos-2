import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class WorkerTests(unittest.TestCase):
    def run_worker(self, data_dir: str) -> subprocess.CompletedProcess[str]:
        env = dict(os.environ, NEOOS_DATA_DIR=data_dir)
        root = Path(__file__).resolve().parents[1]
        return subprocess.run(
            [sys.executable, str(root / "worker.py")],
            env=env, capture_output=True, text=True, check=False,
        )

    def test_heartbeat_reports_queue_without_changing_tasks(self):
        with tempfile.TemporaryDirectory() as temp:
            data = Path(temp)
            tasks_file = data / "tasks.json"
            original = [{"id": "abc123", "title": "Example", "status": "queued"}]
            tasks_file.write_text(json.dumps(original), encoding="utf-8")

            result = self.run_worker(temp)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("queued: 1", result.stdout)
            self.assertEqual(json.loads(tasks_file.read_text(encoding="utf-8")), original)
            journal = (data / "journal.jsonl").read_text(encoding="utf-8")
            self.assertIn("worker_heartbeat", journal)

    def test_malformed_task_json_is_reported_and_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            data = Path(temp)
            tasks_file = data / "tasks.json"
            malformed_content = '{"broken": '
            tasks_file.write_text(malformed_content, encoding="utf-8")

            result = self.run_worker(temp)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("task file could not be parsed", result.stdout)
            self.assertEqual(tasks_file.read_text(encoding="utf-8"), malformed_content)
            journal = (data / "journal.jsonl").read_text(encoding="utf-8")
            self.assertIn("worker_heartbeat", journal)

    def test_non_array_task_json_is_reported_and_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            data = Path(temp)
            tasks_file = data / "tasks.json"
            non_array_content = '{"tasks": []}'
            tasks_file.write_text(non_array_content, encoding="utf-8")

            result = self.run_worker(temp)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("task file must contain a JSON array", result.stdout)
            self.assertEqual(tasks_file.read_text(encoding="utf-8"), non_array_content)
            journal = (data / "journal.jsonl").read_text(encoding="utf-8")
            self.assertIn("worker_heartbeat", journal)


if __name__ == "__main__":
    unittest.main()
