#!/usr/bin/env python3
"""AgentBridge: local-first SQLite message bus for terminal AI agents."""
from __future__ import annotations
import argparse
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

APP = "agent-bridge"
DATA_DIR = Path(os.environ.get("AGENTBRIDGE_HOME", Path.home() / ".local" / "share" / APP)).expanduser()
DB_PATH = DATA_DIR / "bridge.sqlite3"

def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def positive_int(value, label="limit"):
    value = int(value)
    if value < 1:
        raise ValueError(f"{label} must be at least 1.")
    return value

def validate_message(body):
    body = body.strip()
    if not body:
        raise ValueError("Message cannot be empty.")
    if len(body) > 20000:
        raise ValueError("Message too long (maximum 20,000 characters).")
    return body

def connect():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA foreign_keys=ON")
    db.executescript("""
    CREATE TABLE IF NOT EXISTS agents (
      name TEXT PRIMARY KEY, role TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL,
      last_seen TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS messages (
      id INTEGER PRIMARY KEY AUTOINCREMENT, room TEXT NOT NULL DEFAULT 'general',
      sender TEXT NOT NULL, recipient TEXT NOT NULL, body TEXT NOT NULL,
      priority TEXT NOT NULL DEFAULT 'normal', created_at TEXT NOT NULL,
      reply_to INTEGER, metadata TEXT NOT NULL DEFAULT '{}'
    );
    CREATE INDEX IF NOT EXISTS idx_messages_room_id ON messages(room, id);
    CREATE INDEX IF NOT EXISTS idx_messages_recipient_id ON messages(recipient, id);
    CREATE TABLE IF NOT EXISTS reads (
      agent TEXT NOT NULL, message_id INTEGER NOT NULL, read_at TEXT NOT NULL,
      PRIMARY KEY(agent, message_id)
    );
    """)
    return db

def ensure_agent(db, name, role=""):
    name = name.strip()
    if not name or len(name) > 64 or any(c.isspace() for c in name):
        raise ValueError("Agent name must be 1-64 characters with no spaces.")
    stamp = now()
    db.execute("""INSERT INTO agents(name,role,created_at,last_seen) VALUES(?,?,?,?)
      ON CONFLICT(name) DO UPDATE SET
      role=CASE WHEN excluded.role='' THEN agents.role ELSE excluded.role END,
      last_seen=excluded.last_seen""", (name, role, stamp, stamp))
    db.commit()

def print_rows(rows, as_json=False):
    items = [dict(r) for r in rows]
    if as_json:
        print(json.dumps(items, ensure_ascii=False, indent=2))
        return
    for m in items:
        print(f"#{m.get('id','-')} [{m.get('created_at','')}] {m.get('room','general')} "
              f"{m.get('sender','?')} -> {m.get('recipient','?')} ({m.get('priority','normal')})")
        print("  " + str(m.get("body", "")).replace("\n", "\n  "))

def cmd_init(_):
    with connect() as db:
        print(f"AgentBridge ready. Database: {DB_PATH}")
        print(f"Registered agents: {db.execute('SELECT COUNT(*) FROM agents').fetchone()[0]}")

def cmd_register(a):
    with connect() as db:
        ensure_agent(db, a.name, a.role)
        print(f"Registered agent: {a.name}" + (f" — {a.role}" if a.role else ""))

def cmd_agents(a):
    with connect() as db:
        print_rows(db.execute("SELECT name,role,created_at,last_seen FROM agents ORDER BY name").fetchall(), a.json)

def cmd_send(a):
    body = validate_message(a.message)
    if a.to != "all" and not a.to.strip():
        raise ValueError("Recipient is required.")
    with connect() as db:
        ensure_agent(db, a.from_agent)
        if a.to != "all" and not db.execute("SELECT 1 FROM agents WHERE name=?", (a.to,)).fetchone():
            raise ValueError(f"Unknown recipient '{a.to}'. Register it first, or use --to all.")
        cur = db.execute("""INSERT INTO messages(room,sender,recipient,body,priority,created_at,reply_to,metadata)
          VALUES(?,?,?,?,?,?,?,?)""",
          (a.room, a.from_agent, a.to, body, a.priority, now(), a.reply_to, json.dumps({"source":"cli"})))
        db.commit()
        print(f"Sent message #{cur.lastrowid}: {a.from_agent} -> {a.to} in room '{a.room}'")

def cmd_inbox(a):
    limit = positive_int(a.limit)
    with connect() as db:
        ensure_agent(db, a.agent)
        rows = db.execute("""SELECT m.* FROM messages m
          LEFT JOIN reads r ON r.message_id=m.id AND r.agent=?
          WHERE (m.recipient=? OR m.recipient='all') AND m.room=?
          AND (?=1 OR r.message_id IS NULL)
          ORDER BY m.id DESC LIMIT ?""",
          (a.agent, a.agent, a.room, 1 if a.all_messages else 0, limit)).fetchall()
        rows = list(reversed(rows))
        print_rows(rows, a.json)
        if a.mark and rows:
            db.executemany("INSERT OR IGNORE INTO reads(agent,message_id,read_at) VALUES(?,?,?)",
                           [(a.agent, r["id"], now()) for r in rows])
            db.commit()

def cmd_history(a):
    limit = positive_int(a.limit)
    with connect() as db:
        rows = db.execute("SELECT * FROM messages WHERE room=? ORDER BY id DESC LIMIT ?",
                          (a.room, limit)).fetchall()
        print_rows(list(reversed(rows)), a.json)

def cmd_watch(a):
    ensure_interval = max(.25, min(a.interval, 30))
    positive_int(a.after + 1, "after must be zero or greater")
    print(f"Watching room '{a.room}' as '{a.agent}' (Ctrl+C to stop)")
    try:
        while True:
            with connect() as db:
                ensure_agent(db, a.agent)
                rows = db.execute("""SELECT * FROM messages WHERE room=? AND id>?
                  AND (recipient=? OR recipient='all') ORDER BY id""",
                  (a.room, a.after, a.agent)).fetchall()
                for m in rows:
                    print_rows([m], a.json)
                    a.after = max(a.after, m["id"])
            time.sleep(ensure_interval)
    except KeyboardInterrupt:
        print("\nStopped.")

def cmd_reply(a):
    body = validate_message(a.message)
    with connect() as db:
        original = db.execute("SELECT * FROM messages WHERE id=?", (a.message_id,)).fetchone()
        if not original:
            raise ValueError(f"Message #{a.message_id} not found.")
        ensure_agent(db, a.from_agent)
        cur = db.execute("""INSERT INTO messages(room,sender,recipient,body,priority,created_at,reply_to,metadata)
          VALUES(?,?,?,?,?,?,?,?)""",
          (original["room"], a.from_agent, original["sender"], body, a.priority, now(),
           original["id"], json.dumps({"source":"reply"})))
        db.commit()
        print(f"Reply #{cur.lastrowid} sent to {original['sender']} (replying to #{original['id']})")

def cmd_export(a):
    with connect() as db:
        rows = db.execute("SELECT * FROM messages WHERE room=? ORDER BY id", (a.room,)).fetchall()
        target = Path(a.path).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps([dict(r) for r in rows], ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Exported {len(rows)} messages to {target}")

def build_parser():
    p = argparse.ArgumentParser(prog="agentbridge", description="Local message bus so terminal AI agents can talk to one another.")
    p.add_argument("--version", action="version", version="AgentBridge 0.2.0")
    sub = p.add_subparsers(dest="command", required=True)
    q = sub.add_parser("init", help="Initialize local database"); q.set_defaults(func=cmd_init)
    q = sub.add_parser("register", help="Register or update an agent")
    q.add_argument("name"); q.add_argument("--role", default=""); q.set_defaults(func=cmd_register)
    q = sub.add_parser("agents", help="List registered agents")
    q.add_argument("--json", action="store_true"); q.set_defaults(func=cmd_agents)
    q = sub.add_parser("send", help="Send a message")
    q.add_argument("--from", dest="from_agent", required=True); q.add_argument("--to", required=True)
    q.add_argument("--room", default="general"); q.add_argument("--priority", choices=["low","normal","high"], default="normal")
    q.add_argument("--reply-to", type=int); q.add_argument("message"); q.set_defaults(func=cmd_send)
    q = sub.add_parser("inbox", help="Read messages addressed to an agent")
    q.add_argument("agent"); q.add_argument("--room", default="general"); q.add_argument("--limit", type=int, default=50)
    q.add_argument("--all", dest="all_messages", action="store_true", help="Include already-read messages")
    q.add_argument("--mark", action="store_true", help="Mark displayed messages as read")
    q.add_argument("--json", action="store_true"); q.set_defaults(func=cmd_inbox)
    q = sub.add_parser("history", help="Show room history"); q.add_argument("--room", default="general")
    q.add_argument("--limit", type=int, default=50); q.add_argument("--json", action="store_true"); q.set_defaults(func=cmd_history)
    q = sub.add_parser("watch", help="Poll for incoming messages")
    q.add_argument("agent"); q.add_argument("--room", default="general"); q.add_argument("--after", type=int, default=0)
    q.add_argument("--interval", type=float, default=1.0); q.add_argument("--json", action="store_true"); q.set_defaults(func=cmd_watch)
    q = sub.add_parser("reply", help="Reply to a message")
    q.add_argument("--from", dest="from_agent", required=True); q.add_argument("--priority", choices=["low","normal","high"], default="normal")
    q.add_argument("message_id", type=int); q.add_argument("message"); q.set_defaults(func=cmd_reply)
    q = sub.add_parser("export", help="Export a room to JSON")
    q.add_argument("--room", default="general"); q.add_argument("--path", default="agentbridge-export.json"); q.set_defaults(func=cmd_export)
    return p

def main():
    args = build_parser().parse_args()
    try:
        args.func(args)
    except (ValueError, sqlite3.Error, OSError) as exc:
        print(f"agentbridge: error: {exc}", file=sys.stderr)
        return 2
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
