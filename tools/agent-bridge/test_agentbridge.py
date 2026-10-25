import importlib.util
import tempfile
import unittest
from pathlib import Path
from argparse import Namespace

SCRIPT = Path(__file__).with_name("agentbridge.py")
spec = importlib.util.spec_from_file_location("agentbridge", SCRIPT)
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)

class AgentBridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        app.DATA_DIR = Path(self.tmp.name)
        app.DB_PATH = app.DATA_DIR / "test.sqlite3"

    def tearDown(self):
        self.tmp.cleanup()

    def test_send_and_receive(self):
        with app.connect() as db:
            app.ensure_agent(db, "codex")
            app.ensure_agent(db, "hermes")
            db.execute(
                "INSERT INTO messages(room,sender,recipient,body,priority,created_at) VALUES(?,?,?,?,?,?)",
                ("neoos", "codex", "hermes", "hello", "normal", app.now()),
            )
            rows = db.execute("SELECT * FROM messages WHERE recipient=?", ("hermes",)).fetchall()
            self.assertEqual(rows[0]["body"], "hello")

    def test_broadcast_visible(self):
        with app.connect() as db:
            app.ensure_agent(db, "codex")
            app.ensure_agent(db, "hermes")
            db.execute(
                "INSERT INTO messages(room,sender,recipient,body,priority,created_at) VALUES(?,?,?,?,?,?)",
                ("neoos", "codex", "all", "update", "high", app.now()),
            )
            rows = db.execute(
                "SELECT * FROM messages WHERE room=? AND (recipient=? OR recipient='all')",
                ("neoos", "hermes"),
            ).fetchall()
            self.assertEqual(rows[0]["body"], "update")

    def test_empty_message_rejected(self):
        with self.assertRaises(ValueError):
            app.validate_message("  ")

    def test_message_length_rejected(self):
        with self.assertRaises(ValueError):
            app.validate_message("x" * 20001)

    def test_bad_agent_name_rejected(self):
        with app.connect() as db:
            with self.assertRaises(ValueError):
                app.ensure_agent(db, "two words")

if __name__ == "__main__":
    unittest.main()
