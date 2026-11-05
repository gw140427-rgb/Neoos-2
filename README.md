# NeoOS Rebuild

A clean, safety-first starter for rebuilding NeoOS with:
- a Model Context Protocol (MCP) server for task tracking and project status;
- persistent SQLite storage for tasks and journal entries;
- a safe periodic worker that reports queued work without executing arbitrary commands;
- a GitHub Actions scheduled heartbeat (hourly best-effort; not a guaranteed 24/7 process).

## Status

This is a new starter implementation, not a restoration of the deleted repository. It does not contain the old NeoOS source or automatically repair existing Render services.

## Run locally (Python 3.11+ recommended)

```bash
python -m venv .venv
# activate the environment, then:
pip install -r requirements.txt
python -m unittest discover -s tests -v
python worker.py
```

Run the MCP server over stdio for an MCP-compatible client:

```bash
python neoos_mcp.py
```

By default, the SQLite database is created at `data/neoos.sqlite3`. Set `NEOOS_DB_PATH` to choose an exact database file path, or set `NEOOS_DATA_DIR` to change the default data directory. Existing `tasks.json` and `journal.jsonl` files are imported once and left in place. SQLite uses WAL mode and a busy timeout.

## Tools exposed by MCP

- `neoos_status`: runtime and database status.
- `list_tasks`: list task records.
- `add_task`: add a queued task.
- `update_task_status`: update a task to `queued`, `in_progress`, `blocked`, or `done`.
- `read_journal`: read recent journal entries.

The worker is deliberately **non-executing**: it records a heartbeat and summarizes queued tasks. It does not run shell commands, deploy services, modify Render, or delete data.

## Scheduled worker

The workflow in `.github/workflows/neoos-heartbeat.yml` runs hourly on GitHub Actions and can also be started manually. GitHub-hosted workflow runners are ephemeral, so the workflow is a test/heartbeat only; it is not the durable database host.

## Persistent VPS deployment

For AWS EC2, store the database on the EBS-backed path `/var/lib/neoos/neoos.sqlite3` by setting `NEOOS_DB_PATH`. A systemd unit template is in `deploy/systemd/neoos-mcp.service`; deployment and recovery prerequisites are documented in [docs/vps/aws-ec2.md](docs/vps/aws-ec2.md).

The existing `vps_server.py` endpoint is a separate authenticated, read-only Docker status API. It does not create/delete containers or execute terminal commands.

## Safety and persistence

- SQLite is included with standard Python builds; no paid database service is required for this configuration.
- The database persists only when its file is placed on a persistent disk. The EC2 setup uses its attached EBS volume.
- Keep backups. Do not store passwords, API keys, or private personal information in task descriptions.
- S3 object storage is not connected; the AWS account inventory showed no buckets in accessible regions. Create one only after reviewing ownership, access controls, and possible charges.
- Never commit environment files or tokens.
