# NeoAgent (Debian / Termux)

A tiny local message bus that lets multiple CLI agents or human-operated agent sessions exchange tasks. Python standard library only; no API key, server, root access, or extra pip packages required.

## Install

From the repository root:

```bash
cd tools/neoagent
bash install.sh
export PATH="$HOME/.local/bin:$PATH"
neoagent status
```

Or download this directory and run `python3 neoagent.py --help` directly.

## Quick start

```bash
neoagent register planner --role coordinator
neoagent register research --role researcher
neoagent register coder --role coder
neoagent register reviewer --role reviewer
neoagent send planner research "조사: 현재 프로젝트 구조와 위험 요소를 요약해줘"
neoagent inbox research
neoagent send research planner "조사 결과: ..."
neoagent send planner coder "요구사항에 맞게 구현 계획을 작성해줘"
neoagent send coder reviewer "변경 사항을 검토해줘"
neoagent agents
neoagent status
```

For a live inbox poll, run `neoagent watch coder` in a separate terminal. Broadcast to every other registered agent with `neoagent send planner '*' "공유 공지"`.

## Important boundaries

- This is a **message bus**, not an LLM by itself. Start Codex, OpenCode, Hermes, or other CLI sessions separately and give each session its agent name/inbox instructions.
- The optional `--command` field is descriptive only. NeoAgent never executes registered commands or arbitrary shell input.
- Messages are stored locally in SQLite at `~/.local/share/neoagent/neoagent.sqlite3` by default. Override with `NEOAGENT_DATA_DIR=/path`.
- No files outside its data directory are edited or deleted. No automatic network calls, deployments, or API billing.
- It is designed for agents on the **same Linux/Termux environment**. It does not provide cross-device networking or autonomous model-to-model reasoning by itself.

## Troubleshooting

- If `neoagent: command not found`, run `export PATH="$HOME/.local/bin:$PATH"`.
- Check Python with `python3 --version` (Python 3.9+ recommended).
- Inspect pending messages with `neoagent inbox AGENT_NAME`; `--all` includes already-read messages.
