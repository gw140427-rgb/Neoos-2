# NeoOS Rebuild

A clean, safety-first starter for rebuilding NeoOS with:
- a local **Model Context Protocol (MCP)** server for task tracking and project status;
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

The MCP server uses a local JSON task file at `data/tasks.json` by default. Set `NEOOS_DATA_DIR` to change the directory.

## Tools exposed by MCP

- `neoos_status`: runtime and workspace status.
- `list_tasks`: list task records.
- `add_task`: add a queued task.
- `update_task_status`: update a task to `queued`, `in_progress`, `blocked`, or `done`.
- `read_journal`: read recent worker journal entries.

The initial worker is deliberately **non-executing**: it records a heartbeat and summarizes queued tasks. It does not run shell commands, deploy services, modify Render, or delete data.

## Scheduled worker

The workflow in `.github/workflows/neoos-heartbeat.yml` runs hourly on GitHub Actions and can also be started manually. GitHub scheduled jobs are best-effort and may be delayed; this is not a continuously running 24/7 daemon.

## Safety and persistence

- No API keys or secrets are required for the basic task tracker.
- Task state persists only where the process can write its data directory. GitHub-hosted workflow runners are ephemeral, so their local state is not persistent between runs.
- Do not put passwords, tokens, or private personal information in task descriptions.
- Add deployment secrets only after reviewing the deployment design.
