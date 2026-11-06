#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "$0")" && pwd)"
APP_DIR="$HOME/.local/share/termux-ai"
if command -v pkg >/dev/null 2>&1; then
  command -v python >/dev/null 2>&1 || pkg install -y python
  BIN_DIR="${PREFIX:-$HOME/.local}/bin"
else
  command -v python3 >/dev/null 2>&1 || { echo "Python 3가 필요해." >&2; exit 1; }
  BIN_DIR="$HOME/.local/bin"
  mkdir -p "$BIN_DIR"
fi
mkdir -p "$APP_DIR" "$BIN_DIR"
cp "$SCRIPT_DIR/termux_ai.py" "$APP_DIR/termux_ai.py"
PYTHON_BIN="$(command -v python || command -v python3)"
cat > "$BIN_DIR/termux-ai" <<LAUNCHER
#!/data/data/com.termux/files/usr/bin/bash
exec "$PYTHON_BIN" "$APP_DIR/termux_ai.py" "\$@"
LAUNCHER
chmod 700 "$BIN_DIR/termux-ai"
echo "설치 완료! 실행: termux-ai"
case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *) echo "PATH에 추가해 줘: export PATH=\"$BIN_DIR:\$PATH\"" ;;
esac
