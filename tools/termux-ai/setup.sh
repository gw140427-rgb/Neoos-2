#!/usr/bin/env bash
# YangYang AI Room — Termux installer
set -Eeuo pipefail

REPO_RAW="https://raw.githubusercontent.com/gw140427-rgb/Neoos-2/main/tools/termux-ai"
TARGET_NAME="yangyang-ai"

say() { printf '%s\n' "$*"; }
fail() { printf '오류: %s\n' "$*" >&2; exit 1; }

command -v curl >/dev/null 2>&1 || fail "curl이 필요해요. Termux에서 먼저 실행: pkg install curl"
command -v bash >/dev/null 2>&1 || fail "bash를 찾을 수 없어요."

if [[ -n "${PREFIX:-}" && -d "$PREFIX/bin" ]]; then
  BIN_DIR="$PREFIX/bin"
else
  BIN_DIR="$HOME/.local/bin"
  mkdir -p "$BIN_DIR"
fi

TMP_FILE="$(mktemp)"
cleanup() { rm -f "$TMP_FILE"; }
trap cleanup EXIT

say "YangYang AI Room 설치 파일을 가져오는 중..."
curl --fail --location --silent --show-error --retry 2 \
  "$REPO_RAW/yangyang-ai.sh" -o "$TMP_FILE" ||
  fail "다운로드에 실패했어요. 인터넷 연결을 확인해 주세요."

[[ -s "$TMP_FILE" ]] || fail "다운로드 파일이 비어 있어요."
head -n 1 "$TMP_FILE" | grep -qE '^#!/usr/bin/env bash$' ||
  fail "받은 파일이 실행 스크립트 형식이 아니에요."

DEST="$BIN_DIR/$TARGET_NAME"
if [[ -e "$DEST" ]]; then
  BACKUP="$DEST.backup.$(date +%Y%m%d-%H%M%S)"
  cp -p "$DEST" "$BACKUP" || fail "기존 실행기 백업에 실패했어요."
  say "기존 실행기를 백업했어요: $BACKUP"
fi

chmod 700 "$TMP_FILE"
install -m 755 "$TMP_FILE" "$DEST" || fail "실행기 설치에 실패했어요."

say ""
say "설치 완료: $DEST"
case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *)
    say "현재 PATH에 $BIN_DIR 이 없어요."
    say "다음 줄을 ~/.bashrc에 추가한 뒤 셸을 다시 시작하세요:"
    printf 'export PATH="%s:$PATH"\n' "$BIN_DIR"
    ;;
esac
say "실행: yangyang-ai"
say "기존 Codex / Hermes / OpenCode / OpenClaw 설치 상태를 확인해 연결해요."
