import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class WorkerTests(unittest.TestCase):
    def run_worker(self, data_dir: str) -> subprocess.CompletedProcess[str]:
        root = Path(__file__).resolve().parents[1]
        env = dict(os.environ, NEOOS_DATA_DIR=data_dir)
        return subprocess.run(
            [sys.executable, str(root / "worker.py")],
            cwd=root, env=env, capture_output=True, text=True, check=False,
        )

    def test_heartbeat_imports_legacy_tasks_and_reports_queue(self):
        with tempfile.TemporaryDirectory() as temp:
            data = Path(temp)
            tasks_file = data / "tasks.json"
            original = [{"id": "abc123", "title": "Example", "status": "queued"}]
            tasks_file.write_text(json.dumps(original), encoding="utf-8")
            result = self.run_worker(temp)
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



    def test_non_array_legacy_task_file_is_preserved_and_import_retried(self):
        with tempfile.TemporaryDirectory() as temp:
            data = Path(temp)
            tasks_file = data / "tasks.json"
            original_content = '{"tasks": []}'
            tasks_file.write_text(original_content, encoding="utf-8")

            first_run = self.run_worker(temp)

            self.assertEqual(first_run.returncode, 0, first_run.stderr)
            self.assertIn("must contain a JSON array", first_run.stdout)
            self.assertIn("original file was preserved", first_run.stdout)
            self.assertEqual(tasks_file.read_text(encoding="utf-8"), original_content)

            db_path = data / "neoos.sqlite3"
            with sqlite3.connect(db_path) as conn:
                marker = conn.execute(
                    "SELECT value FROM schema_meta WHERE key='imported_tasks_json'"
                ).fetchone()
            self.assertIsNone(marker)

            repaired_tasks = [{"id": "repaired1", "title": "Recovered task", "status": "queued"}]
            tasks_file.write_text(json.dumps(repaired_tasks), encoding="utf-8")
            second_run = self.run_worker(temp)

            self.assertEqual(second_run.returncode, 0, second_run.stderr)
            self.assertNotIn("must contain a JSON array", second_run.stdout)
            with sqlite3.connect(db_path) as conn:
                imported = conn.execute(
                    "SELECT id,title,status FROM tasks WHERE id='repaired1'"
                ).fetchone()
                marker = conn.execute(
                    "SELECT value FROM schema_meta WHERE key='imported_tasks_json'"
                ).fetchone()
            self.assertEqual(imported, ("repaired1", "Recovered task", "queued"))
            self.assertIsNotNone(marker)
            self.assertEqual(tasks_file.read_text(encoding="utf-8"), json.dumps(repaired_tasks))

    def test_invalid_legacy_file_clears_stale_import_marker_and_retries(self):
        with tempfile.TemporaryDirectory() as temp:
            data = Path(temp)
            tasks_file = data / "tasks.json"
            original_content = '{"unexpected": true}'
            tasks_file.write_text(original_content, encoding="utf-8")
            db_path = data / "neoos.sqlite3"
            with sqlite3.connect(db_path) as conn:
                conn.execute("CREATE TABLE schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
                conn.execute("""CREATE TABLE tasks (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL, details TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                )""")
                conn.execute(
                    "INSERT INTO tasks(id,title,status,created_at,updated_at) VALUES (?,?,?,?,?)",
                    ("existing1", "Keep existing task", "queued", "before", "before"),
                )
                conn.execute(
                    "INSERT INTO schema_meta(key,value) VALUES ('imported_tasks_json','old-marker')"
                )

            first_run = self.run_worker(temp)

            self.assertEqual(first_run.returncode, 0, first_run.stderr)
            self.assertIn("must contain a JSON array", first_run.stdout)
            self.assertEqual(tasks_file.read_text(encoding="utf-8"), original_content)
            with sqlite3.connect(db_path) as conn:
                marker = conn.execute(
                    "SELECT value FROM schema_meta WHERE key='imported_tasks_json'"
                ).fetchone()
                existing = conn.execute(
                    "SELECT id,title FROM tasks WHERE id='existing1'"
                ).fetchone()
            self.assertIsNone(marker)
            self.assertEqual(existing, ("existing1", "Keep existing task"))

            repaired_tasks = [{"id": "legacyfix", "title": "Recovered after upgrade"}]
            tasks_file.write_text(json.dumps(repaired_tasks), encoding="utf-8")
            second_run = self.run_worker(temp)
            self.assertEqual(second_run.returncode, 0, second_run.stderr)
            with sqlite3.connect(db_path) as conn:
                imported = conn.execute(
                    "SELECT id,title FROM tasks WHERE id='legacyfix'"
                ).fetchone()
                existing = conn.execute(
                    "SELECT id,title FROM tasks WHERE id='existing1'"
                ).fetchone()
            self.assertEqual(imported, ("legacyfix", "Recovered after upgrade"))
            self.assertEqual(existing, ("existing1", "Keep existing task"))

    def test_malformed_legacy_json_is_warned_and_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            data = Path(temp)
            tasks_file = data / "tasks.json"
            original_content = '{not valid json'
            tasks_file.write_text(original_content, encoding="utf-8")

            result = self.run_worker(temp)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("must contain a JSON array", result.stdout)
            self.assertIn("import will retry", result.stdout)
            self.assertEqual(tasks_file.read_text(encoding="utf-8"), original_content)

    def test_non_utf8_legacy_task_file_is_warned_and_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            data = Path(temp)
            tasks_file = data / "tasks.json"
            original_bytes = b"\\xff\\xfe\\x80"
            tasks_file.write_bytes(original_bytes)

            result = self.run_worker(temp)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("readable", result.stdout)
            self.assertEqual(tasks_file.read_bytes(), original_bytes)

if __name__ == "__main__":
    unittest.main()
