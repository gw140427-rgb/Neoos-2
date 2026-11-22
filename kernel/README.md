# NeoOS

커널부터 직접 만드는 장난감 OS. 이름: NeoOS (2026-11-20 확정).

## 목표 사양 (타깃 머신)

- CPU: ARM64 (AArch64)
- RAM: 최소 512MB, 권장 1GB
- 저장공간: 최소 64MB (커널 자체는 수 MB)
- 화면: 1024x768 프레임버퍼
- 입력: virtio 키보드+태블릿 (시리얼은 폴백으로 유지)
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
- 4단계: 타이머/인터럽트 — 완료 (2026-11-20, GIC+ARM generic timer로 1초마다 tick 1~14 확인, 에코와 동시 동작)
- 5단계: 메모리 관리 — 완료 (2026-11-20, 4KB 페이지 비트맵 할당자 자체 테스트 통과: 할당/해제/재사용/패턴 검증, 124MB 관리)
- 6단계: 프로세스/스케줄링 — 완료 (2026-11-20, tick마다 강제 전환되는 선점형 멀티태스킹 검증: 에코 루프와 B 카운터 1~210 동시 실행)
- 7단계: 파일시스템 + 셸 — 완료 (2026-11-20, RAM 파일시스템 + help/ls/write/cat/rm/mem/clear 셸 검증. 1~7단계 사다리 전부 완료)
- 확장: UEFI 부트로더(uefi/loader.c)로 커널을 디스크 이미지(neoos.img, 64MB GPT+ESP)에서 부팅 — 완료 (2026-11-20, AAVMF 자동 부팅 + 화면/셸 검증)
- 부팅 견고성 수정 (2026-11-22): 폰 Vectras(ARM64 VM)에서 커널 진입 즉시 Synchronous Exception으로 죽던 문제. 원인: EDK2가 EL2로 핸드오프하는 환경(QEMU virt,virtualization=on으로 재현)인데 로더는 SCTLR_EL1만 끄고 커널은 EL1·MMU-off 핸드오프를 가정했음. 수정: boot.S가 CurrentEL을 보고 EL2/EL3면 EL1으로 정식 강등(eret), EL1에서 MMU를 직접 끄고 벡터를 조기에 설치, 스택 주소는 리터럴 로드 없이 PC-relative로 계산. 로더도 실행 중인 레벨의 SCTLR를 끄도록 수정. virtualization=on / cpu max+512MB 조합 포함해 GUI 부팅 검증 완료. 별개로 GICv3 머신에서는 기존 GICv2 드라이버가 나중에 데이터 중단으로 멈추는 한계가 그대로 있음(진입 크래시와 무관, 미해결).
- 8단계: GUI — 완료 (2026-11-22, QEMU 검증: 공개 도메인 8x8 전체 ASCII 폰트, virtio-input 드라이버(태블릿 절대좌표+키보드, virtio-mmio legacy), 창 관리자(상단바 시계, 제목줄 드래그, 클릭 포커스/올리기, 전체 다시그리기로 끌림 자국 없음), 시스템 앱 4종 — 터미널(기존 셸 연결)/시스템 정보/파일/설정(바탕화면 배경색 4종). -kernel 부팅과 UEFI 디스크 이미지 부팅 양쪽에서 화면+입력(커서 이동·타이핑·클릭·드래그) 검증. 고친 것 2개: virtio-mmio 슬롯 간격이 0x1000이 아니라 0x200(32개)인 것, legacy virtqueue는 GuestPageSize를 먼저 써야 PFN이 실제 주소로 해석되는 것)

## 빌드/실행 (VPS /data/home/os-project/)

```
make
qemu-system-aarch64 -machine virt -cpu cortex-a57 -nographic -kernel kernel.elf -device ramfb
```
