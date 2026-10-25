"""Regression tests for fail-closed task storage behavior."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import neoos_mcp


class TaskStorageSafetyTests(unittest.TestCase):
    def test_corrupt_task_file_is_not_treated_as_empty(self):
        with tempfile.TemporaryDirectory() as temp:
            data_dir = Path(temp)
            tasks_file = data_dir / "tasks.json"
            original = '{"id": "keep-me",'
            tasks_file.write_text(original, encoding="utf-8")

            with patch.object(neoos_mcp, "DATA_DIR", data_dir), \
                 patch.object(neoos_mcp, "TASKS_FILE", tasks_file), \
                 patch.object(neoos_mcp, "JOURNAL_FILE", data_dir / "journal.jsonl"):
                with self.assertRaises(ValueError):
                    neoos_mcp.add_task("New task")

            self.assertEqual(tasks_file.read_text(encoding="utf-8"), original)
            self.assertFalse((data_dir / "journal.jsonl").exists())

    def test_non_list_task_file_is_rejected_without_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            data_dir = Path(temp)
            tasks_file = data_dir / "tasks.json"
            original = json.dumps({"existing": "data"})
            tasks_file.write_text(original, encoding="utf-8")

            with patch.object(neoos_mcp, "DATA_DIR", data_dir), \
                 patch.object(neoos_mcp, "TASKS_FILE", tasks_file), \
                 patch.object(neoos_mcp, "JOURNAL_FILE", data_dir / "journal.jsonl"):
                with self.assertRaises(ValueError):
                    neoos_mcp.add_task("New task")

            self.assertEqual(tasks_file.read_text(encoding="utf-8"), original)

    def test_missing_task_file_starts_with_empty_queue(self):
        with tempfile.TemporaryDirectory() as temp:
            data_dir = Path(temp)
            tasks_file = data_dir / "tasks.json"
            with patch.object(neoos_mcp, "DATA_DIR", data_dir), \
                 patch.object(neoos_mcp, "TASKS_FILE", tasks_file), \
                 patch.object(neoos_mcp, "JOURNAL_FILE", data_dir / "journal.jsonl"):
                task = neoos_mcp.add_task("First task")
                self.assertEqual(task["title"], "First task")
                self.assertEqual(task["status"], "queued")
                self.assertEqual(len(json.loads(tasks_file.read_text(encoding="utf-8"))), 1)


if __name__ == "__main__":
    unittest.main()
