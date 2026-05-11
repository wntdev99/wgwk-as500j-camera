# 03. NETSDK (Linux aarch64) 정리

> 출처: `ref/NETSDK_LINUX_aarch64_V2.1_2023-07-25/`
> 벤더 배포 패키지명 `NETSDK_LINUX_aarch64_V2.1_2023-07-25.7z` (3.2 MB, 2023-07-25 빌드)
> SDK 설명서 원본(중문): `ref/NETSDK_LINUX_aarch64_V2.1_2023-07-25/LINUX NETSDK说明文档.pdf`

## 3.1 패키지 구성

```
NETSDK_LINUX_aarch64_V2.1_2023-07-25/
├── include/                         ← 공개 헤더
│   ├── NetSDKDLL.h                  ← 메인 API 진입(타입 + 함수 선언)
│   ├── cmd_def.h                    ← 내부 메시지 CMD 코드 정의
│   ├── data_struct.h                ← 디바이스 설정/이벤트 구조체
│   ├── media_cfg.h                  ← 미디어/스트림 설정 타입
│   ├── function_list.h              ← 능력집(capability) 마크로 카탈로그
│   ├── common_head.h                ← 공용 타입/매크로
│   └── tinyxml.h / tinystr.h        ← TinyXML 외부 의존성
├── lib/aarch64/                     ← aarch64 정적/동적 라이브러리
│   ├── libNetSDK_no_live555.a   (4.97 MB)
│   ├── libNetSDK_no_live555.so  (1.02 MB)
│   ├── libtinyxml.{a,so}            (XML 파서)
│   └── libixml.{a,so}               (UPnP iXML)
├── demo/                            ← 데모 + Makefile + 사전 빌드 바이너리
│   ├── main.cpp                     (84 KB) — 단일 파일 데모
│   ├── configlib.{h,cpp}            (설정 파싱 헬퍼)
│   ├── Mutex.{h,cpp}                (POSIX mutex 래퍼)
│   ├── Makefile / Makefile-hisiv300 / Makefile-- (플랫폼별 빌드)
│   ├── config.cfg                   (런타임 설정 텍스트)
│   ├── conf.ipc.xml                 (IPC 설정 XML 샘플)
│   ├── demo_test                    (2.8 MB, 사전 빌드된 x86_64 실행 파일)
│   ├── replay_20220507_*.h265       (H.265 재생 샘플)
│   └── readme.txt                   (중문, GBK 인코딩 깨짐)
└── LINUX NETSDK说明文档.pdf         (SDK 설명서, 1.16 MB)
```

> **인코딩 주의**: `include/*.h` 파일은 `file` 명령 기준 *ISO-8859 text, with CRLF line terminators*로 보고되지만 실제 주석은 GBK(중문)입니다. UTF-8 환경에서는 깨져 보입니다. iconv로 GBK→UTF-8 변환 후 사용 권장.

## 3.2 라이브러리 변형

| 라이브러리 | 라이브 스트림 | 비고 |
|---|---|---|
| `libNetSDK.a/so` | live555 포함 (RTSP) | 본 패키지에는 **포함되지 않음** |
| `libNetSDK_no_live555.a/so` | live555 미포함 | **본 패키지가 제공하는 유일한 변형**. RTSP 기반 라이브 프리뷰 API는 동작하지 않음(`demo/readme.txt`에 명시) |

`demo/readme.txt` 원문(번역):
> "라이브러리에 NETSDK 외에 RTSP 모듈로 `libNetSDK_no_live555.a/so`가 포함되어 있으며, 이 라이브러리를 사용할 때는 라이브 프리뷰 관련 API를 호출하면 안 됩니다."

즉 RTSP 스트리밍이 필요하면 **외부 RTSP 클라이언트(FFmpeg/GStreamer)**를 사용해 `rtsp://<IP>:554/stream0`에 별도 접속해야 합니다.

## 3.3 빌드

### Makefile 핵심 부분

```makefile
TARGET = demo_test
C_FLAGS += -Wall -g -DLINUX -DNETSDK -O0

INC_FLAGS += -I../include -I./ -Imp4Muxer

PLATFORM=x86_64               # ← 기본값. aarch64 빌드 시 수정 필요
CROSS_COMPILE=

USE_FFMPEG_SO=0
USE_LIVE555=0
LD_FLAGS += -lrt -lpthread
LD_FLAGS += ../lib/$(PLATFORM)/libNetSDK_no_live555.a
LD_FLAGS += ../lib/$(PLATFORM)/libtinyxml.a ../lib/$(PLATFORM)/libixml.a ../lib/$(PLATFORM)/libz.a

ifeq ($(PLATFORM), x86_64)
    LD_FLAGS += -liconv
endif

COMPILE.c = $(CROSS_COMPILE)g++ $(C_FLAGS) $(INC_FLAGS) -c
LINK.c = $(CROSS_COMPILE)g++
```

### aarch64 빌드 시 필요한 수정

1. `PLATFORM=aarch64` (디렉터리 `lib/aarch64/`와 일치).
2. **`lib/aarch64/`에는 `libz.a`가 없습니다.** 시스템 libz 사용으로 변경하거나 별도 공급 필요:
   ```makefile
   LD_FLAGS += ../lib/$(PLATFORM)/libtinyxml.a ../lib/$(PLATFORM)/libixml.a -lz
   ```
3. 교차 컴파일 시 `CROSS_COMPILE=aarch64-linux-gnu-` (Ubuntu) 또는 사용 중인 SBC용 툴체인 prefix.
4. `-DNETSDK` 매크로는 IPCAMERA 펌웨어 측 정의와의 구조체 분기를 위해 **반드시 유지** (readme.txt §2 안내).

### 사전 빌드 바이너리

`demo/demo_test`(2.8 MB)는 `file` 검사 시 x86_64 ELF로 추정됩니다. aarch64 보드에서는 재컴파일이 필요합니다.

## 3.4 헤더 개요

### `NetSDKDLL.h` — 메인 API

#### SDK 라이프사이클
```c
LONG IP_NET_DVR_Init();
LONG IP_NET_DVR_Cleanup();
LONG IP_NET_DVR_GetSDKBuildVersion();
LONG IP_NET_DVR_GetSDKVersion();
LONG IP_NET_DVR_SetLogToFile(DWORD bLogEnable, char *strLogDir, BOOL bAutoDel);
```

#### 콜백 등록
```c
LONG IP_NET_DVR_SetExceptionCallBack(UINT nMessage, HWND hWnd,
                                     fExceptionCallBack cb, void *pUser);
LONG IP_NET_DVR_SetAUXResponseCallBack(AUXResponseCallBack fAUXCallBack, void *pUser);
LONG IP_NET_DVR_SetStatusEventCallBack(StatusEventCallBack fStatusEventCallBack, void *pUser);
```

#### 디바이스 로그인
```c
LONG IP_NET_DVR_Login(char *sDVRIP, WORD wDVRPort,
                      char *sUserName, char *sPassword,
                      LPIP_NET_DVR_DEVICEINFO lpDeviceInfo);
LONG IP_NET_DVR_Logout(LONG lUserID);
LONG IP_NET_DVR_Login_Encrypt(char *sDVRIP, WORD wDVRPort,
                              char *sUserName, char *sPassword,
                              LPIP_NET_DVR_DEVICEINFO lpDeviceInfo,
                              const char *szKeyValue);
LONG IP_NET_DVR_SetAutoReconnect(LONG lUserID, int bAutoReconnect);
```

#### LAN 디바이스 검색
```c
LONG IP_NET_DVR_StartSearchIPC();
LONG IP_NET_DVR_StopSearchIPC();
LONG IP_NET_DVR_GetSearchIPCCount();
LONG IP_NET_DVR_GetIPCInfo(LONG index, IPC_ENTRY * pIPCInfo);
LONG IP_NET_DVR_GetIPCInfoXML(LONG index, char *pXMLInfo, int maxLen);
```

#### 라이브 프리뷰 (no_live555 빌드에서는 호출 금지)
```c
LONG IP_NET_DVR_RealPlay(...);
LONG IP_NET_DVR_RealPlayEx(...);
LONG IP_NET_DVR_StopRealPlay(LONG lRealHandle);
```

#### **PTZ 제어 (광학 줌 핵심)**
```c
LONG IP_NET_DVR_PTZControl(LONG lUser,
                           DWORD dwPTZCommand,   // ← ZOOM_IN_VALUE 등
                           DWORD nTspeed,
                           DWORD nSpeed);
LONG IP_NET_DVR_PTZPreset(LONG lUser,
                          DWORD dwPTZPresetCmd, // SET_PRESET/CLE_PRESET/GOTO_PRESET
                          DWORD dwPresetIndex);
LONG IP_NET_DVR_PTZControlEx(LONG lUser, const char *pXml);
```

##### `dwPTZCommand` enum (`PTZ_CMD_TYPE` in `NetSDKDLL.h`:214)
```c
enum PTZ_CMD_TYPE {
    LIGHT_PWRON   = 2,
    WIPER_PWRON,
    FAN_PWRON,
    HEATER_PWRON,
    AUX_PWRON1,
    AUX_PWRON2,
    ZOOM_IN_VALUE = 11,   // 줌 인
    ZOOM_OUT_VALUE,       // 줌 아웃
    FOCUS_NEAR,
    FOCUS_FAR,
    IRIS_OPEN,
    IRIS_CLOSE,
    TILT_UP,
    TILT_DOWN,
    PAN_LEFT,
    PAN_RIGHT,
    UP_LEFT,
    UP_RIGHT,
    DOWN_LEFT,
    DOWN_RIGHT,
    PAN_AUTO,
    STOPACTION
};

#define ZOOM_IN   ZOOM_IN_VALUE
#define ZOOM_OUT  ZOOM_OUT_VALUE
```

##### 프리셋 enum (`PTZ_PRESET_TYPE`)
```c
enum PTZ_PRESET_TYPE {
    SET_PRESET  = 8,
    CLE_PRESET  = 9,
    GOTO_PRESET = 39
};
```

##### `IP_NET_DVR_PTZControlEx` XML 페이로드 (데모 `main.cpp:1442` 인용)
```cpp
sprintf(xmldata,
    "<xml>\n<cmd>%s</cmd>"
    "<panspeed>%ld</panspeed>"
    "<tiltspeed>%ld</tiltspeed>"
    "</xml>",
    cmdstr, nPspeed, nTspeed);
IP_NET_DVR_PTZControlEx(lUserID, xmldata);
```

`<cmd>` 값으로는 `"zoom_in"`, `"zoom_out"`, `"focus_near"`, `"focus_far"`, `"up"`, `"down"`, `"left"`, `"right"`, `"stop"` 등 문자열 명령을 사용합니다(데모의 stdin 인터프리터에서 그대로 전달).

#### 시스템 제어
```c
LONG IP_NET_DVR_FormatDisk(LONG lUserID, LONG lDiskNumber);
LONG IP_NET_DVR_Upgrade(LONG lUserID, char *sFileName);
LONG IP_NET_DVR_UploadFile(LONG lUserID, LONG fileType, const char *filename);
LONG IP_NET_DVR_RebootDVR(LONG lUserID);
LONG IP_NET_DVR_ShutDownDVR(LONG lUserID);
LONG IP_NET_DVR_Ircut_switch_daynight(LONG lUserID, int day);
LONG IP_NET_DVR_RestoreConfig(LONG lUserID);
LONG IP_NET_DVR_GetConfigFile(LONG lUserID, char *sFileName);
LONG IP_NET_DVR_SetConfigFile(LONG lUserID, char *sFileName);
LONG IP_NET_DVR_GetDVRConfig(LONG lUserID, DWORD dwCommand, LONG lChannel,
                             LPVOID lpOutBuffer, DWORD dwOutBufferSize,
                             LPDWORD lpBytesReturned);
LONG IP_NET_DVR_SetDVRConfig(LONG lUserID, DWORD dwCommand, LONG lChannel,
                             const LPVOID pXml, DWORD dwInBufferSize);
LONG IP_NET_DVR_SystemControl(LONG lUserID, DWORD nCmdValue, LONG flag,
                              const char *pXml);
```

#### 스냅샷
```c
LONG IP_NET_DVR_SnapPic(LONG lUserID, int bsub, int quality,
                        const char *filename, int timeout);
LONG IP_NET_DVR_SnapPicTaskStart(SnapPicTask *task);
LONG IP_NET_DVR_SnapPicTaskStop();
```

#### 음성 인터컴(반이중)
```c
LONG IP_NET_DVR_StartVoiceCom(LONG lUserID, int AudioType,
                              int iSampleRate, int iChannel);
LONG IP_NET_DVR_StopVoiceCom(LONG lUserID);
LONG IP_NET_DVR_InputAudioData(LONG lUserID, const char *pBuffer, int nSize);
```

#### XML 헬퍼 (구조체 ↔ XML 변환)
```c
LONG IP_NET_DVR_GetNetworkCfgByXml(NetworkConfigNew *cfg, char *xmlBuf);
LONG IP_NET_DVR_Network_getLANCfgByXml(LANConfig *cfg, char *xmlBuf);
LONG IP_NET_DVR_Network_getWIFICfgByXml(WIFIConfig *cfg, char *xmlBuf);
LONG IP_NET_DVR_GetServerCfgByXml(ServerConfig *cfg, char *xmlBuf);
LONG IP_NET_DVR_Media_getAudioByXml(AudioConfig *cfg, char *xmlBuf);
// ...etc
```

> 헤더 주석(GBK 깨짐) 원문: *"구조체로 직접 가져오기/설정할 때는 반드시 먼저 GET으로 한 번 읽고, 필요한 항목만 수정해서 SET을 호출해야 한다. 그렇지 않으면 디바이스가 정상 동작하지 않을 수 있다."*

### `cmd_def.h` — CMD 코드 카탈로그

PTZ/줌 관련 CMD:

| 매크로 | 값 | 용도 |
|---|---|---|
| `CMD_PTZ_BASE` | 120 | PTZ 명령 베이스 |
| `CMD_PTZ_CONTROL` | 120+0 | PTZ 일반 제어 |
| `CMD_PTZ_CONTROL_TRANS_DATA` | 120+1 | PTZ 투과 전송 |
| `CMD_PTZ_SPEED_RESET` | 120+2 | PTZ 속도 리셋 |
| `CMD_PTZ_CALL_POSITION` | 120+3 | 좌표 호출 |
| `CMD_PLATFORM_CONTROL` | 120+4 | 플랫폼 제어 |
| `CMD_THERMAL_IMAGER` | 120+5 | 열화상 |
| `CMD_ZOOM_MULTIPLE_NOTIFY` | 120+6 | **줌 배율 변경 통지** |
| `CMD_GET_ZOOM_CFG` | SYSTEM_MANAGE_BASE+126 | **현재 줌 배율 및 최대 줌 배율 조회** |
| `CMD_CTRL_PTZ` | SYSTEM_MANAGE_BASE+128 | PTZ 직접 제어 |
| `CMD_GET_PTZ_STATUS` | SYSTEM_MANAGE_BASE+145 | PTZ 상태 조회(XML 포함) |
| `CMD_SEND_ADVANCE_PTZ_STATUS` | SYSTEM_MANAGE_BASE+138 | PTZ 상태 푸시(내부) |
| `CMD_NOTIFY_AF_FIRMWARE_UPGRADE_STATUS` | SYSTEM_MANAGE_BASE+140 | AF 펌웨어 업그레이드 상태 통지 |

### `function_list.h` — 능력집 마크로

광학 줌·PTZ·AF 관련 주요 매크로:

| 매크로 | 문자열 값 | 의미 |
|---|---|---|
| `FUNCTION_PTZ_CONTROL` | `"ptz_control"` | PTZ 제어 |
| `FUNCTION_PTZ_ALL_CTRL` | `"ptz_all_ctrl"` | 모든 PTZ 제어 |
| `FUNCTION_PTZ_ZOOM` | `"ptz_zoom"` | PTZ 줌 채널 |
| `FUNCTION_PTZ_FOCUS` | `"ptz_focus"` | PTZ 포커스 |
| `FUNCTION_PTZ_IRIS` | `"ptz_iris"` | PTZ 광권 |
| `FUNCTION_PTZ_2_DIRECTION` | `"ptz_2_direction"` | 2방향 PTZ |
| `FUNCTION_PTZ_4_DIRECTION` | `"ptz_4_direction"` | 4방향 PTZ |
| `FUNCTION_PTZ_8_DIRECTION` | `"ptz_8_direction"` | 8방향 PTZ |
| `FUNCTION_HIGHCTRL_PTZ` | `"high_ctrl_ptz"` | 고급 PTZ |
| `FUNCTION_PT_3D` | `"positioning_3d"` | 3D 포지셔닝 |
| `FUNCTION_ELE_ZOOM` | `"ele_zoom"` | **전동 줌(이중 렌즈 카메라 지원)** |
| `FUNCTION_ZOOM_TRACK` | `"zoom_track"` | **변배 추적** |
| `FUNCTION_AF_VERSION` | `"af_setting"` | **AF 설정** |
| `FUNCTION_AF_PROTOCOL_4` | `"af_protocol_4"` | AF 칩이 고급 PTZ 프로토콜 지원 |
| `FUNCTION_MANUAL_PTZ_SPEED` | `"manual_set_ptz_speed"` | 수동 PTZ 속도 |

### `data_struct.h` — 핵심 구조체

#### 자동 줌 트래킹 (`PdAction`, line 1284-1300)
```c
typedef struct {
    unsigned char draw_rect_enable;
    unsigned char draw_human_enable;
    unsigned char track_human_enable;
    unsigned char rect_twinkle_enable;
    AlarmOutputAction outputAction;
    AudioPlayAction   audioAction;
    unsigned char light_twinkle_enable;
    unsigned char notify_alarmserver_enable;
    unsigned char alarm_led_enable;
    unsigned char auto_zoom_enable;   // ← 변배(zoom) 추적 활성화
    unsigned char alarm_push;
    unsigned char reserve1, reserve2, reserve3;
} PdAction;
```

#### 디바이스 capability (`SECOND_DEFAULTCONFIG_DATA`, line ~1990)
```c
// ... 일부 발췌 ...
int ptz_yuntai;   // PTZ
int ptz_zoom;     // 줌 채널
int ptz_af;       // AF
int ptz_track;    // 추적
int ptz_cruise;   // 크루즈
int call;
int led_type;
```

### `media_cfg.h` / `common_head.h` / `tinyxml.h`
- `media_cfg.h` — `MediaStreamConfig`, `RtspConfig`, `webConfig`, `commConfig` 등 스트림 설정.
- `common_head.h` — `LONG`, `DWORD`, `BYTE`, `WORD` Win32 호환 타입 alias.
- `tinyxml.h` / `tinystr.h` — XML 응답 파싱용 외부 TinyXML(2002, Lee Thomason).

## 3.5 데모 `main.cpp` 분석

### 주요 구조
- **`main()`** — 명령 디스패처. stdin에서 한 줄씩 받아 처리.
- 전역 상태 컨테이너 `m_cameraInfoMap` — IPC 단위 정보를 SN으로 보관(스레드 안전을 위해 `Mutex` 사용).
- 콜백 3종:
  - `OnException()` — 예외/연결 끊김
  - `OnStateEvent()` — 로그인, 검색, PTZ 응답 등 상태 이벤트
  - `OnAUXResponse()` — XML 응답 처리(설정 GET/SET 결과)

### PTZ/줌 데모 흐름 (`main.cpp:1400`)
```cpp
int ptzControl(long lUserID) {
    char cmdstr[100], xmldata[1200];
    long nPspeed = 5, nTspeed = 5;

    while (fgets(cmdstr, sizeof(cmdstr), stdin)) {
        if (!strncmp(cmdstr, "ptz esc", 7)) break;
        if (!strncmp(cmdstr, "esc", 3))     break;
        // ...
        sprintf(xmldata,
            "<xml>\n<cmd>%s</cmd>"
            "<panspeed>%ld</panspeed>"
            "<tiltspeed>%ld</tiltspeed></xml>",
            cmdstr, nPspeed, nTspeed);
        IP_NET_DVR_PTZControlEx(lUserID, xmldata);
        Sleep(1);
    }
    return 0;
}
```

도움말 메시지에 따른 사용 가능 명령(`main.cpp:1429`):
> *"valid command: [up] [down] [left] [right] [stop] [esc]...."*

문자열 명령 카탈로그(헤더 enum 기준 추정):
- 방향: `up`, `down`, `left`, `right`, `up_left`, `up_right`, `down_left`, `down_right`
- 줌: `zoom_in`, `zoom_out`
- 포커스: `focus_near`, `focus_far`
- 광권: `iris_open`, `iris_close`
- 정지: `stop`

### 이벤트 코드 (`NetSDKDLL.h:155-204`) 일부 발췌
| 값 | enum | 의미 |
|---|---|---|
| 0 | `EVENT_CONNECTING` | 연결 중 |
| 1 | `EVENT_CONNECTOK` | 연결 성공 |
| 4 | `EVENT_LOGINOK` | 로그인 성공 |
| 10 | `EVENT_SENDPTZOK` | PTZ 명령 전송 성공 |
| 11 | `EVENT_SENDPTZFAILED` | PTZ 실패 |
| 20 | `EVENT_SENDPTZERROR` | PTZ 오류 |
| 22 | `EVENT_PTZALARM` | PTZ 경보 |
| 21 | `EVENT_PTZPRESETINFO` | 프리셋 정보 응답 |
| 24 | `EVENT_RECVVIDEOPARAM` | 비디오 파라미터 수신 |
| 25 | `EVENT_RECVAUDIOPARAM` | 오디오 파라미터 수신 |

## 3.6 SDK vs HAPI 비교

| 항목 | NETSDK | HAPI(HTTP) |
|---|---|---|
| **통합 난이도** | 높음(C/C++, aarch64 라이브러리 링크, 헤더 인코딩 문제) | 낮음(REST + JSON) |
| **포팅성** | aarch64 Linux 한정 | OS/언어 무관 |
| **줌 제어 latency** | 직접 소켓 — 가장 낮음 | HTTP 단기 연결 — 추가 latency |
| **세션 관리** | `IP_NET_DVR_Login` + 자동 재연결 | `getuid` + 60초 `keep_alive` |
| **이벤트 수신** | 콜백(in-process) | 클라이언트 측 TCP listener 필요 |
| **라이브 스트림** | `no_live555` 빌드에서 미지원 — 외부 RTSP 필요 | `/sysinfo/rtspurl`로 URL 받아 외부 RTSP 필요(동일) |
| **펌웨어 업그레이드** | `IP_NET_DVR_Upgrade` 직접 호출 | 해당 HAPI 없음(별도 펌웨어 채널 필요) |
| **PTZ 명령** | `IP_NET_DVR_PTZControl(ZOOM_IN_VALUE, ...)` 또는 `PTZControlEx`(XML) | `/ptz_ctrl/zoom?direction=in` |
| **autostop 지원** | 별도 `STOPACTION`(=24) 명령으로 정지 | `autostop` 파라미터로 ms 지정 |

> **권장**: 줌·PTZ 등 단순 제어는 HAPI, 펌웨어 업그레이드/배치 디바이스 검색/디바이스 측 콜백 이벤트가 필요한 통합은 NETSDK. 양쪽을 동시에 사용해도 무방하나, 인증 세션은 분리.

## 3.7 통합 시 주의 사항

1. **`-DLINUX -DNETSDK`** 컴파일러 매크로 필수(readme.txt §2). 누락 시 IPCAMERA 측 구조체와 SDK 측 구조체 필드 정렬이 어긋남.
2. **음성 인터컴은 LINUX SDK에서 미실현**(`readme.txt §4`): *"对讲在LINUX SDK里面未实现".* HAPI에는 양방향 인터컴 API가 별도로 없으므로, 이 기능이 필요하면 RTSP back channel 또는 별도 채널 검토.
3. **`libNetSDK_no_live555`만 제공** → RTSP 라이브 프리뷰 API(`IP_NET_DVR_RealPlay*`)는 호출 금지. RTSP는 외부 클라이언트 사용.
4. **헤더 인코딩**: 주석을 읽고자 한다면 `iconv -f GBK -t UTF-8 NetSDKDLL.h > NetSDKDLL.utf8.h` 변환 후 참조.
5. **사전 빌드 `demo_test`**는 x86_64일 가능성 — aarch64 보드에서는 재컴파일 필요.
