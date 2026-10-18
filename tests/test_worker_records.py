"""Worker tests for malformed records and report-only behavior."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class WorkerRecordTests(unittest.TestCase):
    def run_worker(self, data_dir):
        env = dict(os.environ, NEOOS_DATA_DIR=str(data_dir))
        root = Path(__file__).resolve().parents[1]
        return subprocess.run(
            [sys.executable, str(root / "worker.py")],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_malformed_records_are_counted_and_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            data = Path(temp)
            tasks_file = data / "tasks.json"
            original = [
                {"id": "one", "title": "valid queued", "status": "queued"},
                {"id": "two", "title": "valid done", "status": "done"},
                "not-an-object",
                {"id": "bad-status", "status": "mystery"},
                None,
            ]
            original_text = json.dumps(original)
            tasks_file.write_text(original_text, encoding="utf-8")

            result = self.run_worker(data)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Tasks total: 5", result.stdout)
            self.assertIn("valid records: 2", result.stdout)
            self.assertIn("malformed records: 3", result.stdout)
            self.assertIn("queued: 1", result.stdout)
            self.assertIn("no shell commands or deployments executed", result.stdout)
            self.assertEqual(tasks_file.read_text(encoding="utf-8"), original_text)
            journal = (data / "journal.jsonl").read_text(encoding="utf-8")
            self.assertIn("malformed_records=3", journal)
            self.assertIn("no tasks executed", journal)


if __name__ == "__main__":
    unittest.main()
