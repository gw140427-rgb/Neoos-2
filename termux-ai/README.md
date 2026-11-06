# Termux AI 1.0

A lightweight Korean-friendly AI chat client for Android Termux. It uses Python's standard library only; no `pip install` is required.

## Install on Termux

```bash
pkg update -y
pkg install -y python curl
curl -fsSL https://raw.githubusercontent.com/gw140427-rgb/Neoos-2/termux-ai-v1/termux-ai/install.sh | bash
termux-ai setup
termux-ai
```

The default provider is OpenRouter's **free-only** model router (`openrouter/free`). It selects from available free models. This is cloud inference, so an internet connection and an API key are needed. Free services can have daily limits, queues, or temporary unavailability. Termux AI does not switch to paid models automatically.

## Commands

```bash
termux-ai setup             # configure provider, model, and API key
termux-ai                   # interactive chat
termux-ai ask "안녕!"       # one question
```

Inside chat: `/help`, `/reset`, `/model`, `/exit`.

## Other OpenAI-compatible providers

During `termux-ai setup`, enter an OpenAI-compatible API base URL ending in `/v1` and the model ID supported by that provider. For a local server on the same phone, `http://127.0.0.1:11434/v1` is accepted. Plain HTTP to non-local hosts is rejected.

## Security and privacy

- API keys are entered with hidden terminal input and saved only in `~/.config/termux-ai/config.json`.
- The config file is created with owner-only permissions (`0600`) where the filesystem supports it.
- The project does not upload or commit your API key, chat history, or local configuration.
- Chat history exists only in memory while the program is running and is not written to disk by this app.
- Never paste your API key into a GitHub issue, commit, screenshot, or chat message.

## Requirements

- Android with Termux
- Python 3
- Internet access for cloud providers

No root access is needed.
