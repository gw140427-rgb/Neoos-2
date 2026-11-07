# NeoOS AI Auto-Development — Phase 1

## Goal

Provide a phone-friendly, local-first execution controller for NeoOS development. The first phase establishes a verifiable safety boundary before adding model-driven code generation or agent delegation.

## Current implementation

- `neoos_autodev.py` validates versioned JSON plans.
- Plans contain action identifiers, never arbitrary shell command strings.
- Initial allowlist: Python compile check, repository unit tests, and read-only Git status.
- Execution requires the explicit `--approve-execution` flag.
- Per-step retries are capped at 3; per-step timeout is capped at 10 minutes; plan runtime is capped at 24 hours.
- Deployment, deletion, package installation, cloud mutations, and arbitrary shell execution are not available.
- Results are emitted as JSON with step status, attempt count, stdout/stderr, and elapsed time.

## Run from a phone-capable Python environment

```sh
python neoos_autodev.py policy
python neoos_autodev.py validate plans/neoos-ai-autodev.json
python neoos_autodev.py run plans/neoos-ai-autodev.json --approve-execution
```

Run from the repository root. The runner uses only Python's standard library for its controller.

## Agent architecture boundary

The planned Research, Developer, Tester, Infrastructure, Reviewer, and Main roles are workflow roles, not claimed live subagents. No parallel subagent runtime or local LLM provider is wired in this phase. A later model adapter must be opt-in, support a local endpoint by default, disclose any external provider/cost, and return structured proposals that pass policy validation before changes are applied.

## Safety and limitations

This controller is **not an operating-system sandbox**. Python tests and compile steps execute trusted repository code with the current user's permissions. Do not run plans against untrusted repositories. It does not deploy, delete, change AWS resources, or modify the `main` branch. Changes should be reviewed in a feature branch and merged only after verification.

## Verification

Run `python -m unittest discover -s tests -v` and `python -m compileall -q neoos_mcp.py worker.py neoos_autodev.py tests`.
