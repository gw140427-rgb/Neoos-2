"""Regression tests for journal parsing and I/O failures."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import neoos_mcp


class JournalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data_dir = Path(self.temp.name)
        self.journal_file = self.data_dir / "journal.jsonl"
        patcher = patch.object(neoos_mcp, "JOURNAL_FILE", self.journal_file)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_malformed_line_does_not_hide_valid_neighbors(self):
        self.journal_file.write_text(
            json.dumps({"event": "first"}) + "\n"
            + "{not valid json}\n"
            + json.dumps({"event": "last"}) + "\n",
            encoding="utf-8",
        )

        result = neoos_mcp.read_journal()

        self.assertEqual([item["event"] for item in result], ["first", "last"])

    def test_unreadable_journal_returns_empty_list(self):
        with patch("neoos_mcp.Path.read_text", side_effect=OSError("simulated read failure")):
            self.assertEqual(neoos_mcp.read_journal(), [])

    def test_journal_limit_is_clamped(self):
        self.journal_file.write_text(
            "\n".join(json.dumps({"index": index}) for index in range(5)) + "\n",
            encoding="utf-8",
        )

        self.assertEqual(len(neoos_mcp.read_journal(0)), 1)
        self.assertEqual(len(neoos_mcp.read_journal(2)), 2)
        self.assertEqual(len(neoos_mcp.read_journal(1000)), 5)


if __name__ == "__main__":
    unittest.main()
