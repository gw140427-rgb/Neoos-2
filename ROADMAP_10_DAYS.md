# NeoOS 10-Day Coding Roadmap

## Scope

Improve the existing NeoOS Rebuild starter in small, reviewable steps. The current project is a task-tracking MCP server plus a report-only worker; this roadmap does not promise that an AI coder will run unattended for ten days. Each day's work is a milestone to complete during an active session.

## Safety rules

- Work on the `automation/neoos-10day-coding-20261016` branch; do not write directly to `main`.
- Preserve existing task data. Tests must use temporary directories and must not touch real user data.
- Never execute queued task text as shell commands.
- Do not deploy services, change account settings, or access secrets as part of this plan.
- Run tests after each code change. Open a pull request for human review; do not auto-merge.

## Day-by-day milestones

| Day | Focus | Deliverable | Acceptance criteria |
| --- | --- | --- | --- |
| 1 | Baseline and guardrails | This roadmap plus worker regression coverage | Existing queued tasks remain unchanged; malformed task JSON is reported and not overwritten. |
| 2 | MCP input validation | Unit tests for task titles, details, status filters, and unknown task IDs | Invalid inputs fail clearly and do not mutate task data. |
| 3 | Task persistence | Harden atomic writes and temporary-file handling | Failed writes do not replace the last valid task file. |
| 4 | Journal reliability | Tests and defensive handling for unreadable or malformed journal lines | One bad journal line does not hide valid neighboring entries. |
| 5 | HTTP authentication | Unit tests for missing, malformed, wrong, and correct bearer tokens | Unauthorized HTTP requests receive 401; token comparison remains constant-time. |
| 6 | Worker reporting | Improve queue summary and malformed-record handling | Worker remains report-only and never executes task contents. |
| 7 | Workflow hardening | Review CI permissions, triggers, and dependency setup | CI runs compile checks and tests without deployment permissions. |
| 8 | Integration tests | Exercise MCP tools with an isolated data directory | Tests do not need production credentials or network access. |
| 9 | Documentation and recovery | Setup, backup/restore, security, and troubleshooting notes | A new contributor can run tests and identify where task data is stored. |
| 10 | Release review | Full regression run and pull request with evidence | All checks are recorded; remaining gaps are listed; no automatic merge. |

## Current baseline

- MCP entry point: `neoos_mcp.py`
- Report-only worker: `worker.py`
- Existing worker regression test: `tests/test_worker.py`
- CI workflow: `.github/workflows/neoos-heartbeat.yml`

## Progress log

- Day 1 started on 2026-10-16 (Asia/Seoul): confirmed the repository baseline and created an isolated working branch.
