#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "$0")" && pwd)"
cd "$SCRIPT_DIR"
command -v pkg >/dev/null 2>&1 || { echo "Termux에서 실행해 줘." >&2; exit 1; }
pkg install -y git gh
gh auth status >/dev/null 2>&1 || gh auth login
LOGIN="$(gh api user --jq .login)"
REPO_NAME="${1:-Termux-AI}"
[[ "$REPO_NAME" =~ ^[A-Za-z0-9._-]+$ ]] || { echo "잘못된 저장소 이름이야." >&2; exit 1; }
echo "GitHub 계정: $LOGIN"
read -r -p "공개 저장소로 만들까? [y/N] " VIS
if [[ "$VIS" =~ ^[Yy]$ ]]; then VISIBILITY="--public"; else VISIBILITY="--private"; fi
if [[ ! -d .git ]]; then git init; fi
git branch -M main
git config user.name "$LOGIN"
if [[ -z "$(git config user.email || true)" ]]; then
  USER_ID="$(gh api user --jq .id)"
  git config user.email "$USER_ID+$LOGIN@users.noreply.github.com"
fi
git add .
git diff --cached --quiet || git commit -m "Initial Termux AI release"
if gh repo view "$LOGIN/$REPO_NAME" >/dev/null 2>&1; then
  echo "이미 저장소가 있어. 기존 저장소를 덮어쓰지 않고 중단했어." >&2
  exit 2
fi
gh repo create "$LOGIN/$REPO_NAME" "$VISIBILITY" --source=. --remote=origin --push --description "Lightweight AI chat client for Termux and Android"
echo "업로드 성공: https://github.com/$LOGIN/$REPO_NAME"
