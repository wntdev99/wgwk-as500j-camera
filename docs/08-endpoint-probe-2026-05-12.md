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
