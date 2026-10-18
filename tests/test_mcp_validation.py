"""Input validation regression tests for the NeoOS MCP task tools."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import neoos_mcp


class MCPValidationTests(unittest.TestCase):
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

    def write_tasks(self, tasks):
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.tasks_file.write_text(json.dumps(tasks), encoding="utf-8")

    def test_add_task_rejects_blank_or_oversized_title_without_mutation(self):
        original = [{"id": "keep", "title": "preserve", "status": "queued"}]
        self.write_tasks(original)
        before = self.tasks_file.read_bytes()

        for title in ("   ", "x" * 161):
            with self.subTest(title_length=len(title)), self.assertRaises(ValueError):
                neoos_mcp.add_task(title)

        self.assertEqual(self.tasks_file.read_bytes(), before)
        self.assertFalse(self.journal_file.exists())

    def test_add_task_rejects_oversized_details_without_mutation(self):
        original = [{"id": "keep", "title": "preserve", "status": "queued"}]
        self.write_tasks(original)
        before = self.tasks_file.read_bytes()

        with self.assertRaises(ValueError):
            neoos_mcp.add_task("valid title", "x" * 2001)

        self.assertEqual(self.tasks_file.read_bytes(), before)
        self.assertFalse(self.journal_file.exists())

    def test_add_task_accepts_boundary_lengths(self):
        task = neoos_mcp.add_task("x" * 160, "y" * 2000)
        self.assertEqual(len(task["title"]), 160)
        self.assertEqual(len(task["details"]), 2000)
        self.assertEqual(task["status"], "queued")
        self.assertEqual(json.loads(self.tasks_file.read_text(encoding="utf-8"))[0]["id"], task["id"])

    def test_list_tasks_rejects_unknown_status_filter(self):
        original = [{"id": "keep", "title": "preserve", "status": "queued"}]
        self.write_tasks(original)
        before = self.tasks_file.read_bytes()

        with self.assertRaises(ValueError):
            neoos_mcp.list_tasks("not-a-status")

        self.assertEqual(self.tasks_file.read_bytes(), before)
        self.assertFalse(self.journal_file.exists())

    def test_update_status_rejects_invalid_status_without_mutation(self):
        original = [{"id": "keep", "title": "preserve", "status": "queued"}]
        self.write_tasks(original)
        before = self.tasks_file.read_bytes()

        with self.assertRaises(ValueError):
            neoos_mcp.update_task_status("keep", "running")

        self.assertEqual(self.tasks_file.read_bytes(), before)
        self.assertFalse(self.journal_file.exists())

    def test_update_status_rejects_unknown_task_id_without_mutation(self):
        original = [{"id": "keep", "title": "preserve", "status": "queued"}]
        self.write_tasks(original)
        before = self.tasks_file.read_bytes()

        with self.assertRaises(ValueError):
            neoos_mcp.update_task_status("missing", "done")

        self.assertEqual(self.tasks_file.read_bytes(), before)
        self.assertFalse(self.journal_file.exists())


if __name__ == "__main__":
    unittest.main()
