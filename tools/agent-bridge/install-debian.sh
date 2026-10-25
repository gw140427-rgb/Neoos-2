#!/usr/bin/env bash
set -eu

REPO_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
DEST_LIB="/usr/local/lib/agent-bridge"
DEST_BIN="/usr/local/bin/agentbridge"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run as root, or use: sudo bash tools/agent-bridge/install-debian.sh" >&2
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is missing. Install it with: apt-get update && apt-get install -y python3" >&2
  exit 1
fi

if [ ! -f "$REPO_DIR/agentbridge.py" ]; then
  echo "Cannot find agentbridge.py beside this installer." >&2
  exit 1
fi

install -d -m 755 "$DEST_LIB"
install -m 644 "$REPO_DIR/agentbridge.py" "$DEST_LIB/agentbridge.py"
cat > "$DEST_BIN" <<'LAUNCHER'
#!/usr/bin/env bash
exec python3 /usr/local/lib/agent-bridge/agentbridge.py "$@"
LAUNCHER
chmod 755 "$DEST_BIN"

echo "AgentBridge 0.2.0 installed: $DEST_BIN"
echo "Initialize it with: agentbridge init"
echo "Data is stored per user at ~/.local/share/agent-bridge/bridge.sqlite3"
