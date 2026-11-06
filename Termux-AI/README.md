# Termux AI

Termux/Android에서 실행하는 가벼운 터미널 AI 채팅 프로그램이야. Python 표준 라이브러리만 사용해.

## 설치

```bash
pkg update
pkg install -y git
 git clone -b termux-ai https://github.com/gw140427-rgb/Neoos-2.git
cd Neoos-2/Termux-AI
bash install.sh
termux-ai
```

첫 실행에서 OpenAI 호환 API 주소, 모델, API 키를 설정해. 기본 모델은 OpenRouter의 무료 라우터 `openrouter/free`이며 무료 제공량 제한이 있을 수 있어.

## 명령어

- `/help` 도움말
- `/model 모델ID` 모델 변경
- `/system 안내문` 시스템 안내문 변경
- `/clear` 대화 초기화
- `/setup` API 설정
- `/save` 대화 저장
- `/exit` 종료

설정은 `~/.config/termux-ai/config.json`, 대화 기록은 `~/.local/share/termux-ai/history.json`에 저장돼. API 키와 대화 기록은 저장소에 포함되지 않아.
