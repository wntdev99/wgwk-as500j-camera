# 08. SDK 매핑 endpoint 실측 probe 결과 (2026-05-12)

> **목적**: NETSDK가 노출하는 기능 중 `wgwk_camera` 라이브러리에 미반영된 항목에 대응되는 HAPI/SCF endpoint가 실제 펌웨어(V3.4.5.2)에 존재하는지 확인.
> **대상**: 192.168.8.101 (MC800S5_AF_V0-A-RTMP-H5 V3.4.5.2 build 2025-11-12)
> **수행 일자**: 2026-05-12

## 8.1 조사 목표

[`docs/03-netsdk.md §3.4.1`](03-netsdk.md) 분석에서 NETSDK가 제공하지만 본 라이브러리가 미커버하는 다음 3개 API의 HAPI/SCF 동등 endpoint 확인:

1. **`CMD_GET_ZOOM_CFG`** (SYSTEM_MANAGE_BASE+126) — 실시간 줌 배율(setpoint vs motor position 구분)
2. **`CMD_GET_PTZ_STATUS`** (SYSTEM_MANAGE_BASE+145) — PTZ 상태 XML(줌 동작 여부, 포커스 위치 등)
3. **`IP_NET_DVR_GET_MediaCapability`** (CMD_GET_MEDIA_CAPABILITY = SYSTEM_MANAGE_BASE+31) — 해상도·비트레이트·프레임레이트 범위

## 8.2 결과 요약

| SDK 기능 | HAPI endpoint | SCF endpoint | 결과 |
|---|---|---|---|
| `GET_MediaCapability` | `/system/video/capability` ✅ | (없음) | **완벽 매핑** — `RESOLUTION_ENTRY` 구조와 1:1 |
| `GET_AudioCapability` | `/system/audio/capability` ✅ | (없음) | 보너스 — `AUDIO_CODEC_ENTRY`와 매핑 |
| `GET_ZOOM_CFG` (motor position) | **부재** | **부재**(`DzoomConfig.multiple_set`은 setpoint만) | **노출 안 됨** |
| `GET_PTZ_STATUS` | **부재** | **부재** | **노출 안 됨** |
| `CMD_ZOOM_MULTIPLE_NOTIFY` 푸시 | `/Event/subscription/regist` ✅ | (없음) | 후속 probe 필요 |

## 8.3 검증 방법

### 펌웨어가 노출하는 HAPI 표면 전체 (61개 API)

`/HAPI/V1.0/sysinfo/functionlist` 응답 (login 후 호출):

```python
from wgwk_camera.control import ControlClient
c = ControlClient(host='192.168.8.101'); c.login()
for api in sorted(c.function_list()):
    print(api)
```

```
/Event/subscription/{regist, refresh, delete}
/Smart/{audiofiles, facedetect, flameflumes, lpr, motiondetect, objectdetect,
        regionai, videocover, videogate}/{get, set}
/Smart/{capability, linkage/capability, objectdetect/capability}
/io/{input/get, output/{get, set}}
/ptz_ctrl/{advfunction/{exec, get}, focus, iris, move, preset, stop, zoom}
/sysinfo/{capability, device_info, functionlist, rtspurl}
/sysman/{factory, reboot}
/system/audio/{capability, get, set}
/system/image/{get, set}
/system/light/{ctrlmode/capability, workmode/capability, get, set}
/system/osd/{get, set}
/system/userosd/{get, set}
/system/video/{capability, get, set}
/systime/{gettime, settime, setntp}
/uid/{getuid, keep_alive}
```

### PTZ status / zoom motor position endpoint 후보 탐색

다음 15개 후보를 HAPI에서 GET 시도. 모두 `code=-1 msg=api not found`:

```
/system/ptz/status         /ptz_ctrl/status          /ptz_ctrl/zoom/status
/ptz_ctrl/zoom/cfg         /ptz_ctrl/zoom/get        /system/ptz/zoom_cfg
/system/ptz/zoom/cfg       /system/ptz/zoom          /system/ptz/get
/ptz_ctrl/get              /ptz_ctrl/preset/list     /ptz_ctrl/preset/get
/system/ptz/preset/get     /system/ptz/capability    /ptz_ctrl/capability
```

**결론**: HAPI에는 PTZ 상태/줌-cfg endpoint가 존재하지 않음.

### SCF endpoint 후보 탐색

SCF는 HTTP 응답 코드로 endpoint 존재 여부를 변별 가능:
- **HTTP 200 + body** → 유효 GET endpoint
- **HTTP 202 + empty body** → 정의되지 않은 endpoint (또는 SET 명령 ACK)
- **HTTP 500 + SOAP fault** → ONVIF 분기 또는 형식 오류

비교 baseline (200): `/getMediaVideoConfig`(12635 bytes), `/getSystemVersionInfo`(258 bytes), `/getPtzConfig`(1543 bytes).

22개 후보 모두 **HTTP 202 + len=0**:
```
/getZoomCfg          /getZoomConfig          /getZoomState          /getDzoomConfig
/getZoomMultiple     /getPTZStatus           /getPtzStatus          /getAdvancePTZStatus
/getPTZState         /getPtzState            /getMediaCapability    /getCapability
/getPTZCapability    /getPtzCapability       /getPTZPreset          /getPresetInfo
/getSerialNumber     /getSystemTime          /getMediaConfig        /getNetworkLANConfig
/getCommConfig       /getInvalidNamehere     ← invalid 대조군도 동일
```

**확인된 SCF 유효 endpoint 전체** (`docs/07-scf-api.md` 통합):
- `/getMediaVideoConfig`, `/getPtzConfig`, `/getPresetList`, `/getSystemVersionInfo`,
- `/setMediaVideoCaptureConfig`, `/setMediaVideoEncodeConfig`, `/setPTZCmd`

**결론**: SCF에도 PTZ 상태/줌-cfg 별도 endpoint 없음. `DzoomConfig.multiple_set`이 유일한 줌 배율 노출 필드이며, **모터 위치가 아닌 ActiveX 클라이언트 설정용 setpoint**.

### `/system/video/capability` 응답 — SDK `RESOLUTION_ENTRY`와 1:1

```json
[
  {"codec_name": "H264", "res_name": "3840X2160", "stream_type": 0,
   "def_bitrate": 7000, "min_bitrate": 512, "max_bitrate": 12288,
   "def_framerate": 20, "min_framerate": 5, "max_framerate": 20, "def_config": 0},
  {"codec_name": "H264", "res_name": "1080P", "stream_type": 0,
   "def_bitrate": 3000, "min_bitrate": 512, "max_bitrate": 9216,
   "def_framerate": 25, "min_framerate": 5, "max_framerate": 60, "def_config": 0},
  {"codec_name": "H264", "res_name": "720P", "stream_type": 0,
   "def_bitrate": 2500, "min_bitrate": 512, "max_bitrate": 6144,
   "def_framerate": 25, "min_framerate": 5, "max_framerate": 60, "def_config": 0},
  ...
]
```

SDK 헤더(`media_cfg.h:88-102`):
```c
typedef struct tag_encode_resolution {
    char res_name[MAX_NAME_LEN];
    char codec_name[MAX_NAME_LEN];
    int  stream_type;
    int  def_bitrate, min_bitrate, max_bitrate;
    int  def_framerate, min_framerate, max_framerate;
    int  dual_stream, def_config;
    int  max_display_framerate;
} RESOLUTION_ENTRY;
```

→ HAPI JSON 필드명이 SDK C 구조체 필드명과 **정확히 일치**(스네이크 케이스 그대로). 펌웨어가 같은 내부 자료구조를 양쪽 채널로 직접 직렬화.

## 8.4 추가 발견 — 라이브러리에 노출 가능한 미사용 HAPI endpoint

probe 과정에서 라이브러리 미커버 endpoint를 다수 확인:

### `/system/userosd/get` — 5개 사용자 OSD (SDK `VideoUserOverlay`와 매핑)
```json
[
  {"enable": 0, "posType": 0, "posX": 0, "posY": 0,
   "fontsize": 0, "linegap": 0, "titleType": 0, "title_utf8": ""},
  ... (5 entries)
]
```

### `/system/light/get` — LED/조명 제어
```json
{
  "led_ctrl_mode": 0, "led_work_mode": 0,
  "light_open_brightness": 0, "light_off_sensitivity": 0,
  "led_brightness_mode": 0, "led_brightness_value": 0,
  "night_starttime": "00:00:00", "night_endtime": "00:00:00"
}
```
+ `/system/light/ctrlmode/capability` → `[{mode:0},{mode:1},{mode:2},{mode:3}]` (4가지 제어 모드)
+ `/system/light/workmode/capability` → `[{mode:0},{mode:1},{mode:2}]` (3가지 작업 모드)

### `/Smart/capability` — Smart 기능 능력
```json
{
  "SupportMotionDetect": 1, "SupportTargetDetect": 1,
  "SupportFaceFd": 0, "SupportFaceFr": 0, "SupportLPR": 0,
  "SupportVG": 0, "SupportRegionAI": 0,
  "SupportAudioDetect": 0, "SupportCoverDetect": 0
}
```
→ 이 카메라는 모션 검출과 객체 검출만 지원. 얼굴/번호판/AI 영역 검출 미지원.

### `/systime/gettime` — 시간/타임존 (NTP 동기화 가능)
```json
{"timeMode": "MANUAL", "timeZone": 1260, "nowtime": "2026-05-12 18:54:17"}
```

### `/Event/subscription/regist` — 이벤트 푸시 등록
```
{code: -1, msg: "Param (ServerType) not found"}
```
→ endpoint는 존재하나 `ServerType` 파라미터 필수. 후속 probe 필요.

### `/system/audio/capability` — 오디오 코덱 (SDK `AUDIO_CODEC_ENTRY`)
```json
[
  {"codec_name": "G.711U", "channels": 1, "bitspersample": 16, "samplerate": 8, "bitrate": 64, "def_config": 1},
  {"codec_name": "G.711A", "channels": 1, "bitspersample": 16, "samplerate": 8, "bitrate": 64, "def_config": 0},
  {"codec_name": "AAC",    "channels": 2, "bitspersample": 16, "samplerate": 16, "bitrate": 16, "def_config": 0}
]
```

## 8.5 결론 및 권장 후속 조치

### 적용 가능(이번 probe로 검증됨)

| 우선순위 | 기능 | endpoint | 라이브러리 메서드 후보 |
|---|---|---|---|
| ★★★ | 비디오 capability 동적 조회 | `/system/video/capability` | `Camera.video_capabilities() -> list[ResolutionEntry]` |
| ★★★ | 인코딩 프로필 검증(capability 사전 체크) | `/system/video/capability` | `EncodingProfile.validate_against(cap)` |
| ★★ | 사용자 OSD 5개 | `/system/userosd/{get,set}` | `Camera.admin.set_user_osd(idx, text, pos=..., ...)` |
| ★★ | LED/조명 제어 | `/system/light/{get,set,workmode/capability,ctrlmode/capability}` | `Camera.admin.set_light(...)` |
| ★★ | NTP 시간 동기화 | `/systime/{gettime, settime, setntp}` | `Camera.admin.sync_time(ntp_server=...)` |
| ★ | 오디오 capability | `/system/audio/capability` | `Camera.audio_capabilities()` |
| ★ | Smart 기능 능력 | `/Smart/capability` | `Camera.smart_capabilities()` |
| ★ | GPIO I/O | `/io/{input/get, output/get, output/set}` | `Camera.io.{...}` |

### 적용 불가(펌웨어가 노출하지 않음)

| 기능 | 사유 |
|---|---|
| 줌 모터 실시간 위치 | HAPI/SCF 모두 부재. `DzoomConfig.multiple_set`은 setpoint만 |
| PTZ 동작 상태 XML | endpoint 부재 |
| PTZ capability 별도 조회 | `/sysinfo/capability`와 `/sysinfo/functionlist`로 우회 가능 |

### 후속 probe가 필요한 항목

- **`/Event/subscription/regist`**: `ServerType` 파라미터의 유효값과 `CMD_ZOOM_MULTIPLE_NOTIFY`(PTZ_BASE+6) 등을 푸시 받는 구조 확인 필요. 사양서 `ref/http_api.pdf` §2.1.6(이벤트 구독 메커니즘) 참조.

## 8.A 사고 분석 — `/setMediaVideoCaptureConfig` 빈 body silent reset

본 probe 진행 중 AF endpoint 비교 baseline 호출에서 `POST /setMediaVideoCaptureConfig` 에 **빈 SOAP body** 를 전송한 결과, 펌웨어가 Capture 영역의 19개 필드를 0/기본값으로 silent reset함을 사후 확인 (2026-05-12).

### 재현 (1회 검증)

```
BEFORE: Brightness=128, Contrast=128, Saturation=128, Sharpness=128, WDRValue=128,
        TNF=128, SNF=128, WB_RGB=8421504, shutter_speed_day/night=1000,
        IrcutSensitivity=50, led_brightness_value=100, ...
  ↓ POST /setMediaVideoCaptureConfig  body=<soap:Body></soap:Body>  → HTTP 202
AFTER : Brightness=0, Contrast=0, Saturation=0, Sharpness=0, WDRValue=0,
        TNF=0, SNF=0, WB_RGB=0, shutter_speed_day/night=10,
        IrcutSensitivity=0, led_brightness_value=0, ...
```

응답은 HTTP 202(빈 본문)으로 `setMediaVideoEncodeConfig`·`setPTZCmd` 정상 호출과 구별되지 않음.

### 영향 및 복구

- 영향 범위: SCF Capture 영역 19개 필드 (모두 0 또는 시간 필드는 `00:00:00`, shutter는 10으로 클램프)
- 복구: `set_image(**baseline 값)` 한 번에 19개 필드 일괄 PUT으로 즉시 복원 — `get_image()`로 정상값 확인 완료

### 영구 대책 (`ImageClient._post` 가드)

- 패턴 `^/?set[A-Z]` (SCF SET endpoint) + `body_inner.strip() == ""` 조합을 **CameraError 로 차단**.
- 옵트인 우회: `_post(..., allow_unsafe_empty=True)`. 실제 적용 사례 없음(향후 의도적 reset 시도용).
- 동일 가드를 `tools/scf_client.SCFClient._post` 에도 적용.
- 검증: `/setMediaVideoCaptureConfig`, `/setPTZCmd`, `/setMediaVideoEncodeConfig`, `/setPtzAfConfig`, `/setPtzConfig`, `/setAfConfig` 모두 빈 body로 호출 시 차단되며, `set_image()` 등 정상 호출 흐름은 영향 없음.

> 다른 SET endpoint(예: `/setPtzConfig`, `/setPtzCommonConfig`, `/setPtzAdvanceConfig`)도 동일하게 silent reset 거동을 보일 가능성이 있으나 (Step B/C/D 미수행), 가드가 endpoint 이름 무관하게 패턴 매칭하므로 일률적으로 차단된다.

## 8.B `/Event/subscription/regist` 라이브 probe — AF lock 이벤트 부재 확인

### 사양서 명세

`ref/http_api.pdf` §3.2.1:
```
POST /HAPI/V1.0/Event/subscription/regist
Body: {
  "ServerType": 0,         // 0=IPv4, 1=domain (단순 enum)
  "ServerName": "192.168.x.x",
  "Port": <client TCP port>,
  "Duration": 30~3600,
  "PostURLPrefix": "",
  "EventType": "all" or "MotionDetect,ObjectDetect,..."
}
```

서버(카메라) → 클라이언트: `POST /HAPI/V1.0/Event/Notification` 단기 HTTP 연결로 JSON 푸시.

### 실측 (192.168.8.101, NUC8 192.168.8.102:9998 listener)

- 등록 HTTP 200, `ID=1`, `TerminationTime=+60s` ✓
- listener에 즉시 4개 NetworkDetect 이벤트 도착 (등록 직후 sync)
- 30초간 `set_af(False→True)` 토글, `zoom_in/out 800ms` 발사 → **AF/Zoom/PTZ 관련 이벤트 0건**
- 삭제 HTTP 200 정상 처리

### 푸시되는 이벤트 카탈로그 (사양서 + 본 카메라 capability)

```json
{"AlarmType": "NetworkDetect", "AlarmSubType": "NetworkDisconnected",
 "TimeStamp": ..., "OccurFlag": "true"/"false", "DeviceID": "..."}
```

본 카메라(`/Smart/capability`)가 지원:
- `MotionDetect` (SupportMotionDetect=1)
- `ObjectDetect` (SupportTargetDetect=1) — 사람/차량/오토바이/자전거
- 미지원: FaceFd, LPR, RegionAI, AudioDetect, CoverDetect, VG, Fire

**AF, PTZ, Zoom 상태 변화는 어떤 AlarmType에도 매핑되지 않음** — 사양서 표에 없고 라이브 trigger 시 푸시되지 않음.

### 결론 (AF lock 감지)

이벤트 푸시로는 불가. 대안:
1. **클라이언트 측 variance plateau 감지** — `Camera.wait_for_af_lock()` (한계는 `docs/09-library-api.md §11.A` 참고).
2. **NETSDK 8091 채널 풀 구현** — `CMD_NOTIFY_AF_*` 가능성 있으나 큰 작업.

## 8.C 포트 8091 (NETSDK Control Protocol) — Phase 1 수동 관찰

`Camera.wait_for_af_lock()`이 클라이언트 측 plateau 휴리스틱에 의존하는 근본 이유는 AF lock 푸시 채널이 HAPI / SCF / ONVIF / Event subscription 어느 쪽에도 없기 때문이다 (§8.5, §8.B). 마지막 후보가 **NETSDK 포트 8091** — `libNetSDK_no_live555.so`가 사용하는 XML_TOPSEE TCP 채널이다. 본 절은 이 채널에 직접 진입을 시도한 결과.

### Phase 1 목적

인증 없이 또는 평문 인증으로 8091에 진입해 `CMD_ZOOM_MULTIPLE_NOTIFY`(PTZ_BASE+6) / `CMD_SEND_ADVANCE_PTZ_STATUS`(1138/1139) / AF 관련 푸시가 수신되는지 확인. 가능하면 Phase 2(라이브러리 통합)로 진행, 불가능하면 추가 작업의 ROI를 평가.

### 발견 1: outbound 프레임 형식 확정

다양한 송신 형식 시도:

| 시도 | 결과 |
|---|---|
| 평문 XML | Connection reset |
| BE 4-byte length + XML | Connection reset |
| LE 4-byte length + XML | Connection reset |
| `MAGIC(58 91 58 51) + LE length + XML(GB2312)` | **200 응답 정상 수신** |
| `MAGIC + BE length + XML` | Connection reset |

**확정 — 본 채널의 송수신 프레임 형식**:
```
+--------+--------+--------+--------+
| 0x58   | 0x91   | 0x58   | 0x51   |  4-byte magic
+--------+--------+--------+--------+
|       payload length (LE u32)      |
+--------+--------+--------+--------+
|         XML payload (GB2312)       |
|        (<?xml ...?><XML_TOPSEE>)   |
+--------+--------+--------+--------+
```

### 발견 2: LOGIN 응답은 정상 수신, 인증은 거부

`Msg_type="LOGIN_MESSAGE" Msg_code="101"` 송신 → 서버는 같은 Msg_type/Msg_code로 응답하되 **`Msg_flag="-1"`** + 빈 `<MESSAGE_BODY></MESSAGE_BODY>`. 약 13초 후 서버가 socket close.

8가지 인증 변형 모두 동일한 `Msg_flag="-1"`:

| 변형 | 결과 |
|---|---|
| `UserName="admin" Password="123456"` | -1 |
| `Password=""` | -1 |
| `Password="<md5(123456)=e10adc...>"` | -1 |
| `Password="123456" Mode="0"` | -1 |
| `UserName/Password = SCF 16-hex 토큰 (52851d.../a17fac...)` | -1 |
| 소문자 `userid`/`passwd` | -1 |
| `+ ProgramType="0"` | -1 |
| `+ ClientType="0"` | -1 |

**평문/단순 해시/SCF 토큰 모두 거부됨**. SDK 헤더 `IP_NET_DVR_Login_Encrypt(..., szKeyValue)` + `IP_NET_DVR_EXCHANGE_Encrypt(lUserID)` + `CMD_ENCRYPT_EXCHANGE_KEY=150` 함수군이 시사하듯 **DES 키 교환 + 암호화 로그인 메커니즘이 필수**로 추정.

### 발견 3: 인증 없이 푸시 수신 불가

LOGIN 응답 수신 직후 30초간 listen하며 `zoom_in/out 800ms` × 2, `set_af(False/True)` 토글을 발사. 추가 프레임 0건 → server는 인증 실패 상태에서 어떤 푸시도 보내지 않는다.

(첫 probe(2025-05-12 이전)에서 받았던 `ALARM_REPORT_MESSAGE eth0 link up`은 일회성 — 네트워크 상태가 막 변경된 직후 인증 무관하게 푸시되는 NetworkDetect 알람이었던 것으로 추정. 재현 안 됨.)

### Phase 2 비용 추정

| 옵션 | 작업량 | 결과 보장 |
|---|---|---|
| B. NETSDK demo_test aarch64 cross-compile + qemu-user → 정식 로그인 패킷 캡처 분석 | 1~2일 | 패킷에 키 교환 노출되면 ✓, 아니면 C로 |
| C. `libNetSDK_no_live555.so` Ghidra/IDA disassembly로 인증·세션·CMD 디스패치 전체 reverse engineering | 수일~수주 | AF lock 푸시가 펌웨어에 실제 구현돼 있어야 의미 있음. 미보장 |

**ROI 평가**: AF lock의 정확한 신호가 운영 가치를 일주 작업으로 정당화할 만큼 critical하지 않다. `wait_for_af_lock` variance plateau가 충분하며, 사용 시 한계는 `docs/09-library-api.md §11.A`에 명시. **Phase 2는 deferred**.

### 향후 재개 조건

다음 중 하나가 성립하면 재개 가치 있음:
- 정확한 zoom motor position이 필수가 되는 운영 요구 등장
- AF lock event가 control loop의 critical path에 필요한 사용처
- aarch64 SBC(Jetson 등)로 배포 시 NETSDK 직접 링크가 자연스러운 옵션이 됨

그 외엔 본 라이브러리의 HAPI + SCF 추상화로 운영 충분.

## 8.D PTZ Preset — save/call/delete API 라이브 검증

### 목적

`Camera.preset_save() / preset_call() / preset_delete()` 가 본 카메라(MC800S5 V3.4.5.2)에서 신뢰할 수 있는 줌 위치 복귀 메커니즘인지 검증. 모터 absolute encoder 부재(§8.5 결론)가 preset 정확도에 영향을 주는지 확인.

### 절차 (4단계 검증)

1. **wide-end 기준 확보** — `zoom_out 10s` 발사 후 모터 settle, 캡처 (`0_wide_reference.jpg`).
2. **4개 위치 저장** — 1.5s `zoom_in` 후 `preset_save(N)` × 4회 (N=1,2,3,4), 매번 프레임 캡처.
3. **wide-end 재복귀** — `zoom_out 10s`.
4. **각 preset 호출 + 캡처** — wide에서 출발해 `preset_call(N)` 발사, 6s settle 후 캡처.
5. **삭제** — `preset_delete(N)` × 4회, 목록 복원 확인.

### 결과

**API 동작 — 정상 (3/3)**:
- `preset_save(N)` → preset 목록에 추가됨
- `get_preset_list()` → `[]` → `[1]` → `[1,2]` → `[1,2,3]` → `[1,2,3,4]`
- `preset_delete(N)` → 정확히 제거

**위치 복귀 — 비결정적 (1/4 정확)**:

| preset | 저장 시점 시야 | 호출 후 시야 | 평가 |
|---|---|---|---|
| #1 (1.5s zoom_in) | 적당히 zoom-in (ROBOTIS+GR-240 보임) | save_p1과 거의 동일 | **정확** ✓ |
| #2 (3.0s zoom_in) | 더 zoom-in (G3 라벨 크게) | recall_p1과 비슷, save_p2 줌 레벨 아님 | **부정확** ✗ |
| #3 (4.5s zoom_in) | 매우 zoom-in | save_p3과 다른 줌 레벨 | **부정확** ✗ |
| #4 (6.0s zoom_in, 최대) | 최대 zoom-in ("G3" 글자만 보임) | **wide_reference보다 더 광각** (ORBBEC 박스 + cable bundle 보임) | **완전 반대 방향** ✗ |

Laplacian variance (참고 — 절대 비교 부적합하나 trend 확인용):
```
preset #1: save_var=236  recall_var=221   Δ=-16
preset #2: save_var=208  recall_var=291   Δ=+83
preset #3: save_var=217  recall_var=2748  Δ=+2531   ← 차이 큼 (다른 시야)
preset #4: save_var=208  recall_var=1220  Δ=+1012   ← 차이 큼 (다른 시야)
```

캡처 파일: `/tmp/preset_4stage_2026_05_12/` (저장 vs 호출 시각 비교 자료).

### 원인 추정

본 카메라가 모터 absolute encoder를 어느 채널로도 노출하지 않는다는 사실(§8.5)과 일관:
- 펌웨어는 모터 절대 위치를 알 수 없고, preset도 정확한 좌표를 저장 못 함
- 가능 메커니즘:
  - PWM 펄스 카운트 / 시간 누적 기반 추정 (drift 누적)
  - 호출 시 hard limit에 부딪힌 상태면 추정 기준점 망가짐
  - preset이 사실 pan/tilt 전용 — 본 카메라는 PT 없으니 zoom 부분 무의미
- recall_p4 가 최대 zoom-in 저장 → 최대 wide-out으로 가는 현상은 가설 #2 또는 #3 시사

### 라이브러리 영향

- API 표면(`preset_save/call/delete`)은 HAPI `/ptz_ctrl/preset`을 정확히 노출하고 동작도 정상. **라이브러리 결함 아님**.
- 운영 한계는 펌웨어 측에 있음. `Camera.preset_call()` docstring + `docs/09-library-api.md §5 (런타임 / preset)` 에 경고 명시.

### 재현 명령
```bash
SCF_USERID=... SCF_PASSWD=... python3 ./scripts/preset_4stage_test.py
# (script: tmp 디렉토리에 단일 파일로 작성 후 실행, 이 문서 §8.D 절차)
```

## 8.E zoom_full_travel_ms 캘리브레이션 (2026-05-13)

ZoomTracker(`docs/09 §12`)의 `full_travel_ms` 파라미터 실측. 모터 saturation 시점을 메인 스트림 프레임 히스토그램 변화 분석으로 식별.

### 방법
- `anchor_wide()` (15s zoom_out으로 wide hard-limit) 후 `zoom_in(25000ms)` 한 번에 발사
- 1초 간격 ffmpeg 프레임 캡처 (총 ~25 샘플)
- 인접 프레임 16-bin 정규화 히스토그램 L1 distance 계산
- noise floor (마지막 5개 delta 평균) × 2 를 threshold로, 3 consecutive 이하 시점 = saturation
- 반대 방향(`anchor_tele()` → `zoom_out(20000ms)`)도 동일 측정

### 결과 (192.168.8.101, V3.4.5.2)

| 방향 | saturation 시점 | full_travel_ms |
|---|---|---|
| zoom_in | T+9.8s | ~9800 |
| zoom_out | T+7.7s | ~7700 |
| **평균** | — | **~8800** |

모터가 in/out 방향에 약 15% 비대칭. 단일 파라미터 모델로는 표현 못 함.

### 관찰
- T+1s 시점 이미 `KF 16X` OSD 표시 (camera 자체의 zoom multiplier 표시. 우리 `multiple_max=10.0`과 의미 다름 — KF는 별도 카운터)
- 모터가 빠르게 max 도달 후 미세 조정 — 비선형 속도 프로파일 의심
- 27s 후 정지 시점(`99_tele_end.jpg`) 시각이 motion 중 캡처(`01s.jpg`)보다 wider — 모터가 hard limit에 부딪힌 후 약간 retract하는 backlash compensation 추정

### 결정
- `ZoomTracker.full_travel_ms` 기본값 12000 → **9000**으로 갱신 (평균 8800에 약간 보수적 가산)
- docs/09 §12에 캘리브레이션 절차 코드 예시 추가
- 캡처 파일: `/tmp/zoom_calib_2026_05_13/`

## 8.F HAPI zoom 명령 단일 호출 ~5s 내부 cap (2026-05-13)

### 발견 경위

`Camera.anchor_wide(hard_limit_ms=12000)` 호출 후 영상이 여전히 zoom-in 상태. `zoom_out(12000)` 단일 명령이 전체 12s 동안 모터를 움직이지 않음을 확인.

### 검증

5s 청크 5회 반복:
```python
for _ in range(5):
    cam.zoom_out(5000)
    time.sleep(5.5)
    cam.stop()
    time.sleep(1.0)
# 결과: 작업장 전체 시야 확보 — 완벽한 wide-end 도달
```

대조군 (단일 12s):
```python
cam.zoom_out(12000)
time.sleep(13.5)
# 결과: 모터가 일부만 이동 (~5s 분량) 후 정지
```

### 결론

**HAPI 펌웨어가 단일 zoom 명령의 `autostop_ms` 파라미터를 약 5초로 내부 cap**. 12초·25초를 요청해도 실제로는 ~5s만 처리. 사양서에 명시되지 않은 펌웨어 동작.

### 라이브러리 영향

- `Camera.anchor_wide()` / `anchor_tele()` — 청크 분할 발사로 리팩터 (`_zoom_chunks()` 도입). 기본 4s 청크 + 0.4s idle.
- `Camera.calibrate_zoom_travel()` — 청크 기반 측정으로 변경. 단, AF 활동으로 인한 노이즈 때문에 saturation 자동 식별 신뢰성 낮음 (delta-based 알고리즘 한계).
- 이전 `calibrate_zoom_travel` 결과 (9000ms) **무효** — 단일 명령 cap 때문에 측정 자체가 잘못된 값이었음.
- 시각 검증으로 확정된 실제 full_travel ≈ **25000ms** (5s × 5회 청크). 기본값 25000으로 갱신.

### 청크 파라미터 (실측 기반)
| 파라미터 | 값 | 근거 |
|---|---|---|
| `_ZOOM_CHUNK_MS` | 4000 | 5s cap 안전 마진 (20%) |
| `_ZOOM_CHUNK_IDLE_MS` | 400 | 다음 명령 수락 보장 |
| 기본 `full_travel_ms` | 25000 | 5s × 5회 = wide-end 완전 도달 시각 검증 |

### 시각 자료
`/tmp/zoom_cap_check/state_0.jpg` (시작 tele) vs `state_5.jpg` (5회 청크 후 wide).

## 8.G 모터 실제 full travel = ~6.5s, 이전 25s 가정은 artifact (2026-05-13)

### 발견

사용자 제보: 카메라 OSD가 표시하는 KF 카운터의 최댓값은 **36**. 이전 측정에서 SCF `multiple_max=10.0`(광학 배율)과 별개의 KF 카운터(1~36)가 존재한다.

KF 누적 실측 (anchor_wide 후 `zoom_in(500ms)` × 12회, 각 직후 KF OSD 캡처):

| 누적 motor time | Observed KF | Δ KF/500ms |
|---|---|---|
| 0 ms | 1 (anchor) | — |
| 500 ms | 4 | +3 |
| 1000 ms | 6 | +2 |
| 2000 ms | 11 | +5 (=2.5/500ms) |
| 3000 ms | 17 | +6 |
| 4000 ms | 22 | +5 |
| 5000 ms | 28 | +6 |
| 6000 ms | 34 | +6 |

**평균 ~185ms / KF**. 사용자 가설 "500ms당 +3 KF" 거의 정확.

### 의미

Motor full range (KF 1→36 = 35 KF) = 35 × 185 ≈ **6500 ms motor time**.

이전 §8.E/§8.F 의 "25s full travel" 가정은 **chunked 명령들이 motor saturated 후에도 발사된 artifact**였음. 실제로는 ~6.5s에 motor가 saturate하고, 이후 19초+ 의 chunked 명령은 wasted no-op.

### Rapid-fire 검증

13회 × `zoom_in(500ms)` back-to-back (sleep 없음) → 8.2초 wall clock으로 KF 1→36 완전 도달 시각 확정. HAPI 호출이 각 500ms를 block하는 동안 motor가 명령의 500ms autostop을 실행 → motor 사실상 연속 동작.

### 라이브러리 변경

- **`ZoomTracker`**: 광학 배율 1~10 모델 → KF 1~36 모델. `ms_per_kf=185` 기본값.
- **`anchor_wide`/`anchor_tele`**: chunked 25s → rapid-fire 14×500ms (7.6s, 76% 단축).
- **`zoom_in(ms)`/`zoom_out(ms)`**: short ms(≤4500)는 단일 호출 그대로, long ms는 rapid-fire 분할.
- **`zoom_level`**: 1.0~36.0 KF 반환. `zoom_multiplier` property로 광학 배율(1.0x~10.0x) 환산.
- **이전 `_zoom_chunks` / `full_travel_ms` / `chunk_settle_s` 등 청크 API 폐기**.

`Camera(zoom_max_kf=36, zoom_ms_per_kf=185, zoom_max_optical_multiplier=10.0)` 생성자 인자가 신규.

### 실측 (2026-05-13, 192.168.8.101)

```
anchor_wide()  -> 7.6s, zoom_level=KF 1.0   (광학 1.00x)
anchor_tele()  -> 7.7s, zoom_level=KF 36.0  (광학 10.00x)
                         시각 OSD: "KF 36X" 확인
zoom_in(500)   x1 -> KF 1.0 → 3.7 (예상 +500/185=2.7)
zoom_in(500)   x2 -> KF 3.7 → 6.4
```

## 8.6 재현 명령

```bash
# 1. HAPI function list
python3 -c "
import sys; sys.path.insert(0, 'src')
from wgwk_camera.control import ControlClient
c = ControlClient(host='192.168.8.101'); c.login()
[print(api) for api in sorted(c.function_list())]
c.logout()"

# 2. HAPI capability
python3 -c "
import sys, json; sys.path.insert(0, 'src')
from wgwk_camera.control import ControlClient
c = ControlClient(host='192.168.8.101'); c.login()
print(json.dumps(c._get('/system/video/capability'), indent=2))
c.logout()"

# 3. SCF endpoint 존재 검증 (HTTP 200 vs 202)
python3 -c "
import requests
ENV = ('<?xml version=\"1.0\"?>'
       '<soap:Envelope xmlns:soap=\"http://www.w3.org/2001/12/soap-envelope\">'
       '<soap:Header><userid>YOUR_USERID</userid><passwd>YOUR_PASSWD</passwd></soap:Header>'
       '<soap:Body></soap:Body></soap:Envelope>')
for ep in ['/getMediaVideoConfig', '/getInvalidName', '/getPtzConfig']:
    r = requests.post(f'http://192.168.8.101{ep}', data=ENV,
        headers={'Content-Type': 'application/x-www-form-urlencoded'}, timeout=5)
    print(f'{ep:25s} HTTP {r.status_code} len={len(r.text)}')"
```
