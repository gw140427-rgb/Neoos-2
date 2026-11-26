# NeoOS-2

MCP-compatible server and SQLite task manager for the NeoOS rebuild.

## Local setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Run tests to verify the setup:

```bash
python -m unittest discover -s tests -v
```

## Running the MCP server

Run the MCP server over stdio for an MCP client:

```bash
python neoos_mcp.py
```

By default, the SQLite database is created at data/neoos.sqlite3. Set
NEOOS_DB_PATH to choose an exact database file path, or set NEOOS_DATA_DIR to
change the default data directory. Existing tasks.json and journal.jsonl files
are imported once and left in place. SQLite uses WAL mode and a busy timeout.

## Tools exposed by MCP

- neoos_status: runtime and database status.
- list_tasks: list task records.
- add_task: add a queued task.
- update_task_status: update a task to queued, in_progress, blocked, or done.
- read_journal: read recent journal entries.

The worker is deliberately **non-executing**: it records a heartbeat and
summarizes queued tasks. It does not run shell commands, deploy services,
modify Render, or delete data.

## Scheduled worker

The workflow in .github/workflows/neoos-heartbeat.yml runs hourly on GitHub
Actions and can also be started manually. GitHub-hosted workflow runners are
ephemeral, so the workflow is a test/heartbeat only; it is not the durable
database host.

## Podroid Docker backend

NeoOS Cloud uses podroid_vps_server.py as its writable Docker control plane.
It runs inside the Podroid environment on the Android phone and supports
container listing, creation, start/stop/restart, pause/resume, logs, one-shot
commands, and deletion. It supports Alpine, Ubuntu, Debian, BusyBox, Node.js,
Python, and Nginx templates.

Guest containers have default limits of 256 MB RAM, 0.5 CPU and 64 PIDs.
They receive a loopback-only published port, run without added Linux
capabilities, and expire after 30 minutes by default. Container writable-layer
data remains across stop/start but is removed when the container is deleted or
expires. The panel does not claim a fixed-size disk or public IP address.

The API requires NEOOS_API_TOKEN (a random secret with at least 32 characters).
The Cloud page can use either a direct authenticated HTTPS reverse proxy or the
Vercel gateway. The gateway requires NEOOS_BACKEND_URL, NEOOS_API_TOKEN and a
separate NEOOS_CONSOLE_TOKEN. See docs/vps/README.md for exact setup steps.

This is a **single-owner control panel**, not a public multi-user VPS platform.
It does not yet implement user registration, per-user container ownership, or
per-account quotas. Keep the owner token private and do not expose the web
terminal to strangers. Docker containers share the phone's host kernel and are
not equivalent to hardware-isolated virtual machines.

vps_server.py remains a separate authenticated, read-only Docker status API.
It does not create/delete containers or execute terminal commands.

## NeoOS apps

One portal, three apps (docs/index.html):

- **NeoOS Cloud** — docs/cloud/index.html, served at /cloud. Podroid Docker
  console with authenticated instance listing, guest creation, lifecycle
  controls, container logs, quick terminal commands, resource/TTL indicators,
  ask-cli guide, and optional Railway sandbox quick start.
- **NeoOS CapCut Studio** — docs/editor/index.html, served at /editor. Browser
  video editor with canvas preview, timeline, text overlays, filters, speed
  control, and MediaRecorder export.
- **콩밥 먹기: 감옥 생존기 v1.1** — docs/bean-jail/index.html, served at /game.
  Retro-sound survival mini game with new events and a hidden ending.

Legacy /vps routes redirect to /cloud. Routing lives in vercel.json (root and
docs/).

## Safety and persistence

- SQLite persists only when its file is placed on a persistent disk. Back up
  the database before moving or rebuilding the host environment.
- Keep container data separate from the task database. Guest writable-layer
  data is removed when its guest container is deleted or expires.
- Do not store passwords, API keys, or private personal information in task
  descriptions.
- Never commit environment files or tokens.
