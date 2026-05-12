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

`demo/demo_test`(2.8 MB)는 `file` 검사 결과 **x86_64 ELF**로 확정됩니다:
```
ELF 64-bit LSB pie executable, x86-64, version 1 (SYSV),
dynamically linked, BuildID[sha1]=0713e2..., for GNU/Linux 3.2.0, with debug_info, not stripped
```
반면 라이브러리는 **aarch64 전용**(`ELF 64-bit LSB shared object, ARM aarch64`):
```
$ file lib/aarch64/libNetSDK_no_live555.so
ELF 64-bit LSB shared object, ARM aarch64, version 1 (SYSV), dynamically linked, stripped
```
즉 SDK 패키지에 동봉된 `demo_test`는 본 패키지의 `lib/aarch64/*` 와 ABI가 일치하지 않습니다. **벤더가 별도의 x86_64 빌드(`lib/x86_64/`)에 대해 사전 컴파일한 결과물을 그대로 동봉한 흔적**으로 추정되며, 본 패키지만으로는 재현 불가능합니다. aarch64 보드에서 검증하려면:
- aarch64 호스트(또는 SBC, 예: Raspberry Pi 4/5, NVIDIA Jetson 등)에서 `make PLATFORM=aarch64 CROSS_COMPILE=`로 네이티브 빌드, 또는
- x86_64 호스트에서 `aarch64-linux-gnu-g++` 툴체인으로 교차 컴파일 후 `qemu-aarch64-static` + `binfmt_misc`로 실행.

### .so 의존성
```
$ readelf -d libNetSDK_no_live555.so | grep NEEDED
NEEDED libstdc++.so.6, libm.so.6, libgcc_s.so.1, libc.so.6
```
순수 표준 C/C++ 런타임만 요구. TinyXML/iXML은 정적 링크되어 있어 별도 의존성 없음(`libtinyxml.so`, `libixml.so`는 데모 빌드에서 사용하지 않음).

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

총 **217개 typedef**(struct/enum) 정의. 주요 카테고리:

| 카테고리 | 대표 typedef |
|---|---|
| 시간/세션 | `TimeConfig`, `SummerTimeConfig`, `NTPConfig`, `TimeSpanCfg` |
| 사용자/권한 | `UserConfig`, `UserAccount`, `Group` |
| 시스템 | `SystemConfig`, `SyslogConfig`, `MiscConfig`, `MaintainConfig` |
| **미디어 캡처** | `VideoCapture`(line 555-617) — brightness/contrast/saturation/sharpness, hflip/vflip/rotate, WDR, IRcut, shutter, ISP, LED, gain |
| **인코딩** | `VideoEncode`, `VideoEncodeCfg`(line 410-424) — `streamID`, `Resolution`, `VideoEncodeFormat`, `BitRateControl`, `initQuant`, `bitRate`, `frameRate`, `display_frameRate`, `QPConfig` |
| **OSD/오버레이** | `VideoOverlay`, `TimeOverlay`, `TitleOverlay`, `VideoUserOverlay`, `UserOSD` |
| 비디오 마스크/ROI | `VideoMaskConfig`, `VideoROI`, `MASK_AREA_ENTRY`, `ROI_AREA_ENTRY` |
| 오디오 | `AudioConfig`, `AudioCapture`, `AudioEncode`, `AudioEncodeType` |
| 미디어 스트림 서버 | `MediaStreamConfig`, `RtspConfig`, `WebConfig`, `CommConfig`, `MulticastConfig`, `HikConfig`, `DhConfig` |
| 플랫폼 | `PlatformConfig`, `VmPlatformConfig`, `VoipConfig`, `GB28181Config` |
| 녹화 | `RecordConfig`, `ScheduleRecordConfig`, `AlarmRecordConfig`, `AlarmCaptureConfig` |
| 알람 | `AlarmConfig`, `InputAlarm`, `MotionDetectAlarm`, `PdAlarm`, `LprAlarm`, `VideoCoverAlarm`, `VideoLostAlarm`, `StorageFullAlarm`, `TempHumidityAlarm`, `VideoGateAlarm`, `VideoRegionAiAlarm`, `FaceDetectAlarm` |
| AI 알람 액션 | `PdAction`, `LprAction`, `FdAction`, `VehicleShapeAction`, `VideoGateAction`, `RegionAiAction`, `TempHumidityAction` |
| **PTZ** | `PTZConfig`, `PTZCommonConfig`, `PTZAdvanceConfig`, `PTZFunction`, `AfConfig` |
| 네트워크 | `NetworkConfigNew`, `LANConfig`, `WIFIConfig`, `ADSLConfigNew`, `PPTPConfig`, `DDNSConfig`, `UPNPConfig`, `P2PConfig`, `G3Config`, `AlarmServerConfig` |
| 서버 | `ServerConfig`, `FtpServer`, `SmtpServer` |
| 시간/위치/스토리지 알림 데이터 | `SDCARD_INFO_DATA`, `USB_INFO_DATA`, `NETWORK_INFO_DATA`, `STORAGE_INFO_DATA`, `NETWORK_STATUS_DATA`, `SYSTEM_VERSION_DATA`, `WIFI_AP_INFO` |

#### `VideoCapture` (image 파라미터, line 555-617)
HAPI `/system/image/get`·SCF `Capture` 영역과 1:1 매핑되는 핵심 구조:
```c
typedef struct {
    int brightness;
    int contrast;
    int saturation;
    int sharpness;

    unsigned char tvsystem;          // 0: NTSC 60Hz 1: PAL 50Hz
    unsigned char forct_antiflicker; // capability "antiflicker"
    short reserved;
    unsigned short cropxpix;         // capability "video_crop"
    unsigned short cropypix;

    int hflip;
    int vflip;
    int rotate;                      // capability "rotate_enable"

    int whitebalance;                // (enable<<24)|(R<<16)|(G<<8)|B
    int backlight;                   // 보조광 0-255
    int HLC;                         // 강광억제 0-255
    int tnf;                         // 2D 노이즈리덕션 0-255
    int snf;                         // 3D 노이즈리덕션 0-255

    int bManualGain;                 // 0=AUTO 1=MANUAL ("gainsetting")
    int gainValue;

    int wdr_mode;                    // VideoWdrMode ("wdr_setting")
    DayTimeSpan wdr_worktime;
    int wdr_value;

    int dfrog_flag;                  // 안개제거
    int dfrog_value;

    VideoShutter shutterSetting;     // "VideoShutter"

    int isp_mode_color;              // 0-3
    int isp_mode_night;              // 0-3
    int videoEncodeMode;             // VideoEncodeMode

    IRCutMode ircut_mode;
    unsigned char ircut_sensitivity;
    unsigned char ircut_openled_delay;
    unsigned char led_brightness_mode;
    unsigned char led_brightness_value;
    unsigned char led_brightness_alarm;
    DayTimeSpan ircut_nighttime;
    int ircut_keepcolor;
    LedMode led_mode;
    LedImageMode ispadvmode;

    unsigned char light_off_sensitivity;
    unsigned char face_exposure_sensitivity;
} VideoCapture;
```

#### `VideoEncodeCfg` (스트림별 인코딩, line 410-424)
```c
typedef struct {
    int enable;
    int streamID;
    Resolution         resolution;       // ex. "1080P", "720P"
    VideoEncodeFormat  encodeFormat;     // ex. "H264", "H265"
    BitRateControl     bitRateControl;   // ex. "CBR", "VBR"
    int initQuant;                       // ← HAPI/SCF의 GOP 와 1:1 매핑 ⚠
    int bitRate;
    int frameRate;
    int display_frameRate;
    LbrControl         lbrConfig;
    VideoQualityEnum   bitRateQuality;
    QPConfig           qp;
} VideoEncodeCfg;
```
> ⚠ **`initQuant` ↔ HAPI `gop` ↔ SCF `Initquant`**: 세 채널 모두 같은 펌웨어 파라미터를 가리키는 별칭입니다(`docs/07-scf-api.md §4.3.5` 참조). 본 분석은 NETSDK 헤더가 SCF 명명(`Initquant`)을 그대로 유지함을 확인합니다.

#### PTZ 자동 줌 트래킹 (`PdAction`, line 1284-1300 부근)
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

#### `AfConfig` (오토포커스, line 179-184)
```c
typedef struct {
    int enable;
    int type;            // 0: BSD 1: ZUO
    int bSendOnStart;    // 시작 시 AF 명령 자동 발사
} AfConfig;
```

### `media_cfg.h` / `common_head.h` / `tinyxml.h`
- `media_cfg.h` — OSD 위치 타입(`Positiontype`, `PositionByCornerEnum`), 알람 코드(`AjAlarmCode`, 45+ 값), AI 알람 타입(`AjAiAlarmType`), 비디오 코덱(`VideoEncodeType_e`: H264/H265/H264+/H265+/H265SMART/MJPEG), 오디오 코덱(`AudioType_e`: PCMU/AAC/PCMA/PCM/OPUS/MP3), `RESOLUTION_ENTRY`/`AUDIO_CODEC_ENTRY` 등.
- `common_head.h` — `LONG`, `DWORD`, `BYTE`, `WORD` 등 Win32 호환 타입 alias + `Sleep()` 매크로 + `CRITICAL_SECTION = pthread_mutex_t` 매핑.
- `tinyxml.h` / `tinystr.h` — XML 응답 파싱용 외부 TinyXML(2002, Lee Thomason).

## 3.4.1 공개 API 카탈로그 (`libNetSDK_no_live555.so` export 245개)

`nm -D --defined-only libNetSDK_no_live555.so | grep 'IP_NET_DVR_'` 결과 245개의 함수 심볼이 export됩니다. 헤더 선언과 1:1 일치하며(누락 1건: `IP_NET_DVR_SET_ModuleConfig` — 헤더에는 선언되지만 .so에는 미구현), **헤더에 선언된 모든 함수가 실제로 빌드되어 있음**을 확인했습니다.

기능별 분류:

| 분류 | 개수 | 대표 API |
|---|---|---|
| 라이프사이클·로그·콜백 | 9 | `Init`, `Cleanup`, `GetSDKVersion`, `GetSDKBuildVersion`, `Get_Timestamp`, `LOG_OPEN`, `LOG_CLOSE`, `SetLogToFile`, `SetExceptionCallBack`, `SetAUXResponseCallBack`, `SetStatusEventCallBack` |
| 디바이스 검색·로그인 | 13 | `Login`, `Logout`, `LogoutAll`, `Login_Encrypt`, `EXCHANGE_Encrypt`, `Reconnect`, `SetAutoReconnect`, `StartSearchIPC`, `StopSearchIPC`, `GetIPCInfo(XML)`, `SearchIPCReleaseInfo`, `ModifyIPCBy*`, `Set_Search_ROOTNAME`, `SetSearchInterval` |
| 라이브 프리뷰 | 7 | `RealPlay`, `RealPlayEx`, `StopRealPlay`, `StopAllRealPlay`, `GetVideoParam`, `GetAudioParam`, `SetRealDataCallBack` |
| PTZ | 3 | `PTZControl`, `PTZControlEx`, `PTZPreset` |
| 스냅샷 | 3 | `SnapPic`, `SnapPicTaskStart`, `SnapPicTaskStop` |
| 녹화(SDK 내부 저장) | 6 | `StartRecord`, `StopRecord`, `StartRecordStream`, `InputRecordStream`, `StopRecordStream`, `CreateIFrame` |
| 음성 인터컴 | 6 | `StartTalk`, `StopTalk`, `AddTalk`, `RemoveTalk`, `StartVoiceCom`/`StopVoiceCom`, `InputAudioData`, `SetVoiceComClientVolume` |
| 시스템 제어(범용) | 5 | `SystemControl`(CMD 코드 전달), `GetDVRConfig`, `SetDVRConfig`, `WriteAUXStringEx`, `SendRawMsg` |
| 시스템 제어(전용) | 11 | `RebootDVR`, `ShutDownDVR`, `RebootIPCBySN`, `RestoreIPCBySN`, `RestoreConfig`, `Ircut_switch_daynight`, `FormatDisk`, `GetFormatProgress`, `Upgrade`, `UploadFile`, `CloseUpgradeHandle`, `GetUpgradeProgress`, `GetUpgradeState`, `SCARE_OFF`, `SEND_ENCRYPPT_RAWDATA` |
| 펌웨어 GET 명령(비동기) | 22 | `GET_AlarmConfig`, `GET_AudioCapture`, `GET_VideoEncodeConfig`, `GET_VideoCaptureConfig`, `GET_VideoOverlayConfig`, `GET_MediaConfig`, `GET_MediaStreamConfig`, `GET_NetworkLANConfig`, `GET_NetworkConfig`, `GET_PtzConfig`, `GET_SystemConfig`, `GET_TimeConfig`, `GET_SYSTEMTIME`, `GET_MediaCapability` 등 |
| 펌웨어 SET 명령(직접) | 25 | `SET_VideoEncodeConfig`, `SET_VideoCaptureConfig`, `SET_VideoOSDConfig`, `SET_VideoUserOSDConfig`, `SET_VideoMaskConfig`, `SET_VideoConfig`, `SET_AudioConfig`, `SET_MediaConfig`, `SET_MediaStreamConfig`, `SET_NetworkLANConfig`, `SET_NetworkConfig`, `SET_NetworkWIFIConfig`, `SET_UserConfig`, `SET_TimeConfig`, `SET_SYSTEMTIME`, `SET_AlarmConfig`, `SET_InputAlarmConfig`, `SET_MotionDetectAlarm`, `SET_PersonDetectAlarm`, `SET_VlAlarmConfig`, `SET_VCAlarmConfig`, `SET_VideoGateAlarmConfig`, `SET_OutputAlarmConfig`, `SET_PlatformConfig`, `SET_GB28181Config`, `SET_MiscConfig` |
| XML ↔ struct 변환 | 약 60 | `XMLGET_*`(struct → XML 문자열, malloc 반환), `Media_get*ByXml`, `Network_get*ByXml`, `System_get*ByXml`, `Alarm_get*ByXml`, `Get*CfgByXml`, `XMLGET_MediaCapability` |
| 파일 다운로드 | 4 | `GetFileByName`, `StopGetFile`, `GetDownloadState`, `GetDownloadPos`, `GetConfigFile`, `SetConfigFile` |
| 녹화 재생 | 7 | `GetReplayAblity`, `GetReplay_Dates_Distribute(ByXml)`, `GetReplay_OneDay_Distribute(ByXml)`, `GetReplay_SearchMode_ByXml`, `PlayDeviceFile`, `ReplayByTime`, `ControlReplay`, `SetReplayDataCallBack`, `SetReplayEventCallBack` |
| 사용자 데이터(보조) | 2 | `GetUserData`, `SetUserData` |
| 유틸 | 3 | `GetLastErrorCode`, `GET_EVENTNAME`(이벤트 코드 → 문자열), `wzwTest`(내부 디버그용으로 보임) |

> **헤더에만 선언되고 export 안 된 함수: `IP_NET_DVR_SET_ModuleConfig`**. 다른 4개(`IP_NET_DVR_ALARMER`, `..._CLIENTINFO`, `..._DEVICEINFO`)는 구조체 typedef 이름으로 함수 아님.

## 3.4.2 통신 프로토콜

라이브러리 strings 분석에서 다음이 확인됩니다:

```
<?xml version="1.0" encoding="GB2312" ?>
<XML_TOPSEE>
  <MESSAGE_HEADER Msg_type="REPLAY_CONTROL_MESSAGE" Msg_code="%ld" Msg_flag="0" />
  <MESSAGE_BODY>
    <REQUEST_PARAM FileName="%s" StartPos="%d" PlayParam="%ld" />
  </MESSAGE_BODY>
</XML_TOPSEE>
```

- **루트 태그: `XML_TOPSEE`** ← SCF/SOAP의 `<XML_TOPSEE>`와 동일한 명명. 본 SDK는 SCF의 클라이언트 구현이라고 봐도 무방.
- **인코딩: GB2312** (HAPI는 UTF-8). 다국어 OSD를 SDK 경로로 변경할 때 인코딩 변환에 주의.
- **포트: `PTZPort` 기본 8091** (`config.cfg`, `conf.ipc.xml` 양쪽 모두). HAPI(80)·RTSP(554)·SCF(80)와는 다른 별도 포트.
- **SET 함수가 직접 GET 없이도 동작 가능**해 보이나, 헤더 주석(GBK)에 *"먼저 GET으로 한 번 읽고 필요한 항목만 수정하여 SET 호출, 그렇지 않으면 디바이스가 정상 동작하지 않을 수 있다"*는 경고가 명시되어 있음. `wgwk_camera.merge_into_current()`가 채택한 패턴과 동일.

> 본 SDK가 `XML_TOPSEE`를 사용한다는 사실은 **HAPI `/system/video/set`의 펌웨어 버그를 우회하기 위해 SCF `/setMediaVideoEncodeConfig`로 라우팅하는 우리 라이브러리의 결정과 정합**합니다. SCF 채널은 벤더가 공식 SDK에서도 사용하는 채널이므로, 안정성 측면에서 권장 경로입니다(`docs/07-scf-api.md §4.3.5`, `docs/09-library-api.md` 참조).

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

### 데모 명령 핸들러 카탈로그 (`g_cmd[]`, `main.cpp:2827`)

데모는 `main.cpp` 단일 파일에 47개의 stdin 명령 핸들러를 정의하며, 각 핸들러는 SDK API 1~2개를 호출합니다.

| stdin 명령 | 핸들러 함수 | 호출하는 SDK API |
|---|---|---|
| `Login by config.cfg` | `handle_login` | `IP_NET_DVR_Login(ip, port, user, pass, NULL)` |
| `Logout` | `handle_logout` | `IP_NET_DVR_Logout` |
| `Start searchIPC` | `handle_search_begin` | `IP_NET_DVR_StartSearchIPC` (별도 thread로 결과 출력) |
| `Stop searchIPC` | `handle_search_stop` | `IP_NET_DVR_StopSearchIPC`, `SearchIPCReleaseInfo` |
| `Read SN` | `handle_readsn` | `IP_NET_DVR_SystemControl(CMD_GET_SERIALNUMBER, ...)` |
| `Snapshot` | `handle_snappic` | `IP_NET_DVR_SnapPic(id, 0/1, 100, "*.jpg", 0)` |
| `Reboot one by SN` | `handle_reboot` | `IP_NET_DVR_RebootIPCBySN(SN)` (브로드캐스트) |
| `Reboot logged in` | `handle_rebootLoggedin` | `IP_NET_DVR_RebootDVR(id)` (유니캐스트) |
| `Restore one by SN` | `handle_restore` | `IP_NET_DVR_RestoreIPCBySN(SN)` |
| `Get device time` | `handle_gettime` | `IP_NET_DVR_SystemControl(CMD_GET_SYSTEM_TIME, ...)` |
| `Sync nowtime` | `handle_settime` | `IP_NET_DVR_SET_SYSTEMTIME(id, &AjTime)` |
| `Get current version` | `handle_get_version` | `IP_NET_DVR_SystemControl(CMD_GET_SYSTEM_VERSION_INFO, ...)` |
| `Get sdk version` | `handle_getsdkversion` | `IP_NET_DVR_GetSDKVersion()` |
| `Get overlay OSD` | `handle_get_osd` | `IP_NET_DVR_GET_VideoOverlayConfig(id)` |
| `Set OSD` | `handle_setosd` | `IP_NET_DVR_SET_VideoOSDConfig(id, &VideoOverlay)` ← 글로벌 캐시 `g_ipc_mediacfg` 변경 |
| `Set user OSD` | `handle_setuserosd` | `IP_NET_DVR_SET_VideoUserOSDConfig(id, &VideoUserOverlay)` |
| `PTZ begin` | `handle_ptz` / `ptzControl` | `IP_NET_DVR_PTZControlEx(id, "<xml><cmd>..</cmd>..</xml>")` 루프 |
| `Start realplay` | `handle_realplay_begin` | `IP_NET_DVR_RealPlayEx(ip, user, pass, OnMediaRecv, &uinfo, 1)` ⚠ `no_live555` 빌드에서는 호출 금지 |
| `Stop realplay` | `handle_realplay_stop` | `IP_NET_DVR_StopRealPlay(handle)` |
| `Show/Hide debug` | `handle_show_debug` / `_hide_debug` | `IP_NET_DVR_SetLogToFile(3 or 0, ".", 0)` |
| `Get handle_GetDeviceAbility` | `handle_GetDeviceAbility` | `IP_NET_DVR_GetDeviceAbility(id)` |
| `Get config` | `handle_get_config` | 다양한 `IP_NET_DVR_GET_*Config` 호출 |
| `Download config` | `handle_download_config` | `IP_NET_DVR_GetConfigFile(id, "conf.ipc.xml")` |
| `Upload config` | `handle_upload_config` | `IP_NET_DVR_SetConfigFile(id, "conf.ipc.xml")` |
| `Network config ModifyIPCBySN` | `handle_modifyipc` | `IP_NET_DVR_ModifyIPCBySN(SN, &LANConfig, &MediaStreamConfig)` |
| `Start record` | `handle_record_start` | `IP_NET_DVR_StartRecord(handle, "./", 60, 600)` |
| `Stop record` | `handle_record_stop` | `IP_NET_DVR_StopRecord(handle)` |
| `Set FPS` | `handle_setfps` | `IP_NET_DVR_SET_VideoEncodeConfig(id, &VideoEncode)` |
| `Set audio enable` | `handle_setaudioenable` | `IP_NET_DVR_SET_AudioConfig(id, &AudioConfig)` |
| `Ircut control` | `handle_ircutcontrol` | `IP_NET_DVR_Ircut_switch_daynight(id, day)` |
| `Replay test` | `handle_replaytest` | `IP_NET_DVR_ReplayByTime(id, time_today)` + `SetReplayDataCallBack` |
| `Upgrade test` | `handle_upgrade_test` | `IP_NET_DVR_Upgrade(id, filename)` |

### 데모가 보여주는 SDK 사용 패턴(요약)

1. **초기화 → 콜백 등록**: `IP_NET_DVR_Init()` → `SetStatusEventCallBack(OnStateEvent)` + `SetAUXResponseCallBack(OnAUXResponse)`.
2. **로그인**: `Login(ip, ptz_port=8091, user, pass, NULL)` → `OnStateEvent`에서 `EVENT_LOGINOK` 수신.
3. **설정 조회는 비동기**: `IP_NET_DVR_GET_MediaConfig(id)` 호출만 하면 응답이 `OnAUXResponse`로 들어옴. `ActionCode = CMD_GET_MEDIA_CONFIG` 분기에서 `IP_NET_DVR_GetMediaCfgByXml(&cfg, pResponse)` 로 XML 파싱 → 글로벌 `g_ipc_mediacfg` 캐시.
4. **설정 변경은 GET → modify → SET**: 위에서 캐시한 `g_ipc_mediacfg`를 수정한 뒤 `SET_*` 직접 호출. (헤더 주석의 권고를 그대로 구현.)
5. **PTZ는 명령 문자열 + XML**: `<xml><cmd>zoom_in</cmd><panspeed>5</panspeed>...</xml>` 형식. `STOP_ACTION`(=24) 또는 `"stop"`을 보내 정지.
6. **이벤트는 단일 콜백 분기**: 47가지 이상의 `EVENT_*` 코드를 `switch(nStateCode)`로 처리.

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
4. **헤더 인코딩**: 주석을 읽고자 한다면 `iconv -f GBK -t UTF-8 NetSDKDLL.h > NetSDKDLL.utf8.h` 변환 후 참조. 파일 본문은 CRLF 줄바꿈(`file` 결과: *with CRLF line terminators*)이므로 `tr -d '\r'`로 LF 변환 후 grep 권장.
5. **사전 빌드 `demo_test`는 x86_64**(확정), 라이브러리는 **aarch64**(확정) — ABI 불일치. aarch64 환경 또는 cross-compile 필요.
6. **포트 8091은 외부 노출 주의**: PTZPort(8091)는 본 SDK의 제어 채널이지만 동시에 SCF(`/setMediaVideoEncodeConfig` 등)와 HAPI(80)의 추상화를 위한 백엔드입니다. 방화벽에서 차단 시 SDK 사용 불가.
7. **`-O0 -g` 디폴트**: 데모 Makefile은 디버깅 편의를 위해 최적화를 끄고 디버그 심볼을 유지. 운영 빌드에서는 `-O2 -DNDEBUG` 권장.

## 3.8 본 라이브러리(`wgwk_camera`)와의 매핑

`src/wgwk_camera/`의 Python 추상화는 NETSDK의 모든 핵심 기능을 HAPI/SCF 조합으로 대체합니다. **NETSDK를 직접 링크하지 않아도 동일한 결과**를 얻을 수 있습니다.

| 기능 | NETSDK | `wgwk_camera` (HAPI/SCF) |
|---|---|---|
| 로그인 | `IP_NET_DVR_Login(ip, 8091, ...)` | `Camera()` 생성 시 `ControlClient.get_uid()`(HAPI port 80) |
| 세션 유지 | 라이브러리 내부 자동 reconnect | `keep_alive` 30s 주기, `Camera.refresh_session()` |
| 디바이스 정보 | `IP_NET_DVR_SystemControl(CMD_GET_SYSTEM_VERSION_INFO)` | `Camera.device_info()` |
| 줌 IN | `IP_NET_DVR_PTZControl(id, ZOOM_IN_VALUE, ts, sp)` | `Camera.zoom_in(autostop_ms=500)` |
| 줌 OUT | `IP_NET_DVR_PTZControl(id, ZOOM_OUT_VALUE, ts, sp)` | `Camera.zoom_out(autostop_ms=500)` |
| 줌 정지 | `IP_NET_DVR_PTZControl(id, STOPACTION, ...)` | `Camera.zoom_stop()` |
| 프리셋 호출 | `IP_NET_DVR_PTZPreset(id, GOTO_PRESET, idx)` | `Camera.goto_preset(idx)` |
| 스냅샷 | `IP_NET_DVR_SnapPic(id, 0, 100, "*.jpg", 0)` | `Camera.snapshot("frame.jpg")` |
| 이미지 파라미터 변경 | `IP_NET_DVR_GET_VideoCaptureConfig` → modify → `SET_VideoCaptureConfig` | `Camera.admin.set_image(brightness=..., wdr_mode=...)` |
| OSD ON/OFF | `IP_NET_DVR_SET_VideoOSDConfig(&overlay)` | `Camera.admin.apply_osd(enabled=False)` |
| 인코딩 변경 | `IP_NET_DVR_SET_VideoEncodeConfig(&encode)` | `Camera.admin.apply_encoding_profile(PRECISION_PROFILE)` ← SCF 라우팅 |
| 미디어 캐퍼빌리티 | `IP_NET_DVR_GET_MediaCapability` | `Camera.control.video_capability()` |
| RTSP URL | (라이브러리 미지원, `no_live555`) | `Camera.video_main().url` |
| OpenCV 통합 | (없음) | `with cam.video_main().opencv() as cap:` |
| 재부팅 | `IP_NET_DVR_RebootDVR(id)` | `Camera.admin.reboot(confirm=True)` |
| 공장 초기화 | `IP_NET_DVR_RestoreConfig(id)` | **의도적으로 미구현**(주석으로만 안내) |

### 본 라이브러리가 NETSDK 대비 갖는 이점

1. **순수 Python + 표준 HTTP/RTSP** — 의존성: `requests`, (선택) `opencv-python`. NETSDK처럼 aarch64 전용 .so를 빌드/배포할 필요 없음.
2. **x86_64/aarch64 OS 무관** — NUC8(x86_64), Jetson(aarch64), RPi(aarch64), 클라우드 VM 모두 동일.
3. **`dry_run=True` 디폴트 안전망** — NETSDK SET API는 호출 즉시 적용. 본 라이브러리 `admin.apply_*`는 변경 사항을 `diff`로만 반환.
4. **GOP 클램프 가드** — 펌웨어가 GOP를 fps 정수배로 강제 조정하는 거동을 `gop_will_clamp()`로 예측·경고/거부.
5. **펌웨어 버그 우회** — HAPI `/system/video/set`의 RemoteDisconnected 버그를 SCF `/setMediaVideoEncodeConfig`로 자동 라우팅.
6. **OpenCV/FFmpeg/GStreamer 통합** — `VideoStream` 추상으로 `cap.read()`까지 한 줄.

### NETSDK가 본 라이브러리 대비 갖는 이점

1. **저지연 PTZ** — TCP 8091 long-lived 세션. HAPI는 GET/PUT마다 TCP 연결 수립(keep-alive 사용해도 추가 latency).
2. **이벤트 푸시** — `OnStateEvent`/`OnAUXResponse` 콜백으로 모션디텍션, 알람, 줌 배율 변경(`CMD_ZOOM_MULTIPLE_NOTIFY`) 등을 푸시 형태로 수신. HAPI에서는 폴링 필요.
3. **펌웨어 업그레이드 API** — `IP_NET_DVR_Upgrade(id, "firmware.bin")`. HAPI에는 동등 기능 없음(웹 UI 또는 SCF로 우회).
4. **디바이스 검색(브로드캐스트)** — `StartSearchIPC`로 LAN의 모든 IPCAMERA를 자동 발견. HAPI에는 검색 API 없음(IP를 미리 알아야 함).
5. **녹화 파일 재생** — `ReplayByTime`, `GetReplay_Dates_Distribute` 등 SD 카드 녹화 재생 흐름이 명세화. HAPI에 동등 채널 없음.

### 종합 권장

| 사용 시나리오 | 권장 채널 |
|---|---|
| 단일 카메라, 줌·스냅샷·라이브 스트림 중심 | **`wgwk_camera` (HAPI/SCF/RTSP)** |
| 다수 카메라 자동 검색·일괄 펌웨어 업그레이드 | **NETSDK** (단, aarch64 보드 한정) |
| 알람·이벤트 푸시 처리 | NETSDK 콜백 — 또는 별도 webhook 서버 구축(HAPI) |
| 임베디드 클라이언트(Jetson/Raspberry Pi) | 둘 다 가능. 단순함은 `wgwk_camera`, 저지연·이벤트 푸시는 NETSDK |
| Windows/macOS 데스크탑 | **`wgwk_camera`** (NETSDK는 Linux aarch64 전용) |

## 3.9 본 분석에서 사용한 검증 명령

```bash
# 1. 헤더의 함수 선언 수집 (CRLF 정규화)
tr -d '\r' < include/NetSDKDLL.h | grep -oE 'IP_NET_DVR_[A-Za-z_0-9]+' | sort -u > /tmp/decls.txt

# 2. .so에서 export된 함수 수집
nm -D --defined-only lib/aarch64/libNetSDK_no_live555.so | awk '$2=="T"{print $3}' | grep ^IP_NET_DVR_ | sort > /tmp/exports.txt

# 3. 양방향 diff
comm -23 /tmp/decls.txt /tmp/exports.txt   # 헤더에만 있고 .so에 없음 → IP_NET_DVR_SET_ModuleConfig 등 4건
comm -13 /tmp/decls.txt /tmp/exports.txt   # .so에만 있고 헤더에 없음 → (없음)

# 4. .so 의존성
readelf -d lib/aarch64/libNetSDK_no_live555.so | grep NEEDED

# 5. 데모 함수 카탈로그
awk '/^(static |void |int |LONG |const char\*)/ && /\(/ {print NR": "$0}' demo/main.cpp

# 6. data_struct.h typedef 카탈로그(CRLF 정규화 필요)
tr -d '\r' < include/data_struct.h | awk '/^}/{print NR": "$0}'
```

총 217개 typedef, 245개 export 함수, 47개 데모 stdin 핸들러를 식별 — 본 SDK의 공식 표면적 전체.
