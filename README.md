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

For AWS EC2, store the database on the EBS-backed path `/var/lib/neoos/neoos.sqlite3` by setting `NEOOS_DB_PATH`. A systemd unit template is in `deploy/systemd/neoos-mcp.service`; deployment and recovery prerequisites are documented in [docs/vps/aws-ec2.md](docs/vps/aws-ec2.md).

`vps_server.py` is a separate authenticated, read-only Docker status API: it does not create/delete containers or execute terminal commands.

`podroid_vps_server.py` is the writable panel behind the console: it lists containers with live CPU/RAM and published ports, creates capped guest containers (`--cap-drop=ALL`, `--security-opt=no-new-privileges`, fixed memory/CPU/PID limits, one free port from 8101–8199), starts/stops/reboots/deletes them, serves a one-shot web terminal (`POST /api/instances/{id}/exec`), caps simultaneous guests (`MAX_CONTAINERS`, `429 capacity_full`), expires guests after 30 minutes, and never touches containers it did not create or anything named `box` / `user-vps-*`. Endpoints, environment variables and guardrails: [docs/vps/README.md](docs/vps/README.md).

## NeoOS apps

One portal, four apps (`docs/index.html`):

- **Neo AI 채팅** — [docs/ai/index.html](docs/ai/index.html), served at `/ai`. Five selectable models: Neo-2, Neo-2 Plus, Neo-2 Mini, Neo-1 Plus and Neo-1. The Neo-2 series uses 2024 (GPT-4o era) knowledge as its baseline.
- **NeoOS Cloud** — [docs/cloud/index.html](docs/cloud/index.html), served at `/cloud`. Unified AI-sandbox and VPS console with a local engine: deploy, start/stop/reboot/delete and the web terminal work without any backend, with state kept in the browser. `MAX_INSTANCES=4`, no 24-hour expiry on worker instances (guest containers are cleaned up after 30 minutes), `ask-cli` install guide, and the Railway free-sandbox quick start. An optional API mode forwards actions to a real NeoOS backend. Backend setup and IAM requirements: [docs/vps/AWS.md](docs/vps/AWS.md); the EC2 backend uses an attached IAM role and only manages instances tagged for NeoOS.
- **NeoOS CapCut Studio** — [docs/editor/index.html](docs/editor/index.html), served at `/editor`. Browser video editor: canvas preview, timeline, text overlays, filters, speed control, and MediaRecorder export.
- **콩밥 먹기: 감옥 생존기 v1.1** — [docs/bean-jail/index.html](docs/bean-jail/index.html), served at `/game`. Retro-sound survival mini game with new events and a hidden ending.

`/vps`, `/vps/aws.html` and `docs/vps/index.html` are redirects to `/cloud`; the old Podroid dashboard was folded into NeoOS Cloud. Routing lives in `vercel.json` (root and `docs/`).

The AI chat backend is [neo_ai_server.py](neo_ai_server.py): `GET /health` lists the models and `POST /chat` forwards a whitelisted model plus up to 12 messages to Ollama. It needs no client-side API key (a static page cannot keep one secret); abuse is capped by a per-IP rate limit and a single-generation lock. Model definitions live in `models/*/Modelfile` (Neo-2 = 1.5B, Neo-2 Plus = 3B, Neo-2 Mini = 0.5B base). On this sandbox run `./start_ai.sh` after a restart: it starts Ollama from `/data/ollama`, loads models from `/data/ollama-models`, starts the backend on port 8091, and republishes the port. The Vercel functions in `docs/api/` proxy to the same backend URL as the page's direct fallback. The Neo models are prompt/parameter variants of open base models, not weights trained from scratch.

> The admin panel and API settings are stored in the browser. In local-engine mode nothing is deployed to a cloud provider: instances and costs are simulated, so no real permission or billing applies. Real actions only happen in API mode, where protection comes from the server API token, the instance quota, and the IAM role.

## Safety and persistence

- SQLite is included with standard Python builds; no paid database service is required for this configuration.
- The database persists only when its file is placed on a persistent disk. The EC2 setup uses its attached EBS volume.
- Keep backups. Do not store passwords, API keys, or private personal information in task descriptions.
- S3 object storage is not connected; the AWS account inventory showed no buckets in accessible regions. Create one only after reviewing ownership, access controls, and possible charges.
- Never commit environment files or tokens.
