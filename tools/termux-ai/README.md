# YangYang AI Room for Termux

A small terminal launcher for AI command-line tools that are already installed on your device.

## Install

In Termux:

```bash
pkg install curl -y
curl -fsSL https://raw.githubusercontent.com/gw140427-rgb/Neoos-2/main/tools/termux-ai/setup.sh | bash
```

Then start it:

```bash
yangyang-ai
```

## Commands

- `yangyang-ai` — open the terminal menu.
- `yangyang-ai status` — show which supported CLIs are available.
- `yangyang-ai doctor` — check the environment and whether common config folders exist.
- `yangyang-ai chat` — launch the first available tool in this order: Codex, Hermes, OpenCode, OpenClaw.
- `yangyang-ai codex`, `hermes`, `opencode`, `openclaw` — launch a specific installed tool.
- `yangyang-ai help` — show help.

Arguments after a tool name are passed directly to that tool.

## Important

This project is a launcher, not an AI model or cloud service. It does not download model weights, create API keys, log in to accounts, or silently install heavyweight agents. Install and sign in to the AI CLIs you choose separately.

The launcher does not print API keys or read the contents of credential files. The installer backs up an existing `yangyang-ai` executable before replacing it. It does not change or delete existing Codex, Hermes, OpenCode, or OpenClaw configuration.

## Files

- `setup.sh` — downloads and installs the launcher into Termux's executable directory.
- `yangyang-ai.sh` — menu, status checks, diagnostics, and command dispatcher.
