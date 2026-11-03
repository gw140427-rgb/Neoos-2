#!/usr/bin/env bash
set -euo pipefail
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST_DIR="${NEOAGENT_BIN_DIR:-$HOME/.local/bin}"
mkdir -p "$DEST_DIR"
install -m 755 "$SOURCE_DIR/neoagent.py" "$DEST_DIR/neoagent"
if ! printf '%s' "$PATH" | tr ':' '\n' | grep -Fxq "$DEST_DIR"; then
  echo "설치 완료: $DEST_DIR/neoagent"
  echo "현재 셸에서 실행하려면:"
  echo "  export PATH=\"$DEST_DIR:\$PATH\""
else
  echo "설치 완료: $DEST_DIR/neoagent"
fi
echo "빠른 시작:"
echo "  neoagent register planner --role coordinator"
echo "  neoagent register research --role researcher"
echo "  neoagent register coder --role coder"
echo "  neoagent send planner research '프로젝트 요구사항 조사'"
echo "  neoagent inbox research"
