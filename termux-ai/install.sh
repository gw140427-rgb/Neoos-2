#!/data/data/com.termux/files/usr/bin/bash
set -eu

if [ -z "\${PREFIX:-}" ] || [ ! -d "$PREFIX" ]; then
  echo "이 설치 스크립트는 Android Termux에서 실행해야 합니다."
  exit 1
fi

if ! command -v python >/dev/null 2>&1; then
  echo "Python 설치 중..."
  pkg install -y python
fi

DEST="$PREFIX/bin/termux-ai"
RAW_URL="https://raw.githubusercontent.com/gw140427-rgb/Neoos-2/termux-ai-v1/termux-ai/termux_ai.py"
TMP="\${DEST}.download"

python - "$RAW_URL" "$TMP" <<'PY'
import sys
import urllib.request

url, destination = sys.argv[1], sys.argv[2]
request = urllib.request.Request(url, headers={"User-Agent": "termux-ai-installer/1.0"})
with urllib.request.urlopen(request, timeout=30) as response:
    data = response.read()
if not data.startswith(b"#!/usr/bin/env python3"):
    raise SystemExit("다운로드한 파일을 확인할 수 없습니다. 설치를 중단합니다.")
with open(destination, "wb") as handle:
    handle.write(data)
PY

mv "$TMP" "$DEST"
chmod 700 "$DEST"
echo "Termux AI 설치 완료!"
echo "다음 명령을 실행하세요: termux-ai setup"
echo "설정 후 실행: termux-ai"
