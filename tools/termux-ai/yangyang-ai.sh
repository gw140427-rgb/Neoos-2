#!/usr/bin/env bash
# YangYang AI Room — lightweight launcher for AI CLIs already installed on this device.
set -Eeuo pipefail

APP_NAME="YangYang AI Room"
VERSION="1.0.0"
NO_COLOR="${NO_COLOR:-}"
if [[ -t 1 && -z "$NO_COLOR" ]]; then
  C_CYAN=$'\033[36m'; C_GREEN=$'\033[32m'; C_YELLOW=$'\033[33m'
  C_RED=$'\033[31m'; C_BOLD=$'\033[1m'; C_RESET=$'\033[0m'
else
  C_CYAN=""; C_GREEN=""; C_YELLOW=""; C_RED=""; C_BOLD=""; C_RESET=""
fi

info() { printf '%s\n' "$*"; }
ok() { printf '%s✓%s %s\n' "$C_GREEN" "$C_RESET" "$*"; }
warn() { printf '%s!%s %s\n' "$C_YELLOW" "$C_RESET" "$*"; }
err() { printf '%s오류:%s %s\n' "$C_RED" "$C_RESET" "$*" >&2; }

banner() {
  printf '%s' "$C_CYAN"
  cat <<'BANNER'
 __   __                   __
 \ \ / /__ _ __   __ _ ___/ /__  _ __   __ _
  \ V / _ \ '_ \ / _` / __| '_ \| '_ \ / _` |
   | |  __/ | | | (_| \__ \ | | | | | | (_| |
   |_|\___|_| |_|\__,_|___/_| |_|_| |_|\__,_|
BANNER
  printf '%s%s%s\n' "$C_RESET" "$C_BOLD" "             AI ROOM  v$VERSION"
  printf '%s기존에 설치된 AI CLI를 한곳에서 실행합니다.%s\n\n' "$C_CYAN" "$C_RESET"
}

has() { command -v "$1" >/dev/null 2>&1; }

run_agent() {
  local name="$1"
  shift
  if ! has "$name"; then
    err "$name 실행 파일을 찾지 못했어요."
    info "먼저 해당 도구를 설치하고 로그인해 주세요. 이 실행기는 기존 설정을 삭제하거나 API 키를 만들지 않아요."
    return 127
  fi
  info "$name 실행 중..."
  "$name" "$@"
}

status() {
  local name
  printf '%s%-12s %-12s%s\n' "$C_BOLD" "도구" "상태" "$C_RESET"
  for name in codex hermes opencode openclaw; do
    if has "$name"; then
      printf '%-12s %s사용 가능%s\n' "$name" "$C_GREEN" "$C_RESET"
    else
      printf '%-12s %s설치 안 됨%s\n' "$name" "$C_YELLOW" "$C_RESET"
    fi
  done
}

doctor() {
  info "== 기기 진단 =="
  printf 'OS: %s\n' "$(uname -s 2>/dev/null || printf unknown)"
  printf 'Architecture: %s\n' "$(uname -m 2>/dev/null || printf unknown)"
  printf 'Shell: %s\n' "${BASH_VERSION:-unknown}"
  if [[ "${PREFIX:-}" == *"/com.termux/files/usr" ]]; then
    ok "Termux 환경 감지"
  else
    warn "Termux PREFIX가 감지되지 않았어요. 일반 Linux에서도 실행할 수 있어요."
  fi
  info ""
  status
  info ""
  info "설정 폴더 존재 여부(내용은 열거나 출력하지 않음):"
  local dir
  for dir in "$HOME/.codex" "$HOME/.hermes" "$HOME/.config/opencode" "$HOME/.openclaw"; do
    if [[ -d "$dir" ]]; then
      ok "$dir"
    else
      info "  없음: $dir"
    fi
  done
}

chat() {
  if has codex; then run_agent codex "$@"; return $?; fi
  if has hermes; then run_agent hermes "$@"; return $?; fi
  if has opencode; then run_agent opencode "$@"; return $?; fi
  if has openclaw; then run_agent openclaw "$@"; return $?; fi
  err "실행 가능한 AI CLI가 없어요. Codex, Hermes, OpenCode 또는 OpenClaw를 먼저 설치해 주세요."
  return 127
}

help_text() {
  cat <<'HELP'
사용법:
  yangyang-ai                 대화형 메뉴 열기
  yangyang-ai status          AI 도구 설치 상태 보기
  yangyang-ai doctor          Termux 및 설정 폴더 진단
  yangyang-ai chat [인자...]  설치된 도구 중 Codex 우선 실행
  yangyang-ai codex [인자...] Codex 실행
  yangyang-ai hermes [인자...] Hermes 실행
  yangyang-ai opencode [인자...] OpenCode 실행
  yangyang-ai openclaw [인자...] OpenClaw 실행
  yangyang-ai help            도움말

API 키와 로그인 정보는 화면에 표시하거나 자동 변경하지 않습니다.
HELP
}

menu() {
  local choice
  while true; do
    banner
    status
    printf '\n%s1%s Codex     %s2%s Hermes\n' "$C_CYAN" "$C_RESET" "$C_CYAN" "$C_RESET"
    printf '%s3%s OpenCode  %s4%s OpenClaw\n' "$C_CYAN" "$C_RESET" "$C_CYAN" "$C_RESET"
    printf '%s5%s 진단      %s0%s 종료\n' "$C_CYAN" "$C_RESET" "$C_CYAN" "$C_RESET"
    printf '\n선택: '
    if ! IFS= read -r choice; then return 0; fi
    case "$choice" in
      1) run_agent codex || true ;;
      2) run_agent hermes || true ;;
      3) run_agent opencode || true ;;
      4) run_agent openclaw || true ;;
      5) doctor ;;
      0|q|Q) info "YangYang AI Room 종료."; return 0 ;;
      *) warn "메뉴에서 번호를 선택해 주세요." ;;
    esac
    printf '\n계속하려면 Enter: '
    IFS= read -r _ || true
    printf '\n'
  done
}

main() {
  local action="${1:-menu}"
  if [[ $# -gt 0 ]]; then shift; fi
  case "$action" in
    menu) menu ;;
    status) status ;;
    doctor) doctor ;;
    chat) chat "$@" ;;
    codex|hermes|opencode|openclaw) run_agent "$action" "$@" ;;
    help|-h|--help) help_text ;;
    --version|-v) info "$APP_NAME $VERSION" ;;
    *) err "알 수 없는 명령: $action"; help_text; return 2 ;;
  esac
}

main "$@"
