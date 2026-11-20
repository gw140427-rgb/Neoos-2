# NeoOS

커널부터 직접 만드는 장난감 OS. 이름: NeoOS (2026-11-20 확정).

## 목표 사양 (타깃 머신)

- CPU: ARM64 (AArch64)
- RAM: 최소 512MB, 권장 1GB
- 저장공간: 최소 64MB (커널 자체는 수 MB)
- 화면: 1024x768 프레임버퍼
- 입력: 키보드 (현재는 시리얼, 이후 USB)
- 실행 환경: QEMU virt → 이후 폰 Vectras VM

설계 원칙: 가볍게. 폰 에뮬레이션(Vectras, KVM 없음)에서도 돌아야 한다.

## 부가 사양

- 부팅 방식: QEMU -kernel 직접 로드 (UEFI 아님)
- CPU 코어: 싱글코어로 시작, 멀티코어는 나중
- 그래픽 가속: 없음, 소프트웨어 렌더링만 (프레임버퍼에 직접 그림)
- 네트워크: 초기 없음, 이후 virtio-net
- 저장장치: 초기엔 램만 사용, 이후 virtio-blk
- 사운드: 없음 (계획 없음)
- USB: 나중 단계
- 타이머: ARM generic timer
- 종료/재부팅: PSCI 호출
- 보안부팅: 없음

## 진행 상황

- 1단계: 부팅 + 시리얼 출력 — 완료 (2026-11-20, QEMU 검증)
- 2단계: 시리얼 입력 + 에코 (neo> 프롬프트) — 완료 (2026-11-20, QEMU 검증)
- 3단계: ramfb 프레임버퍼 화면 출력 — 완료 (2026-11-20, 스크린샷 검증: 배경+패널+"NeoOS" 글자. 고친 것 3개: fw_cfg 설정은 DMA로 써야 함, -mgeneral-regs-only, DMA 구조체 volatile)
- 4단계: 타이머/인터럽트
- 5단계: 메모리 관리
- 6단계: 프로세스/스케줄링
- 7단계: 파일시스템 + 셸

## 빌드/실행 (VPS /data/home/os-project/)

```
make
qemu-system-aarch64 -machine virt -cpu cortex-a57 -nographic -kernel kernel.elf -device ramfb
```
