# Optical Zoom IP 카메라 자료 분석

이 디렉터리는 광학 줌이 가능한 IP 카메라(모델 `WGWK-AS500J`)에 대한 통합/평가용 외부 벤더 자료를 정리한 문서 모음입니다. 소스 코드 레포지토리가 아니라, 벤더 제공 사양서 / HTTP API 문서 / Linux aarch64 NETSDK 패키지를 한국어로 재정리한 결과물입니다.

## 디렉터리 레이아웃

```
optical_zoom/
├── docs/                        ← 본 분석 문서(한국어)
│   ├── README.md                ← 이 파일
│   ├── 01-hardware-spec.md      ← 카메라 하드웨어 사양
│   ├── 02-http-api.md           ← HTTP API(HAPI) 정리
│   ├── 03-netsdk.md             ← NETSDK(C/C++) 정리
│   └── 04-zoom-control-guide.md ← 광학 줌 제어 통합 가이드
└── ref/                         ← 원본 벤더 자료
    ├── http_api.pdf             ← HAPI 사양서 PDF(VER 1.5, 2024-03-18)
    ├── http_api_text.txt        ← 위 PDF 텍스트 추출본(134 KB)
    ├── simple_spec.pdf          ← 카메라 하드웨어 사양서
    ├── NETSDK_LINUX_aarch64_V2.1_2023-07-25.7z
    └── NETSDK_LINUX_aarch64_V2.1_2023-07-25/   ← 압축 해제본
        ├── demo/                ← C++ 데모(`main.cpp`, `Makefile`, 사전 빌드 `demo_test`)
        ├── include/             ← SDK 헤더(`NetSDKDLL.h` 등)
        ├── lib/aarch64/         ← 정적/동적 라이브러리
        └── LINUX NETSDK说明文档.pdf  ← SDK 설명서(중문)
```

## 핵심 사실 요약

| 항목 | 값 |
|---|---|
| 카메라 모델 | `WGWK-AS500J` |
| 메인 칩셋 | SigmaStar `SSC377D` |
| 이미지 센서 | Sony `IMX335`, 5 MP, 1/2.8" CMOS |
| 최대 해상도 | 3840×2160 @ 20 fps (메인) / D1·VGA·640×360 (서브) |
| 코덱 | H.265+ / H.265 / H.264 |
| 광학 줌 | **전동 줌(electric zoom) + 자동 초점(AF) 인터페이스 지원** — 별도의 zoom 렌즈·zoom 제어 보드·zoom 펌웨어 필요 |
| 네트워크 | RJ45 10/100M, HTTP/RTSP/DHCP/NTP/ONVIF |
| 전원 | DC 12 V, 130 mA |
| 동작 온도 | -40 ~ +65 °C |

## 제어 경로

이 카메라는 두 가지 통합 경로를 제공합니다.

1. **HTTP API (HAPI)** — REST 호출. 가장 단순한 통합 경로.
   - 진입점: `http://<카메라IP>/HAPI/V1.0/...`
   - 광학 줌: `PUT/GET /HAPI/V1.0/ptz_ctrl/zoom?direction=in|out&autostop=<ms>`
   - 자세한 내용: [`02-http-api.md`](02-http-api.md)
2. **NETSDK (C/C++)** — `libNetSDK_no_live555.so`(aarch64) 링크 후 `IP_NET_DVR_PTZControl()` / `IP_NET_DVR_PTZControlEx()` 호출. 라이브 스트림 콜백·이벤트 콜백 포함.
   - 자세한 내용: [`03-netsdk.md`](03-netsdk.md)

두 경로의 비교 및 줌 제어 통합 가이드는 [`04-zoom-control-guide.md`](04-zoom-control-guide.md) 참고.

## 원본 자료 출처 및 신뢰도

- `ref/http_api.pdf` — 벤더 제공 공식 사양서 VER 1.5 (2024-03-18). 저자: 李光明.
- `ref/simple_spec.pdf` — 벤더 제공 카메라 사양서(영문/일부 일본식 전각 문자 혼용).
- `ref/NETSDK_LINUX_aarch64_V2.1_2023-07-25` — 벤더 제공 SDK 패키지(2023-07-25 빌드). 헤더는 ISO-8859-1로 저장된 GBK 중문 주석을 포함.

모든 분석 내용은 위 원본 파일에서 직접 인용·검증된 내용이며, 추정이 포함된 부분은 별도 표기했습니다.
