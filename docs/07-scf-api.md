# 07. SCF API — 비공식 SOAP 채널 (MC800S5)

이 문서는 카메라 웹 UI(`http://192.168.8.213/`)가 사용하는 **비공식 SCF(Service Configuration Framework) API** 를 정리한 것입니다. HAPI와는 별개 채널이며, HAPI에서 노출되지 않는 **모든 고급 이미지 설정 및 실시간 줌 배율 read** 를 제공합니다.

## 1. 발견 경위

- `docs/06-live-probe-result.md`에서 확인한 대로 HAPI에는 줌 배율 read, WDR, 셔터 모드 등 고급 기능이 노출되지 않음
- 크롬 웹 UI가 어떤 채널을 쓰는지 확인하기 위해 HAR(`192.168.8.213.har`, 11 MB, 82 entries) 캡처를 분석
- 카메라가 **HAPI와는 별개의 HTTP+SOAP 엔드포인트**를 노출함을 확인 (이하 본 문서에서는 **SCF**라 칭함 — 클라이언트 측 식별자 `scfLogin`에서 유래)
- 검증 일자: 2026-05-12, 캡처된 인증 토큰을 우분투 환경에서 그대로 재사용해 동작 확인

## 2. 채널 구조

| 항목 | 값 |
|---|---|
| 트랜스포트 | HTTP/1.1 POST |
| 포트 | 80 (HAPI와 동일) |
| **Content-Type** | **`application/x-www-form-urlencoded`** ← 핵심. `text/xml`이면 표준 ONVIF/gSOAP 처리기로 분기되어 `wsa:ActionNotSupported` 오류 발생 |
| Accept | `text/javascript, text/html, application/xml, text/xml, */*` |
| X-Requested-With | `XMLHttpRequest` (브라우저 AJAX 표시) |
| 응답 Server | `gSOAP/2.8` |
| 응답 Content-Type | `text/plain; charset=utf-8` (XML 내용이지만 plain) |
| CORS | `Access-Control-Allow-Origin: *` |
| 바디 형식 | SOAP 1.2 Envelope (`http://www.w3.org/2001/12/soap-envelope`) |
| 응답 (성공) | HTTP 202 (PTZ 명령) 또는 200 + XML 본문 (get 류) |

### SOAP Envelope 템플릿

```xml
<?xml version="1.0"?>
<soap:Envelope xmlns:soap="http://www.w3.org/2001/12/soap-envelope">
  <soap:Header>
    <userid>{userid_des_hex}</userid>
    <passwd>{passwd_des_hex}</passwd>
  </soap:Header>
  <soap:Body>
    {payload}
  </soap:Body>
</soap:Envelope>
```

## 3. 인증 토큰

| 필드 | 형식 | 예시(캡처값) |
|---|---|---|
| `userid` | 16자리 hex (= 8 byte DES 블록) | `52851dbd7918bbae` |
| `passwd` | 16자리 hex (= 8 byte DES 블록) | `a17faccd02661e4c` |

### 발급 메커니즘 (현재 미확정)

- 페이지 JS(`/jsCore/m.js`)의 minified 코드 안에 `g_des_userid` / `g_des_passwd` 변수가 있고, `jsCore/des.js`가 DES 라이브러리로 로드됨
- 로그인 엔드포인트 식별자: `scfLogin` — ActiveX 플러그인 `IPCConfigCtrl`의 attribute로 설정됨 (Linux 크롬에서는 동작 미상)
- **실용적 해결책 (현 시점)**:
  1. 크롬 DevTools의 Network 탭으로 한 번 HAR 캡처
  2. `userid`/`passwd` 16자리 hex 추출
  3. 환경변수 또는 설정 파일로 보관
- **검증된 사실**: 한 번 발급된 토큰은 **장수명**(시간이 지나도 그대로 통함). 영구성은 미확정 (재부팅 시 유효 여부는 별도 검증 필요)

### 향후 자동화 후보

- `jsCore/m.js`(88 KB)의 정밀 분석으로 DES 키와 로그인 호출 형식 추출
- 또는 NETSDK의 `IP_NET_DVR_Login_Encrypt()`가 같은 DES 인증을 사용할 가능성 (다만 SDK는 aarch64 전용)
- 펌웨어 라벨 `MC800S5_AF_V0-A-RTMP-H5`에서 `RTMP-H5`는 SCF 사용 단서

## 4. 엔드포인트 카탈로그

HAR에서 확인된 7개 호출.

### 4.1 `POST /getPtzConfig` — PTZ 설정 + **실시간 줌 배율**

- **요청 바디**: 빈 `<soap:Body></soap:Body>` (헤더만으로 인증)
- **응답 (발췌)**:

```xml
<PTZConfig Protocol="PELCO_D" ComPort="1" BaudRate="2400" DataBits="8" StopBits="10"
           Verify="NONE" FlowControl="NONE" BootAction="0"
           autoHome="1" autoCalibration="1" lowPowerControl="0">
  <AfConfig enable="1" type="0" bSendOnStart="1" bSendCoordinate="1" />
  <DzoomConfig multiple_max="10.0" multiple_set="1.9" />
  <ScanConfig CruiseSpeed="0" CruiseTime="0" LineScanTime="0" />
  <AdvanceConfig>
    <FunctionConfig FunctionName="ScanBegin" PresetNumber="92" Function="Set" .../>
    <FunctionConfig FunctionName="ScanOn"    PresetNumber="99" Function="Call" ReserveValue="50" .../>
    <FunctionConfig FunctionName="Orbit"     PresetNumber="98" Function="Call" ReserveValue="10" .../>
    <FunctionConfig FunctionName="PtzRestore" .../>
    <FunctionConfig FunctionName="FocusRestore" .../>
    <FunctionConfig FunctionName="GuardPos" .../>
    <FunctionConfig FunctionName="PtzReboot" .../>
  </AdvanceConfig>
</PTZConfig>
```

| 필드 | 의미 | 비고 |
|---|---|---|
| `DzoomConfig multiple_max` | 최대 줌 배율 | **10.0배** (확정) |
| `DzoomConfig multiple_set` | **현재 줌 배율** | 실시간 read 가능 (예: 1.9배) |
| `AfConfig enable` | AF 활성 여부 | 1=on, 0=off |
| `AfConfig type` | AF 타입 | 0=기본 (해석 미상) |
| `AfConfig bSendCoordinate` | AF 좌표 전송 | 영상 분석 기반 AF 추정 |
| `Protocol PELCO_D` | PTZ 시리얼 프로토콜 | PELCO-D (보안 카메라 표준) |
| `BaudRate 2400` | PTZ 통신 속도 | 2400 bps |
| `autoHome`, `autoCalibration` | 자동 귀환 / 자동 캘리브레이션 | 활성 |
| `AdvanceConfig` | 고급 기능 ↔ 프리셋 번호 매핑 | ScanBegin→92, ScanEnd→93, ScanOn→99, Orbit→98, PtzRestore→82, FocusRestore→84, GuardPos→79, PtzReboot→94 |

### 4.2 `POST /setPTZCmd` — PTZ 명령 (fire-and-forget)

- **요청 바디**: `<xml><cmd>{token}</cmd></xml>`
- **응답**: HTTP 202, 빈 바디 (성공/실패 확인 불가 — 후속 `getPtzConfig`로 검증)

#### 확인된 cmd 토큰

| cmd | 동작 | 비고 |
|---|---|---|
| `zoomtele` | 줌 in (망원) | `tele`=telephoto |
| `zoomwide` | 줌 out (광각) | `wide`=wide-angle |
| `FocusNearAutoOff` | 포커스 near (수동) | `AutoOff`=명령 후 AF 자동 모드 끔 |
| `FocusFarAutoOff` | 포커스 far (수동) | 동일 |
| `IrisOpenAutoOff` | 광권 open | 본 모듈은 실제 동작 가능성 낮음(`ptz_iris` capability) |
| `IrisCloseAutoOff` | 광권 close | 동일 |
| `stop` | 모든 PTZ 정지 | **줌·포커스 명령은 fire-and-forget이므로 반드시 stop 호출 필요** |

#### 추정 추가 cmd (미검증)

- 회전: `up`, `down`, `left`, `right`, `up_left`, `up_right`, `down_left`, `down_right` (HAPI move와 동일 형식 추정)
- 프리셋: `preset_set_N`, `preset_call_N` (별도 SCF 엔드포인트일 가능성 더 큼)

### 4.3 `POST /getMediaVideoConfig` — 모든 이미지·인코딩·OSD 설정 read

- **요청 바디**: 빈 `<soap:Body></soap:Body>`
- **응답 크기**: ~12 KB (전체 미디어 설정 + 코덱 매트릭스)
- **응답 구조**: `<Video><Capture .../><Encode>...</Encode><JpegConfig .../><Overlay>...</Overlay><Mask>...</Mask><ROI .../><UserOverlay>...</UserOverlay><YUV .../><CodeList .../></Video>`

`<Capture>` 속성 카탈로그 (사용자가 크롬 설정 페이지에서 본 모든 항목):

| 속성 | 값 범위 | 의미 |
|---|---|---|
| `Brightness` | 0~255 (128 기본) | 밝기 |
| `Contrast` | 0~255 | 명암 |
| `Saturation` | 0~255 | 채도 |
| `Sharpness` | 0~255 | 선명도 |
| `TVSystem` | 0/1 | 0=NTSC, 1=PAL (영상 표준) |
| `forct_antiflicker` | 0/1/2 | **전원 주파수** (안티플리커 강제) — 0=auto, 1=50Hz, 2=60Hz 추정 |
| `cropxpix`, `cropypix` | int | 비디오 크롭 픽셀 |
| `HFlip`, `VFlip` | 0/1 | **좌우 / 상하 반전** |
| `rotate` | 0/90/180/270 | 화면 회전 |
| `WB_RGB` | int (RGB 패킹) | 화이트밸런스 (8421504 = 0x808080 회색 = auto) |
| `BackLight` | 0/1 | **LC (역광 보정, Light Compensation)** |
| `HLC` | 0/1 | **HLC (Highlight Compensation, 강한 빛 억제)** |
| `TNF` | 0~255 | **3D DNR (Temporal Noise Filter)** |
| `SNF` | 0~255 | **2D DNR (Spatial Noise Filter)** |
| `IrcutMode` | 0~ | IRCUT 모드 (auto/timing/manual/external) |
| `IrcutSensitivity` | 0~100 | IRCUT 광감 민감도 |
| `IrcutOpenLedDelay` | sec | IR LED ON 후 IRCUT 동작 지연 |
| `led_brightness_mode` | 0/1/2 | LED 밝기 모드 |
| `led_brightness_value` | 0~100 | LED 밝기 |
| `led_brightness_alarm` | 0~ | 경보 시 LED 밝기 |
| `IrcutNightStartTime`, `IrcutNightEndTime` | `HH:MM:SS` | 야간 모드 시간대 |
| `IrcutKeepColor` | 0/1 | 야간에도 컬러 유지 |
| `led_mode` | 0/1/2 | 0=IR only, 1=auto, 2=white only (등) |
| `ispadvmode` | 0/1 | ISP 고급 모드 |
| `bManualGain` | 0/1 | **수동 게인 사용 여부** |
| `gainValue` | 0~ | **게인 값** (bManualGain=1일 때) |
| `WDRMode` | 0/1/... | **WDR 모드** (0=off, 1=on, 2+ 추정) |
| `WDRValue` | 0~255 | **WDR 강도** |
| `WDRStartTime`, `WDREndTime` | `HH:MM:SS` | WDR 적용 시간대 |
| `DfrogFlag` | 0/1 | **Defog (안개 제거)** |
| `DfrogValue` | 0~255 | Defog 강도 |
| `shutter_mode` | 0/1/... | **주간 셔터 모드** |
| `shutter_mode_night` | 0/1/... | **야간 셔터 모드** |
| `shutter_speed_day` | μs | 주간 셔터 속도 (1000 = 1/1000s) |
| `shutter_speed_night` | μs | 야간 셔터 속도 |
| `isp_mode_color`, `isp_mode_night` | 0/1 | ISP 컬러/야간 모드 |
| `videoEncodeMode` | 0/1 | 비디오 인코딩 모드 (성능 우선/품질 우선) |
| `aov_mode`, `aov_fps` | int | AoV(Always-on-Video) 모드 |
| `light_off_sensitivity` | 0~100 | 보광등 off 민감도 |
| `face_exposure_sensitivity` | 0~100 | 얼굴 노출 민감도 |

> **결론**: 사용자가 크롬에서 설정한 **모든 항목** (밝기, 명암, 채도, 선명도, LC, HLC, 2D DNR, 전원 주파수, 좌우 반전, WDR mode, 주·야 셔터 모드)이 모두 `Capture` 한 곳에 매핑되어 있음.

### 4.4 `POST /setMediaVideoCaptureConfig` — 이미지 설정 변경

- **요청 바디**: `<Video><Capture {모든 속성}>...</Capture></Video>` — **전체 페이로드 PUT 방식** (변경할 속성만이 아니라 전체 Capture를 보내야 함)
- **응답**: HTTP 200, 빈 바디

#### 권장 호출 패턴

```
1. /getMediaVideoConfig 로 현재 Capture 전체 read
2. 변경할 속성만 in-memory에서 수정
3. /setMediaVideoCaptureConfig 로 전체 Capture 다시 PUT
4. (선택) /getMediaVideoConfig 로 적용 확인
```

#### 페이로드 예시 (Brightness 128 → 124, FishEyeCfg 포함)

```xml
<soap:Body>
  <Video>
    <Capture Brightness="124" Contrast="128" Saturation="128" Sharpness="128"
             TVSystem="0" forct_antiflicker="0" cropxpix="0" cropypix="0"
             HFlip="0" VFlip="0" rotate="0" WB_RGB="8421504" BackLight="0" HLC="0"
             TNF="128" SNF="128" IrcutMode="0" IrcutSensitivity="50"
             IrcutOpenLedDelay="5" led_brightness_mode="2" led_brightness_value="100"
             led_brightness_alarm="0" IrcutNightStartTime="18:00:00"
             IrcutNightEndTime="08:00:00" IrcutKeepColor="0" led_mode="1"
             ispadvmode="0" bManualGain="0" gainValue="0" WDRMode="0" WDRValue="128"
             DfrogFlag="0" DfrogValue="128" WDRStartTime="00:00:00" WDREndTime="00:00:00"
             shutter_mode="0" shutter_mode_night="0" shutter_speed_day="1000"
             shutter_speed_night="1000" isp_mode_color="0" isp_mode_night="0"
             videoEncodeMode="0" aov_mode="2" aov_fps="1" light_off_sensitivity="60"
             face_exposure_sensitivity="60">
      <FishEyeCfg Enable="0" autocrop="0" diameter_ppm="0"
                  center_ppm_x="0" center_ppm_y="0"/>
    </Capture>
  </Video>
</soap:Body>
```

### 4.5 `POST /getPresetList` — 프리셋 목록

```xml
<PTZ>
  <PresetList><p>1</p></PresetList>
  <BackList></BackList>
  <LineList></LineList>
  <PatrolList></PatrolList>
</PTZ>
```

### 4.6 `POST /getTimeConfig` — 시간 설정 (분석 미완)

### 4.7 `ws://192.168.8.213:12351/` — WebSocket 라이브 비디오 (H5 플레이어 채널)

- HAR에서 3건 캡처됨 (HTTP Upgrade 후 WebSocket)
- 본 문서 범위 밖 — RTSP(`rtsp://...:554/stream0`)가 동일 데이터를 더 표준적인 방법으로 제공하므로 통합에는 RTSP 권장

## 5. HAPI vs SCF 비교

| 능력 | HAPI (HTTP GET, JSON) | SCF (POST SOAP, XML) |
|---|---|---|
| 인증 | username/MD5password 또는 Session ID (60초 만료) | DES 16-hex userid/passwd (장수명) |
| 줌 명령 | `/ptz_ctrl/zoom?direction=in&autostop=ms` | `/setPTZCmd cmd=zoomtele` + 별도 `stop` |
| **줌 배율 read** | ❌ 미노출 | ✅ `multiple_set` |
| **최대 배율** | ❌ | ✅ `multiple_max=10.0` |
| **AF 상태 read** | ❌ | ✅ `AfConfig enable` |
| 포커스 제어 | `/ptz_ctrl/focus near\|far` | `FocusNearAutoOff`/`FocusFarAutoOff` |
| **포커스 lock 신호** | ❌ | ❌ (둘 다 없음 — OpenCV 우회 필요) |
| 밝기·대비·채도·샤프니스 | `/system/image/get,set` | `Capture Brightness="..."` 등 |
| **WDR / 셔터 / DNR / HLC / 게인 / WB** | ❌ 미노출 | ✅ Capture 속성으로 모두 가능 |
| 스냅샷 | `/snapshot.cgi` (720×480 JPEG) | 미발견 (RTSP 1프레임 추출 우회) |
| 프리셋 | `/ptz_ctrl/preset method=set/call/delete&presetno=N` | `/getPresetList` (read만 확인) |
| 응답 코덱 | JSON | XML attribute-only |
| 실패 모드 | `ResponseCode!=0` + 메시지 | HTTP 500 + SOAP Fault (gSOAP) |

> **결론**: HAPI와 SCF는 **상호 보완적**. 줌·포커스 기본 제어는 HAPI가 더 깔끔(autostop 시간 지정 가능)하지만, **줌 배율 read와 고급 이미지 설정은 SCF만 가능**. 통합 클라이언트는 두 채널을 함께 사용.

## 6. 제한 사항

| 제한 | 영향 | 우회 |
|---|---|---|
| 토큰 발급 자동화 X | 초기 1회 HAR 캡처로 토큰 추출 필요 | 재부팅·펌웨어 업데이트 후 재캡처 |
| 절대 줌값 직접 설정 X | "2.5x로 가라" 같은 명령 X | `multiple_set` 폴링 + `zoomtele`/`zoomwide` 반복으로 폐루프 구현 |
| 포커스 lock 신호 X | AF 수렴 시점 미상 | RTSP 프레임에서 라플라시안 분산으로 추정 |
| `setPTZCmd` fire-and-forget | 명령 성공/실패 확인 어려움 | `getPtzConfig`로 후속 검증 |
| `setMediaVideoCaptureConfig` 전체 PUT | 부분 업데이트 시 다른 필드 보존 못 함 | 호출 직전 항상 GET → 수정 → PUT 패턴 |
| 응답 일부 빈 바디 | 디버깅 단서 부족 | HTTP 상태 코드(202/200/500)로 1차 판단 |
| WebSocket :12351 미분석 | 라이브뷰 채널 활용 불가 | RTSP 메인/서브 스트림 사용 (동일 데이터) |

## 7. 사용 예시 — curl 한 줄

```bash
# 변수
CAM=192.168.8.213
USERID=52851dbd7918bbae   # HAR에서 추출
PASSWD=a17faccd02661e4c
HDR='Content-Type: application/x-www-form-urlencoded'
SOAP="<?xml version=\"1.0\"?><soap:Envelope xmlns:soap=\"http://www.w3.org/2001/12/soap-envelope\"><soap:Header><userid>${USERID}</userid><passwd>${PASSWD}</passwd></soap:Header>"

# 줌 배율 read
curl -s -X POST "http://$CAM/getPtzConfig" -H "$HDR" \
  -d "${SOAP}<soap:Body></soap:Body></soap:Envelope>" | grep -oE 'multiple_set="[^"]*"'

# 줌 in 0.5초
curl -s -X POST "http://$CAM/setPTZCmd" -H "$HDR" \
  -d "${SOAP}<soap:Body><xml><cmd>zoomtele</cmd></xml></soap:Body></soap:Envelope>"
sleep 0.5
curl -s -X POST "http://$CAM/setPTZCmd" -H "$HDR" \
  -d "${SOAP}<soap:Body><xml><cmd>stop</cmd></xml></soap:Body></soap:Envelope>"

# 이미지 설정 read
curl -s -X POST "http://$CAM/getMediaVideoConfig" -H "$HDR" \
  -d "${SOAP}<soap:Body></soap:Body></soap:Envelope>" \
  | grep -oE '<Capture[^>]*>'
```

## 8. 다음 작업

이 문서로 SCF 채널의 정적 명세는 확정. 후속 작업:

1. **`tools/zoom_client.py`에 SCFClient 통합** — Python 라이브러리 + CLI에 SCF 채널 추가 (`get-zoom`, `set-image`, `wdr`, `shutter` 등 서브커맨드)
2. **줌 절대값 폐루프 PoC** — `goto_zoom(2.5)` 같은 함수로 목표 배율 자동 도달
3. **이미지 설정 변경 PoC** — `set_image(brightness=200, wdr_mode=1)` 등 dataclass 기반 partial-update 추상화
4. **토큰 자동 발급 PoC** — `jsCore/m.js` 정밀 분석 (별도 큰 작업)
5. **AF 동작 검증** — `bSendCoordinate`/`bSendOnStart`이 실제 어떤 행동을 트리거하는지 (`setMediaVideoCaptureConfig`로 변경 시도)
