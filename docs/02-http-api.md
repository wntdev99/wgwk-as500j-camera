# 02. HTTP API (HAPI) 정리

> 출처: `ref/http_api.pdf` — VER 1.5 (2024-03-18), 저자 李光明.
> 텍스트 추출본: `ref/http_api_text.txt`.

## 2.1 개요

- 약칭: **HAPI** (HTTP API)
- 통신: HTTP **단기 연결(short connection)** + JSON 응답
- 지원 기능:
  1. 디바이스 능력 및 지원 API 조회
  2. 시스템 제어(재부팅, 공장 초기화 등)
  3. **PTZ 제어**(회전, 프리셋, 줌, 포커스, 광권 등)
  4. 네트워크/비디오/오디오/저장/경보/스마트 분석/PTZ 설정의 GET·SET
  5. 이벤트 구독 메커니즘
  6. 경보 이벤트 업로드

## 2.2 HTTP 메서드 규칙

| 메서드 | 용도 |
|---|---|
| `GET` | 메시지 바디 없음. 모든 파라미터는 URL의 `?key=value&...`로 전달 |
| `PUT` | 바디에 JSON으로 파라미터 전달. GET을 지원하는 API는 PUT도 지원 |
| `POST` | **이벤트 구독/갱신/삭제/통지 전용**. `Content-Type: application/x-www-form-urlencoded` 지정 |

## 2.3 응답 메시지 포맷

모든 응답은 다음 구조의 JSON입니다.

```json
{
  "Response": {
    "ResponseURL": "/HAPI/V1.0/uid/getuid",
    "SessionID":  "15E25D",
    "ResponseCode": 0,
    "ResponseString": "Succeed",
    "Data": "null"
  }
}
```

| 필드 | 의미 |
|---|---|
| `ResponseURL` | 요청 URL을 그대로 반환 |
| `SessionID` | `getuid`로 발급된 세션 ID. 사용자명/비밀번호 인증 방식이면 빈 문자열 |
| `ResponseCode` | `0`이 성공 |
| `ResponseString` | `"Succeed"`이면 성공, 그 외는 오류 메시지 |
| `Data` | GET의 결과 데이터(JSON 또는 `"null"`). PUT/POST 응답에서는 `"null"` |

## 2.4 URL 규칙

```
/HAPI/V1.0[/Channels/<ID>]/<service-name>/<resource-name>[/<child>][/<ID>][?key1=value1&key2=value2]
```

- `[/Channels/<ID>]` — 다채널 장비(NVR, 멀티 카메라)용. `ID=0`은 채널 무관, `ID>=1`은 채널 번호. **단안 카메라는 생략 가능**(본 모델은 단안이므로 일반적으로 생략).

## 2.5 인증 (HAPI 1.5 §1.5)

두 가지 방식 중 하나 선택:

### 2.5.1 사용자명/비밀번호 방식

- URL 또는 바디에 `username` + `password` 동봉
- 비밀번호는 **평문 또는 32자리 MD5 해시** 모두 허용
- 사용자명/비밀번호 대소문자는 인증 결과에 영향 없음
- 예: `password=e10adc3949ba59abbe56e057f20f883e` (이는 `"123456"`의 MD5)

### 2.5.2 Session ID 방식 (권장)

1. `/HAPI/V1.0/uid/getuid?username=admin&password=<MD5>` 호출 → `SessionID` 발급
2. 이후 모든 호출은 `?uid=<SessionID>` 또는 바디에 `"uid": "..."` 전달
3. **마지막 성공 호출로부터 60초** 후 만료
4. 만료 방지: `/HAPI/V1.0/uid/keep_alive?uid=<SessionID>` 주기 호출

### 호출 예시 (사양서 §1.6 원문 인용)

```http
# 1) 평문 비밀번호로 uid 발급
GET /HAPI/V1.0/uid/getuid?username=admin&password=123456

# 2) MD5 비밀번호로 uid 발급
GET /HAPI/V1.0/uid/getuid?username=admin&password=e10adc3949ba59abbe56e057f20f883e

# 3) uid 갱신(GET)
GET /HAPI/V1.0/uid/keep_alive?uid=15E25D

# 4) uid 갱신(PUT)
PUT /HAPI/V1.0/uid/keep_alive HTTP/1.1
content-type: application/json
{ "uid": "3CFABD6" }
```

## 2.6 전체 엔드포인트 카탈로그

> `ref/http_api_text.txt`에서 `/HAPI/V1.0/` 패턴을 추출해 정리. 일부 엔드포인트는 사양서 내부에서 `smart`와 `Smart`(첫 글자 대소문자)가 혼용되어 있으므로 실기에서는 둘 다 시도 가능.

### 세션
| API | 메서드 | 설명 |
|---|---|---|
| `/uid/getuid` | GET/PUT | uid(SessionID) 발급 |
| `/uid/keep_alive` | GET/PUT | uid 60초 만료 방지 |

### 시스템 정보 / 제어
| API | 메서드 | 설명 |
|---|---|---|
| `/sysinfo/device_info` | GET/PUT | SN, device_type, model, MAC, 커널 버전, 펌웨어 버전 |
| `/sysinfo/functionlist` | GET/PUT | 디바이스가 지원하는 API 목록(JSON 배열) |
| `/sysinfo/capability` | GET/PUT | **디바이스 능력집(capability) 문자열 리스트** |
| `/sysinfo/rtspurl` | GET/PUT | 메인/서브 스트림 RTSP URL 반환 |
| `/sysman/reboot` | GET/PUT | 재부팅 |
| `/sysman/factory` | GET/PUT | 공장 초기화 |

### IO 제어
| API | 설명 |
|---|---|
| `/io/input/get` | IO 입력 상태 조회 |
| `/io/output/get` | IO 출력 상태 조회 |
| `/io/output/set` | IO 출력 상태 설정 |

### 시간
| API | 설명 |
|---|---|
| `/systime/gettime` | 시간/타임존 조회 |
| `/systime/settime` | 시간/타임존 설정 |
| `/systime/setntp` | NTP 설정 |

### **PTZ 제어 (광학 줌 핵심)**
| API | 설명 |
|---|---|
| `/ptz_ctrl/stop` | PTZ 정지 |
| `/ptz_ctrl/move` | 8방향 이동 |
| `/ptz_ctrl/preset` | 프리셋 set/call/delete |
| **`/ptz_ctrl/zoom`** | **줌 in/out** |
| `/ptz_ctrl/focus` | 포커스 near/far |
| `/ptz_ctrl/iris` | 광권 open/close |
| `/ptz_ctrl/advfunction/exec` | 고급 기능 실행 |
| `/ptz_ctrl/advfunction/get` | 고급 기능 목록 |

### 영상 캡처
| API | 설명 |
|---|---|
| `/snapshot.cgi` 또는 `/snapshot` | 수동 스냅샷 |

### 미디어 설정
| API | 설명 |
|---|---|
| `/system/image/{get,set}` | 이미지 파라미터 |
| `/system/video/{capability,get,set}` | 비디오 인코딩 |
| `/system/audio/{capability,get,set}` | 오디오 인코딩 |
| `/system/osd/{get,set}` | OSD |
| `/system/light/{ctrlmode/capability, workmode/capability, get, set}` | 조명/IRCUT |

### 스마트 분석
| API | 설명 |
|---|---|
| `/smart/capability` | 스마트 능력집 |
| `/smart/audiofiles/get` | 경고음 목록 |
| `/smart/linkage/capability` | 연동 능력 |
| `/motiondetect/{get,set}` 또는 `/smart/motiondetect/{get,set}` | 움직임 검출 |
| `/smart/objectdetect/{capability,get,set}` | 객체 검출(사람·차량·비기동차) |
| `/smart/videocover/{get,set}` | 비디오 차폐 |
| `/smart/facedetect/{get,set}` | 얼굴 검출 |
| `/smart/videogate/{get,set}` | 라인 크로스 검출 |
| `/smart/regionai/{get,set}` | 영역 침입 검출 |
| `/smart/lpr/{get,set}` | 번호판 인식 |
| `/smart/flameflumes/{get,set}` | 화염·연기 검출 |

### 이벤트(POST 전용)
| API | 설명 |
|---|---|
| `/Event/subscription/regist` | 이벤트 구독 등록 |
| `/Event/subscription/refresh` | 구독 갱신 |
| `/Event/subscription/delete` | 구독 해제 |
| `/Event/Notification` | (디바이스 → 클라이언트) 이벤트 통지 |

## 2.7 핵심 API 상세 — 광학 줌

### `/HAPI/V1.0/ptz_ctrl/zoom`

| 파라미터 | 타입 | 설명 |
|---|---|---|
| `direction` | string | `"in"`(확대) / `"out"`(축소) |
| `autostop` | int (ms) | 지정 ms 후 자동 정지(블로킹 호출). **0 또는 미지정 = 무한 동작**, 값이 **1000을 초과하면 1000ms에서 자동 정지** |
| `username` + `password` (또는 `uid`) | string | 인증 정보 |

**호출 예시**

```
# 확대(in) 500ms
GET /HAPI/V1.0/ptz_ctrl/zoom?direction=in&autostop=500
   &username=admin&password=e10adc3949ba59abbe56e057f20f883e

# 축소(out) 100ms
GET /HAPI/V1.0/ptz_ctrl/zoom?direction=out&autostop=100
   &username=admin&password=e10adc3949ba59abbe56e057f20f883e
```

**응답 예시**

```json
{
  "Response": {
    "ResponseURL": "/HAPI/V1.0/ptz_ctrl/zoom",
    "SessionID":   "",
    "ResponseCode": 0,
    "ResponseString": "Succeed",
    "Data": { "direction": "in", "autostop": 500 }
  }
}
```

### 동반 API: `/ptz_ctrl/focus`

| 파라미터 | 값 |
|---|---|
| `direction` | `"near"` / `"far"` |
| `autostop` | 위 zoom과 동일 |

### 동반 API: `/ptz_ctrl/move`

| 파라미터 | 값 |
|---|---|
| `direction` | `"left"`, `"right"`, `"up"`, `"down"`, `"left_up"`, `"right_up"`, `"left_down"`, `"right_down"` |
| `speed` | `1` ~ `10` |
| `autostop` | ms |

### 동반 API: `/ptz_ctrl/preset`

| 파라미터 | 값 |
|---|---|
| `method` | `"set"` / `"call"` / `"delete"` |
| `presetno` | `1` ~ `255` |

> **줌-프리셋 조합 패턴**: 일반적으로 광학 줌 카메라에서는 `move` + `zoom` + `focus` 조합으로 특정 화각을 잡은 뒤 `preset?method=set&presetno=N` 으로 저장하고, 이후 `method=call`로 즉시 복원합니다.

## 2.8 능력집(`capability`) 키 — 줌 관련

`/sysinfo/capability` 응답의 `caps` 문자열 중 광학 줌·PTZ 도입 시 확인해야 할 키:

| 키 | 의미 |
|---|---|
| `ptz_control` | PTZ 제어 기능 |
| `ptz_zoom` | PTZ 줌 채널 존재 |
| `zoom_track` | 변배 추적(검출 시 자동 줌인) |
| `ele_zoom` | 전동 줌(electric zoom) — 이중 렌즈 카메라 |
| `dzoomsetting` | 디지털 줌 설정 |
| `af_setting` | AF(자동 초점) 기능 |
| `af_protocol_4` | AF 칩이 고급 PTZ 제어 프로토콜 지원 |
| `positioning_3d` | 3D 포지셔닝 |
| `high_ctrl_ptz` | 고급 PTZ 제어 |
| `pt_2_direction`/`pt_4_direction`/`pt_8_direction` | PTZ 회전 방향 수 |

> 위 키들의 전체 카탈로그는 `ref/NETSDK_LINUX_aarch64_V2.1_2023-07-25/include/function_list.h`에 마크로(`FUNCTION_ELE_ZOOM`, `FUNCTION_ZOOM_TRACK`, `FUNCTION_AF_VERSION` 등)로 정의되어 있습니다. HAPI 응답의 `caps` 문자열은 이 마크로의 값(예: `"ele_zoom"`, `"zoom_track"`, `"af_setting"`)과 동일합니다.

## 2.9 이벤트 구독 흐름

```
클라이언트                    카메라(서버)
   │ TCP 9998 LISTEN
   │
   │── POST regist ────────▶│   (Duration ≤ 3600s)
   │◀── Response ID ─────────│
   │
   │             ▼ 경보 발생 시
   │◀── POST Notification ───│  (TCP 단기 연결로 클라이언트 측 포트로 push)
   │
   │── POST refresh ──────▶│   (TerminationTime 도래 전 갱신)
   │
   │── POST delete ──────▶│   (구독 해제)
```

### 구독 등록 요청 예 (`POST /Event/subscription/regist`)

```json
{
  "ServerType": 0,
  "ServerName": "192.168.1.253",
  "Port": 9998,
  "Duration": 3600,
  "PostURLPrefix": "",
  "EventType": "all"
}
```

| 필드 | 의미 |
|---|---|
| `ServerType` | `0`=IPv4, `1`=도메인 |
| `ServerName` | 클라이언트(수신측) IP/도메인 |
| `Port` | 클라이언트 수신 포트(1~65535) |
| `Duration` | 구독 주기(초), 30~3600 |
| `PostURLPrefix` | 디바이스가 push할 URL prefix |
| `EventType` | `"all"` 또는 쉼표 구분(`"MotionDetect,ObjectDetect"`) |

### 응답에서 받는 식별자

| 필드 | 의미 |
|---|---|
| `ID` | 구독 식별자(갱신·해제 시 필요) |
| `CurrentTime` | UTC epoch 초 |
| `TerminationTime` | 구독 만료 시각(UTC epoch 초) |

## 2.10 변경 이력 (사양서 §修订记录)

| 일자 | 버전 | 변경 |
|---|---|---|
| 2023-11-03 | V1.0 | 최초 공개 |
| 2023-12-05 | V1.1 | IO 상태 제어 추가 |
| 2024-01-03 | V1.2 | 보광등 밝기 모드 설정 추가 |
| 2024-01-15 | V1.3 | 이벤트 통지에 `Picture`(이미지 첨부) 옵션 및 `OccurFlag`(true=경보 발생, false=경보 종료) 속성 추가 |
| 2024-01-16 | V1.4 | 이벤트 통지에 로컬 시간 문자열 추가, 객체 검출 SET API 절 보완 |
| 2024-03-18 | V1.5 | 비디오 차폐 / 얼굴 검출 / 라인 크로스 / 영역 침입 / 화염 검출 GET·SET 추가 |

## 2.11 통합 시 권장 사항

1. **항상 Session ID 방식 사용** — URL에 평문 비밀번호가 남는 것을 방지하고, 60초 keep_alive 루프를 별도 스레드로 운영.
2. **줌 명령은 `autostop`을 짧게(50~200ms) 끊어 호출** — 정확한 줌 위치 제어를 위해 `/ptz_ctrl/stop`을 백업으로 둠.
3. **줌 동작 전 capability 검증** — `/sysinfo/capability`에서 `ele_zoom` 또는 `ptz_zoom` 문자열 존재 여부를 확인. 없으면 카메라 본체에 줌 렌즈·보드가 결합되지 않은 상태(사양서 §광학 줌 단서 참조).
4. **RTSP 스트림과 제어 채널 분리** — RTSP는 `rtsp://<IP>:554/stream0|stream1`로 별도 클라이언트(GStreamer/FFmpeg 등)에서 처리하고, HAPI는 제어 전용으로 사용.
5. **이벤트 push는 클라이언트 측 TCP listener 필요** — 카메라가 단기 연결로 push하므로 수신측은 단순 HTTP/TCP 서버를 띄워두어야 함.
