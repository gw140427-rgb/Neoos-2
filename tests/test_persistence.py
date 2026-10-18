"""Regression tests for atomic task-file persistence."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import neoos_mcp


class TaskPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data_dir = Path(self.temp.name)
        self.tasks_file = self.data_dir / "tasks.json"
        self.journal_file = self.data_dir / "journal.jsonl"
        self.patches = [
            patch.object(neoos_mcp, "DATA_DIR", self.data_dir),
            patch.object(neoos_mcp, "TASKS_FILE", self.tasks_file),
            patch.object(neoos_mcp, "JOURNAL_FILE", self.journal_file),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def test_write_tasks_atomically_replaces_existing_file(self):
        self.tasks_file.write_text('[{"id":"old"}]\n', encoding="utf-8")

        neoos_mcp._write_tasks([{"id": "new", "title": "saved"}])

        self.assertEqual(
            json.loads(self.tasks_file.read_text(encoding="utf-8")),
            [{"id": "new", "title": "saved"}],
        )
        self.assertEqual(list(self.data_dir.glob(".tasks.json.*.tmp")), [])

    def test_replace_failure_preserves_existing_file_and_cleans_temp_file(self):
        original = '[{"id":"keep","title":"existing"}]\n'
        self.tasks_file.write_text(original, encoding="utf-8")

        with patch("neoos_mcp.os.replace", side_effect=OSError("simulated replace failure")):
            with self.assertRaisesRegex(OSError, "simulated replace failure"):
                neoos_mcp._write_tasks([{"id": "new"}])

        self.assertEqual(self.tasks_file.read_text(encoding="utf-8"), original)
        self.assertEqual(list(self.data_dir.glob(".tasks.json.*.tmp")), [])

    def test_write_failure_preserves_existing_file_and_cleans_temp_file(self):
        original = '[{"id":"keep"}]\n'
        self.tasks_file.write_text(original, encoding="utf-8")

        with patch("neoos_mcp.os.fsync", side_effect=OSError("simulated sync failure")):
            with self.assertRaisesRegex(OSError, "simulated sync failure"):
                neoos_mcp._write_tasks([{"id": "new"}])

        self.assertEqual(self.tasks_file.read_text(encoding="utf-8"), original)
        self.assertEqual(list(self.data_dir.glob(".tasks.json.*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
