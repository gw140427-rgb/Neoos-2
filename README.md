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

## Running the server

Run the MCP server over stdio for an MCP client:

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

On a Podroid node, store the database on a persistent path such as `/var/lib/neoos/neoos.sqlite3` by setting `NEOOS_DB_PATH`. A systemd unit template is in `deploy/systemd/neoos-mcp.service`; backend setup is documented in [docs/vps/README.md](docs/vps/README.md).

`vps_server.py` is a separate authenticated, read-only Docker status API: it does not create/delete containers or execute terminal commands.

`podroid_vps_server.py` is the writable panel behind the console: it lists containers with live CPU/RAM and published ports, creates capped guest containers (`--cap-drop=ALL`, `--security-opt=no-new-privileges`, fixed memory/CPU/PID limits, one free port from 8101–8199), starts/stops/reboots/deletes them, serves a one-shot web terminal (`POST /api/instances/{id}/exec`), caps simultaneous guests (`MAX_CONTAINERS`, `429 capacity_full`), expires guests after 30 minutes, and never touches containers it did not create or anything named `box` / `user-vps-*`. Endpoints, environment variables and guardrails: [docs/vps/README.md](docs/vps/README.md).

## NeoOS apps

One portal, four apps (`docs/index.html`):

- **Neo AI 채팅** — [docs/ai/index.html](docs/ai/index.html), served at `/ai`. Five selectable models: Neo-2, Neo-2 Plus, Neo-2 Mini, Neo-1 Plus and Neo-1. The Neo-2 series uses 2024 (GPT-4o era) knowledge as its baseline.
- **NeoOS Cloud** — [docs/cloud/index.html](docs/cloud/index.html), served at `/cloud`. Podroid-only guest console with a local engine: deploy, start/stop/reboot/delete and the web terminal work without any backend, with state kept in the browser. `MAX_INSTANCES=4`, Podroid guests are cleaned up after 30 minutes, `ask-cli` install guide, and the Railway free-sandbox quick start. An optional API mode forwards actions to the Podroid backend ([docs/vps/README.md](docs/vps/README.md)).
- **NeoOS CapCut Studio** — [docs/editor/index.html](docs/editor/index.html), served at `/editor`. Browser video editor: canvas preview, timeline, text overlays, filters, speed control, and MediaRecorder export.
- **콩밥 먹기: 감옥 생존기 v1.1** — [docs/bean-jail/index.html](docs/bean-jail/index.html), served at `/game`. Retro-sound survival mini game with new events and a hidden ending.

`/vps` and `docs/vps/index.html` redirect to `/cloud`; the Podroid dashboard is NeoOS Cloud. Routing lives in `vercel.json` (root and `docs/`).

The AI chat backend is [neo_ai_server.py](neo_ai_server.py): `GET /health` lists the models and `POST /chat` forwards a whitelisted model plus up to 12 messages to Ollama. It needs no client-side API key (a static page cannot keep one secret); abuse is capped by a per-IP rate limit and a single-generation lock. Model definitions live in `models/*/Modelfile` (Neo-2 = 1.5B, Neo-2 Plus = 3B, Neo-2 Mini = 0.5B base). On this sandbox run `./start_ai.sh` after a restart: it starts Ollama from `/data/ollama`, loads models from `/data/ollama-models`, starts the backend on port 8091, and republishes the port. The Vercel functions in `docs/api/` proxy to the same backend URL as the page's direct fallback. The Neo models are prompt/parameter variants of open base models, not weights trained from scratch.

> The admin panel and API settings are stored in the browser. In local-engine mode nothing is deployed to a node: guests are simulated in the browser. Real actions only happen in API mode, where protection comes from the Podroid API token, the 4-guest quota and the 30-minute TTL.

## Safety and persistence

- SQLite is included with standard Python builds; no paid database service is required for this configuration.
- The database persists only when its file is placed on a persistent disk on the Podroid node.
- Keep backups. Do not store passwords, API keys, or private personal information in task descriptions.
- No external object storage is connected; task data stays in local SQLite on the node.
- Never commit environment files or tokens.
