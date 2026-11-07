# NeoOS AI Auto-Development — Phase 1 and Local Role Pipeline

## Goal

Provide a phone-friendly, local-first execution controller and local model analysis pipeline. Model output remains a proposal until a person reviews it.

## Current implementation

- `neoos_autodev.py` validates versioned JSON execution plans.
- Plans contain fixed action identifiers, never arbitrary shell command strings.
- Initial allowlist: Python compile check, repository unit tests, and read-only Git status.
- Execution requires the explicit `--approve-execution` flag.
- Per-step retries are capped at 3; per-step timeout is capped at 10 minutes; plan runtime is capped at 24 hours.
- Deployment, deletion, package installation, cloud mutations, and arbitrary shell execution are not available.
- `neoos_local_ai.py` connects to a local OpenAI-compatible model endpoint and runs five role-separated prompts sequentially: Researcher, Developer, Tester, Infrastructure, and Reviewer.
- The local-model adapter only permits loopback hosts (localhost / 127.0.0.1 / ::1). External and LAN endpoints are rejected.
- AI output is advisory text only. The role pipeline does not edit files, run commands, create commits, or deploy.

## Local model setup

The default endpoint is Ollama's local OpenAI-compatible API:

```sh
export NEOOS_AI_BASE_URL=http://127.0.0.1:11434/v1
export NEOOS_AI_MODEL=YOUR_INSTALLED_MODEL
python neoos_local_ai.py models
python neoos_local_ai.py run --task "Review the NeoOS task worker" --output reports/role-review.json
```

For another local OpenAI-compatible server, set `NEOOS_AI_BASE_URL` to its loopback `/v1` endpoint. No API key is required by the local-first path. If a local server is not running or the requested model is not installed, the command reports the connection error; it does not silently switch to a cloud service.

The adapter uses Python's standard library only. The local inference server and model must be installed separately.

## Execution controller

Run from the repository root:

```sh
python neoos_autodev.py policy
python neoos_autodev.py validate plans/neoos-ai-autodev.json
python neoos_autodev.py run plans/neoos-ai-autodev.json --approve-execution
```

The baseline plan runs compile checks, unit tests, and Git status. Explicit approval is required before any step runs.

## Agent architecture boundary

The Researcher, Developer, Tester, Infrastructure, and Reviewer entries are role-separated prompts sent one after another to **one local model**. They are not independent or parallel subagents. The Main role is the controller that sequences work and collects results. A genuine multi-agent runtime is not wired in this phase.

## Safety and limitations

The controller is **not an operating-system sandbox**. Python tests and compile steps execute trusted repository code with the current user's permissions. Do not run plans against untrusted repositories. The role pipeline treats task text and model replies as untrusted data. It never grants the model tools.

No code is automatically edited, no arbitrary commands are executed, and no cloud infrastructure is changed by the local-model pipeline. Deployment, deletion, and modifications to `main` remain outside this phase. Work should be reviewed in a feature branch and merged only after verification.

## Verification

```sh
python -m compileall -q neoos_mcp.py worker.py neoos_autodev.py neoos_local_ai.py tests
python -m unittest discover -s tests -v
python neoos_autodev.py validate plans/neoos-ai-autodev.json
```

CI runs compilation, repository unit tests, and baseline plan validation on pull requests.
