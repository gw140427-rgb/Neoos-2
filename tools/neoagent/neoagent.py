#!/usr/bin/env python3
"""NeoAgent: small local multi-agent message bus for Debian/Termux (stdlib only)."""
from __future__ import annotations
import argparse, json, os, sqlite3, sys, time
from pathlib import Path
from datetime import datetime, timezone

DATA_DIR = Path(os.environ.get("NEOAGENT_DATA_DIR", str(Path.home() / ".local" / "share" / "neoagent")))
DB_PATH = DATA_DIR / "neoagent.sqlite3"
ROLES = {"coordinator", "researcher", "coder", "reviewer", "user"}

def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def connect():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("""CREATE TABLE IF NOT EXISTS agents (
        name TEXT PRIMARY KEY, role TEXT NOT NULL, command TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL, last_seen TEXT)""")
    db.execute("""CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT, sender TEXT NOT NULL, recipient TEXT NOT NULL,
        body TEXT NOT NULL, created_at TEXT NOT NULL, read_at TEXT)""")
    db.commit()
    return db

def print_rows(rows):
    for row in rows:
        print(json.dumps(dict(row), ensure_ascii=False))

def main():
    p = argparse.ArgumentParser(prog="neoagent", description="NeoOS local multi-agent message bus")
    sub = p.add_subparsers(dest="action", required=True)
    r = sub.add_parser("register", help="register an agent")
    r.add_argument("name"); r.add_argument("--role", choices=sorted(ROLES), default="researcher")
    r.add_argument("--command", default="", help="optional launch command label; never executed by NeoAgent")
    s = sub.add_parser("send", help="send a message")
    s.add_argument("sender"); s.add_argument("recipient"); s.add_argument("message")
    i = sub.add_parser("inbox", help="read pending messages")
    i.add_argument("name"); i.add_argument("--all", action="store_true")
    a = sub.add_parser("agents", help="list registered agents")
    w = sub.add_parser("watch", help="poll inbox for messages")
    w.add_argument("name"); w.add_argument("--interval", type=float, default=3.0)
    w.add_argument("--once", action="store_true")
    sub.add_parser("status", help="show local database status")
    args = p.parse_args()
    db = connect()
    try:
        if args.action == "register":
            db.execute("INSERT INTO agents(name,role,command,created_at,last_seen) VALUES(?,?,?,?,?) "
                       "ON CONFLICT(name) DO UPDATE SET role=excluded.role, command=excluded.command, last_seen=excluded.last_seen",
                       (args.name, args.role, args.command, now(), now()))
            db.commit(); print(f"등록됨: {args.name} ({args.role})")
        elif args.action == "send":
            names = {x["name"] for x in db.execute("SELECT name FROM agents")}
            if args.sender not in names: sys.exit(f"오류: 발신 에이전트 '{args.sender}'를 먼저 register 하세요.")
            if args.recipient != "*" and args.recipient not in names: sys.exit(f"오류: 수신 에이전트 '{args.recipient}'가 없습니다.")
            recipients = [x["name"] for x in db.execute("SELECT name FROM agents WHERE name != ?", (args.sender,))] if args.recipient == "*" else [args.recipient]
            for recipient in recipients:
                db.execute("INSERT INTO messages(sender,recipient,body,created_at) VALUES(?,?,?,?)",
                           (args.sender, recipient, args.message, now()))
            db.commit(); print(f"전송 완료: {len(recipients)}개 에이전트")
        elif args.action == "inbox":
            q = "SELECT id,sender,recipient,body,created_at,read_at FROM messages WHERE recipient=?"
            if not args.all: q += " AND read_at IS NULL"
            q += " ORDER BY id"
            rows = db.execute(q, (args.name,)).fetchall()
            print_rows(rows)
            if not args.all and rows:
                db.executemany("UPDATE messages SET read_at=? WHERE id=?", [(now(), x["id"]) for x in rows])
                db.commit()
        elif args.action == "agents":
            print_rows(db.execute("SELECT name,role,command,created_at,last_seen FROM agents ORDER BY name").fetchall())
        elif args.action == "watch":
            if args.interval < 1: sys.exit("--interval은 1초 이상이어야 합니다.")
            print(f"{args.name} 대기 중. 종료: Ctrl+C", flush=True)
            while True:
                rows = db.execute("SELECT id,sender,body,created_at FROM messages WHERE recipient=? AND read_at IS NULL ORDER BY id", (args.name,)).fetchall()
                if rows:
                    print_rows(rows)
                    db.executemany("UPDATE messages SET read_at=? WHERE id=?", [(now(), x["id"]) for x in rows]); db.commit()
                if args.once: break
                time.sleep(args.interval)
        elif args.action == "status":
            print(json.dumps({"database": str(DB_PATH), "agents": db.execute("SELECT COUNT(*) FROM agents").fetchone()[0],
                              "messages": db.execute("SELECT COUNT(*) FROM messages").fetchone()[0]}, ensure_ascii=False, indent=2))
    finally:
        db.close()

if __name__ == "__main__":
    main()
