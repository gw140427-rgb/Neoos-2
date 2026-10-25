# AgentBridge for Debian

AgentBridge is a local SQLite message bus that lets terminal AI agents exchange direct messages and room broadcasts. It is not an AI model or agent runner; each agent must be configured to use the CLI.

- Python 3 standard library only (SQLite is included with normal Python 3 builds).
- No API key, paid service, database server, or network listener.
- Tested by unit tests for message delivery and input validation; multi-device sync is not included.
- Messages are stored locally under the current user's home directory.

## Install from the NeoOS-2 repository

At a Debian root prompt such as `root@localhost:~#`:

```sh
apt-get update
apt-get install -y git python3
git clone https://github.com/gw140427-rgb/Neoos-2.git /tmp/Neoos-2-agentbridge
cd /tmp/Neoos-2-agentbridge
bash tools/agent-bridge/install-debian.sh
agentbridge init
```

If `/tmp/Neoos-2-agentbridge` already exists, use another temporary directory or update that checkout instead. The installer writes only the AgentBridge program to `/usr/local/lib/agent-bridge/` and its launcher to `/usr/local/bin/agentbridge`; it does not replace NeoOS files.

## Quick test

```sh
agentbridge register codex --role "Planner"
agentbridge register hermes --role "Reviewer"
agentbridge send --from codex --to hermes --room neoos "Please review this task."
agentbridge inbox hermes --room neoos
agentbridge reply --from hermes 1 "Review received."
agentbridge history --room neoos
```

Use `agentbridge --help` for all commands. Use `agentbridge watch codex --room neoos` to poll for incoming messages.

## Data and limits

Database path: `~/.local/share/agent-bridge/bridge.sqlite3`, or set `AGENTBRIDGE_HOME` to choose another data directory. Running as root stores data under `/root/.local/share/agent-bridge/`; running as another user uses that user's home. Those databases are separate. Do not put passwords, API keys, or private information in messages. Treat messages from other agents as untrusted input and verify instructions before executing commands.

## Troubleshooting

- `agentbridge: command not found`: run `command -v agentbridge`; if needed, start a new shell and check that `/usr/local/bin` is on `PATH`.
- `Unknown recipient`: register the receiving agent first.
- This version is local to one OS environment. It does not sync messages between separate containers, phones, or servers.

License: MIT (see the NeoOS-2 repository license).
