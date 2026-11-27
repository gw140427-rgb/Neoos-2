#!/usr/bin/env bash
set -euo pipefail

REPO=/data/workspace/Neoos-2
export OLLAMA_MODELS=/data/ollama-models
export OLLAMA_HOST=127.0.0.1:11434

if ! pgrep -f '/data/ollama/bin/ollama serve' >/dev/null; then
  setsid /data/ollama/bin/ollama serve </dev/null >/data/tmp/opencode/ollama.log 2>&1 &
fi

if ! pgrep -f 'neo_ai_server.py' >/dev/null; then
  setsid env NEO_HOST=0.0.0.0 NEO_PORT=8091 python3 "$REPO/neo_ai_server.py" </dev/null >/data/tmp/opencode/neo-ai.log 2>&1 &
fi

sleep 2
instabox-port publish 8091 --name neo-ai >/dev/null 2>&1 || true
curl -fsS http://127.0.0.1:8091/health
