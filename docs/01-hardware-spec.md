# 01. 카메라 하드웨어 사양

> 출처: `ref/simple_spec.pdf` — 벤더 제공 영문 사양서(전각 문자 혼용 원본).
> **실기 검증 결과는 본 문서 마지막 §"실기 확인 결과 (2026-05-12)" 절을 우선 참고.** 실측이 사양서와 다른 부분은 실측 값을 신뢰.

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

## 실기 확인 결과 (2026-05-12)

본 절은 실제 수령된 모듈을 LAN에서 직접 점검한 결과로, 사양서와 다른 값을 우선합니다. 전체 데이터는 `docs/06-live-probe-result.md`를 참조.

| 항목 | 사양서 기재 | **실측 값** |
|---|---|---|
| device_type (HAPI) | `MC800S` (사양서 §2.2.1 예시) | **`MC800S5`** — 8 MP 변형 |
| 펌웨어 라벨 | — | `MC800S5_AF_V0-A-RTMP-H5 V3.4.5.2 build 2025-11-12 17:30:10` |
| 디바이스 커널 | — | `Linux 5.10.61 armv7l` (32-bit ARM, **aarch64 NETSDK 직접 탑재 불가**) |
| 출하 메인 스트림 | 사양서엔 다양한 옵션 기재 | **H.265 3840×2160 @ 20 fps VBR 6 000 kbps** (활성) |
| 출하 서브 스트림 | — | **H.265 720×480 @ 20 fps VBR 500 kbps** (활성) |
| 확장 스트림(stream3) | `three_video` 능력 명시 | H.265 720P @ 10 fps VBR 1 000 kbps (현재 비활성) |
| 광학 줌(`ele_zoom`) 능력 | 사양서 명시 | **없음** — 본 펌웨어 capability에 부재 |
| 변배 추적(`zoom_track`) | 사양서 명시 | **없음** |
| PTZ 줌(`ptz_zoom`) | — | **있음** — `/ptz_ctrl/zoom`으로 제어 가능 |
| AF(`af_setting`, `af_coordinate`) | 일부만 명시 | **둘 다 있음** |
| 디지털 줌(`dzoomsetting`) | — | **있음** |
| PTZ 방향 | — | `ptz_4_direction`만 존재(2/8방향 미지원) |
| 한국어(`ko-ko`) | 사양서 미명시 | **있음** |
| ONVIF Discovery (3702/UDP) | "ONVIF 지원" 명시 | **포트 closed** — 본 펌웨어에서 비활성. ONVIF 사용 불가 |
| HTTPS (443/TCP) | `with_https` 능력 명시 | **포트 closed**, capability에도 없음 — 본 펌웨어는 HTTP만 |
| RTMP push (1935/TCP) | `rtmp` 능력 명시 | 능력은 있으나 **포트는 closed** — push 대상이 별도 설정되어야 동작하는 듯 |
| HTTP-alt (8000/TCP) | — | **open** (응답 없음) — RTMP/H5 라이브뷰 채널 가능성, 미확정 |

### 줌 동작에 대한 실측 해석

`ptz_zoom`은 존재하지만 `ele_zoom`(이중 렌즈 전동 줌)이 없으므로, 본 8 MP 모듈은 사양서가 가정한 "줌 렌즈 + 줌 제어 보드 + 줌 펌웨어 3종 결합"과는 다른 구현(단일 가변초점 렌즈 + 단일 모터 또는 디지털 줌 + AF) 가능성이 큽니다. **실제 화각 변화가 광학(렌즈 이동)인지 디지털(크롭)인지는 `/ptz_ctrl/zoom direction=in&autostop=1000` 호출 후 RTSP 영상으로 직접 관찰해야 확정**됩니다. 검증 절차는 `docs/05-bringup-test.md` §6.5 참고.

### 활용 권장 사항 (실측 기반)

1. **줌·PTZ 제어는 HAPI `/ptz_ctrl/*` 사용** — ONVIF가 비활성이므로 표준 ONVIF PTZ는 사용 불가
2. **라이브 스트리밍은 RTSP 직접 사용** — `rtsp://192.168.8.213:554/stream0`(4K HEVC) 또는 `/stream1`(720×480). 디바이스가 알려준 URL을 그대로 사용
3. **NETSDK는 통합 호스트(우분투) 측 클라이언트로만 가능** — 카메라 펌웨어(armv7l)에는 aarch64 SDK를 직접 올릴 수 없음
4. **이벤트 push 사용 시 `/Event/subscription/regist`** — POST 방식, 클라이언트 측 TCP listener 필요
