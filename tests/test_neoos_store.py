import json
import os
import tempfile
import unittest
from pathlib import Path

import neoos_store


class NeoOSStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_env = dict(os.environ)
        os.environ["NEOOS_DATA_DIR"] = self.temp.name
        os.environ.pop("NEOOS_DB_PATH", None)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.old_env)
        self.temp.cleanup()

    def test_add_update_and_read_task(self):
        task = neoos_store.add_task("Save settings", "Keep the user preferences")
        self.assertEqual(task["status"], "queued")
        self.assertEqual(neoos_store.list_tasks("queued")[0]["id"], task["id"])
        updated = neoos_store.update_task_status(task["id"], "done")
        self.assertEqual(updated["status"], "done")
        self.assertEqual(neoos_store.list_tasks("queued"), [])
        self.assertEqual(neoos_store.list_tasks("done")[0]["id"], task["id"])
        events = neoos_store.read_journal(10)
        self.assertEqual([event["event"] for event in events], ["task_added", "task_status_updated"])

    def test_legacy_json_files_are_imported_and_not_deleted(self):
        folder = Path(self.temp.name)
        old_tasks = [{"id": "old01", "title": "Old task", "details": "from JSON", "status": "queued"}]
        old_journal = {"at": "2026-01-01T00:00:00+00:00", "event": "old_event", "details": "preserve me"}
        (folder / "tasks.json").write_text(json.dumps(old_tasks), encoding="utf-8")
        (folder / "journal.jsonl").write_text(json.dumps(old_journal) + "\n", encoding="utf-8")
        self.assertEqual(neoos_store.list_tasks()[0]["id"], "old01")
        self.assertEqual(neoos_store.read_journal(10)[0]["event"], "old_event")
        self.assertEqual(json.loads((folder / "tasks.json").read_text(encoding="utf-8")), old_tasks)
        self.assertTrue((folder / "journal.jsonl").exists())

    def test_database_path_can_be_set_to_persistent_mount(self):
        custom = Path(self.temp.name) / "mounted" / "neoos.sqlite3"
        os.environ["NEOOS_DB_PATH"] = str(custom)
        neoos_store.add_task("Persist on EBS")
        self.assertTrue(custom.is_file())

    def test_invalid_status_is_rejected(self):
        with self.assertRaises(ValueError):
            neoos_store.list_tasks("execute")
        with self.assertRaises(ValueError):
            neoos_store.update_task_status("missing", "execute")


if __name__ == "__main__":
    unittest.main()
