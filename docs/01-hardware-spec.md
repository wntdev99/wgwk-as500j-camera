# 01. 카메라 하드웨어 사양

> 출처: `ref/simple_spec.pdf` — 벤더 제공 영문 사양서(전각 문자 혼용 원본).

## 기본 정보

| 항목 | 값 |
|---|---|
| **Model NO.** | `WGWK-AS500J` |
| **Main control chip** | SigmaStar `SSC377D` |
| **Image sensor** | Sony `IMX335` — 5 MP, 1/2.8" CMOS |

## 비디오 처리

- **코덱**: H.265+ / H.265 / H.264
- **비트레이트**: 0.1 ~ 12 Mbps (가변)
- **프레임레이트**: 1 ~ 20 fps (가변)
- **메인 스트림 해상도/프레임레이트**
  - `3840×2160` @ 20 fps
  - `3072×2048`, `2592×1944`, `2560×1440`, `2304×1296`, `1920×1080`, `1280×720` @ 25 fps
  - 정사각 해상도: `1944×1944`, `1200×1200` 지원(보조 사양서 항목)
- **서브 스트림 해상도**: `720×480`, `D1`, `VGA`, `640×360`
- 메인/서브 스트림 모두 H.264·H.265 인코딩 지원

> 주: 원본 사양서에는 두 가지 비디오 처리 블록이 함께 기재되어 있어 두 가지 펌웨어/설정 변형의 차이일 수 있습니다(서브스트림 D1·VGA·640×360 vs. 720×480·D1·VGA·640×360 등). 실기 확인이 필요한 부분입니다.

## 오디오

- **오디오 입출력**: 라인 입력 1 ch, 라인 출력 1 ch
- **오디오 처리**: G.711 코딩, **양방향 음성 인터컴(two-way voice intercom)** 지원
- **A/V 동기화** 지원

## IRCUT (주야간 전환)

- 통합 IRCUT 스위칭 회로 내장
- 4가지 제어 모드: 자동 / 외부 제어 / 수동 / 시간 예약
- 보광등 보드 인터페이스: PWM 적외선(IR) + PWM 백색광

## 광학 줌 (이 레포의 핵심 관심사)

> 원문 인용:
> *"Support electric zoom and auto focus interface, need to be matched with zoom lens, zoom control board and zoom program."*

**해석**: 카메라 본체는 **전동 줌(electric zoom)과 자동 초점(AF)을 위한 인터페이스를 제공**할 뿐이며, 실제 동작을 위해서는 다음 세 가지가 함께 결합되어야 합니다.

1. **줌 렌즈(zoom lens)** — 물리적 광학 줌이 가능한 가변초점 렌즈 모듈
2. **줌 제어 보드(zoom control board)** — 렌즈의 모터를 구동하는 PCB
3. **줌 프로그램(zoom program)** — 위 보드를 제어하는 펌웨어/SDK 측 지원 로직

따라서 본 카메라 모듈을 단독으로 구매해도 광학 줌 동작이 보장되지 않으며, 벤더가 제공하는 줌 렌즈/보드/펌웨어 셋과 함께 패키지로 도입해야 합니다.

## 네트워크 및 프로토콜

- **이더넷**: RJ45 1 포트, 10/100 M 적응형
- **지원 프로토콜**: HTTP / RTSP / DHCP / NTP / ONVIF 등
- **API**:
  - HTTP API(HAPI) — 본 자료에 포함된 `http_api.pdf` 참조
  - RTSP 스트림 — `/HAPI/V1.0/sysinfo/rtspurl` 응답 기준 `rtsp://<IP>:554/stream0`(메인), `rtsp://<IP>:554/stream1`(서브)

## 부가 기능 (Business functions)

- OSD 지원
- 실시간 A/V 전송
- **정밀 인체 검출(humanoid detection)**
- 이중 광원 경보(dual light source alarm), 음성 경보(sound alarm)
- 동작 인식 / 객체 검출 / 얼굴 검출 / 차량 검출 / 번호판 인식 / 화염 검출 등 스마트 분석(HAPI 능력집 기준)

## 전원·환경

- **전원**: DC 12 V 입력, 소비 전류 130 mA (≈ 1.56 W)
- **신뢰성**: 전원·네트워크 종합 낙뢰 보호 — 국가표준 `GB/T 17626.5` 및 국제표준 `IEC 61000-4-5` 준수
- **동작 온도**: -40 °C ~ +65 °C

## 통합 시 고려사항

| 항목 | 내용 |
|---|---|
| 전원 설계 | DC 12 V 단일 전원. PoE는 사양서상 미언급(필요 시 외부 PoE 스플리터 사용) |
| 호스트 플랫폼 | NETSDK가 aarch64용으로 제공되므로 ARM64 SBC(예: NVIDIA Jetson, Raspberry Pi 64-bit, RK3588 등)와 자연스러운 매칭 |
| 실시간성 | RTSP 스트림 + HAPI 제어 분리 운용 권장. 줌 명령은 `autostop` 파라미터로 지속시간 제어 |
| 줌 동작 검증 | 실기 도입 시 `/sysinfo/capability` 응답의 `ele_zoom`, `zoom_track`, `dzoomsetting`, `ptz_zoom` 같은 capability 문자열이 포함되는지 사전 확인 필요 |
