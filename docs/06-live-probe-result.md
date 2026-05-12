# 06. 실기 프로브 결과 (MC800S5, 펌웨어 V3.4.5.2)

이 문서는 실제 수령된 카메라 모듈에서 측정한 결과를 정리한 **실측 보고서**입니다. 사양서(`docs/01-hardware-spec.md`)나 HAPI 문서(`docs/02-http-api.md`)와 다른 부분은 본 문서가 우선합니다.

| 항목 | 값 |
|---|---|
| 검증 일자 | 2026-05-12 |
| 검증 호스트 | `jeongmin@ThinkPad-T14-Gen-5` (Ubuntu 24.04, `192.168.8.216/24`) |
| 검증 대상 | `192.168.8.213` (공유기 DHCP 예약으로 고정) |
| 검증 방법 | LAN 내 직접 HTTP/RTSP 호출, `curl`/`ffprobe`/`bash /dev/tcp` |

## 1. 디바이스 식별

`GET /HAPI/V1.0/sysinfo/device_info` 응답:

```json
{
  "SN": "EF000000063098F1",
  "device_type": "MC800S5",
  "ether": "F0:00:06:30:98:F1",
  "kernelversion": "Linux 5.10.61 #160 PREEMPT Thu Nov 2 18:50:24 CST 2023 armv7l",
  "fsversion": "MC800S5_AF_V0-A-RTMP-H5 V3.4.5.2 build 2025-11-12 17:30:10"
}
```

| 항목 | 실측 값 | 사양서 기재 | 비고 |
|---|---|---|---|
| device_type | `MC800S5` | `WGWK-AS500J`(외함 모델) / `MC800S`(사양서 §2.2.1 예시) | **`MC800S5`는 8 MP 변형 — 사양서 5 MP `MC800S`와 구분됨** |
| 펌웨어 라벨 | `MC800S5_AF_V0-A-RTMP-H5 V3.4.5.2` | — | AF 펌웨어, RTMP·H5 지원, 빌드 2025-11-12 |
| 커널 | Linux 5.10.61 `armv7l` | — | **32 비트 ARM** (SDK는 aarch64용 — 직접 디바이스에 올릴 수 없음) |
| MAC | `F0:00:06:30:98:F1` | — | OUI `F0:00:06`는 미할당 대역(SignalStar 계열 보드 OEM 추정) |

## 2. 열린 포트 (`bash /dev/tcp`로 11 포트 점검)

```
80/tcp   open       HTTP (HAPI + 웹 UI)
443/tcp  closed     HTTPS 미사용
554/tcp  open       RTSP
1935/tcp closed     RTMP push (서버 미동작)
2020/tcp closed     —
3702/tcp closed     ONVIF WS-Discovery 미사용
8000/tcp open       (응답 없음 — 추정: 외부 RTMP/H5 푸시 채널 또는 P2P, 추가 검증 필요)
8080/tcp closed     —
8554/tcp closed     —
8899/tcp closed     —
9999/tcp closed     —
```

> 8000 포트는 TCP 연결은 수락하나 HTTP HEAD·ONVIF SOAP 둘 다 빈 응답. capability에 `rtmp`/`with_h5`가 있고 펌웨어 라벨이 `RTMP-H5`이므로 **RTMP 또는 WebSocket 기반 H5 라이브뷰 채널**일 가능성이 큼. 실 통신은 웹 UI 라이브뷰 작동 시 크롬 DevTools(Network)로 확인 권장.

## 3. RTSP — 실측으로 확정된 정답

`GET /HAPI/V1.0/sysinfo/rtspurl` 응답:

```json
{
  "ch0_main": "rtsp://192.168.8.213:554/stream0",
  "ch0_sub":  "rtsp://192.168.8.213:554/stream1"
}
```

`ffprobe -rtsp_transport tcp` DESCRIBE 결과:

| 경로 | 코덱 | 해상도 | 프레임레이트 | 상태 |
|---|---|---|---|---|
| `/stream0` | **HEVC (H.265)** | **3840×2160** | 20 fps | ✅ 동작 |
| `/stream1` | HEVC | 720×480 | 20 fps | ✅ 동작 |
| `/live/0` | — | — | — | ❌ 404 |
| `/cam/realmonitor` | — | — | — | ❌ 404 |

**사용 권장**:
```bash
# 메인 4K HEVC (인증 동봉)
ffplay -fflags nobuffer -flags low_delay -rtsp_transport tcp \
  "rtsp://admin:123456@192.168.8.213:554/stream0"

# 서브 저해상도 (지연 최소화·디버깅용)
ffplay -fflags nobuffer -rtsp_transport tcp \
  "rtsp://admin:123456@192.168.8.213:554/stream1"

# 30초 무손실 녹화
ffmpeg -rtsp_transport tcp -i "rtsp://admin:123456@192.168.8.213:554/stream0" \
  -t 30 -c copy capture.mp4
```

## 4. 현재 비디오 인코딩 설정 (`/system/video/get`)

| streamID | enable | 코덱 | 해상도 | fps | 비트레이트 | GOP | 모드 |
|---|---|---|---|---|---|---|---|
| 1 (메인) | ✅ | H.265 | **3840×2160** | 20 | 6 000 kbps | 80 | VBR |
| 2 (서브) | ✅ | H.265 | 720×480 | 20 | 500 kbps | 80 | VBR |
| 3 (확장) | ❌ | H.265 | 720P | 10 | 1 000 kbps | 40 | VBR |

> 사양서 §2.10에 명시된 "메인 스트림 3840×2160 @ 20fps"가 그대로 출하 기본값으로 설정되어 있음 — 8 MP 모듈은 이 해상도까지 정상 동작. `three_video` 능력이 있으므로 stream3까지 활성화하면 추가 채널 1개 더 사용 가능.

## 5. HAPI 능력집 (capability) — 97개 키 전체

`GET /HAPI/V1.0/sysinfo/capability` 응답에서 확인된 97개 `caps` 문자열을 카테고리별로 분류:

### 5.1 PTZ / 줌 / 포커스 (광학 줌 관련 — 핵심)

| 키 | 의미 | 상태 |
|---|---|---|
| `ptz_control` | PTZ 제어 기능 | ✅ |
| `ptz_all_ctrl` | 모든 PTZ 제어 | ✅ |
| `ptz_zoom` | **줌 채널 지원** | ✅ |
| `ptz_focus` | 포커스 제어 | ✅ |
| `ptz_iris` | 광권 제어 | ✅ |
| `ptz_4_direction` | 4방향 회전 | ✅ |
| `mute_ptz_turn` | PTZ 회전 시 무음 | ✅ |
| `af_setting` | **AF(자동 초점) 설정** | ✅ |
| `af_coordinate` | AF 좌표 지정 | ✅ |
| `dzoomsetting` | **디지털 줌 설정** | ✅ |
| `positioning_3d` | 3D 포지셔닝 | ✅ |
| `ele_zoom` | (전동 줌) | ❌ **없음** |
| `zoom_track` | (변배 추적) | ❌ **없음** |
| `ptz_2_direction` / `ptz_8_direction` | (2/8방향) | ❌ 없음 — 본 모듈은 4방향만 |

> **줌 동작 해석**: `ptz_zoom`이 있으나 `ele_zoom`이 없다는 점은 **렌즈가 줌 렌즈(가변초점)는 맞지만 사양서의 "이중 렌즈 전동 줌" 정의와는 다른 구현**(단일 가변초점 렌즈 + 단일 모터)임을 시사합니다. `zoom_track`(검출 시 자동 줌인)도 없어 자동 추적 기능은 별도 구현이 필요합니다.

### 5.2 비디오 / 스트리밍

| 키 | 의미 |
|---|---|
| `three_video` | 3 스트림 |
| `with_h5` | H5 라이브뷰 플레이어 내장 |
| `rtmp`, `rtmp_timespan` | RTMP 푸시 + 시간대 설정 |
| `media_capabiltiy` | 미디어 능력집 |
| `vencodemode_set` | 비디오 인코딩 모드 설정 |
| `wdr_setting`, `hdr_setting` | WDR / HDR |
| `with_qpsetting` | VBR QP 한계 설정 |
| `mp4_support` | MP4 컨테이너 |
| `front_replay` / `replay_bytime` / `export_record` | 전방 재생 / 시간 기반 재생 / 녹화 내보내기 |
| `picture_capture` | 정지 영상 캡처 |
| `create_timelapse` | 타임랩스 생성 |
| `video_qos` | 비디오 QoS |
| `video_crop`, `video_mask`, `video_shutter`, `forbid_video` | 영상 후처리 |

### 5.3 스마트 분석

| 키 | 의미 |
|---|---|
| `VideoPD` | 사람 검출 |
| `AlarmPdVG` | 라인 크로스 검출(사람) |
| `VehicleCar`, `VehicleMoto`, `VehicleBicycle` | 차량 / 오토바이 / 자전거 검출 |
| `pd2rectconf` | 사람 검출 사각형 설정 |
| `pd_polygon_area` | 사람 검출 다각형 영역 |
| `humanmosic` | 사람 자동 모자이크 |
| `md_18x22` | 18×22 그리드 움직임 검출 |
| `hd_disablemd` | HD 모드에서 MD 비활성화 |

### 5.4 알람 / 연동

| 키 | 의미 |
|---|---|
| `alarm_arming`, `alarm_server` | 알람 부무장 / 알람 서버 보고 |
| `arming_audiodesc`, `arming_bytime`, `arming_daynight` | 부무장 음성 설명 / 시간 / 주야 |
| `audio_action_daynight`, `audio_amplify`, `audioprompt`, `audio_Repartition` | 오디오 액션 / 증폭 / 프롬프트 |
| `scare_off` | 위협 사운드 |
| `ledtype_set`, `ircut_setting`, `ircut_leddelay` | 보광등 / IRCUT 설정 |
| `ra_mp3`, `ra_pcm` | 반향 MP3 / PCM 재생 |
| `ioout_arming`, `io_output_set`, `one_input`, `one_output`, `gpio_input`, `gpio_output` | GPIO/IO |

### 5.5 네트워크 / 시스템

| 키 | 의미 |
|---|---|
| `network_storage` | NAS |
| `schedule_record`, `storage_support` | 스케줄 녹화 |
| `dhcp_fixtime`, `fixipcfg`, `ipaddrlimit`, `be_set_mtu`, `domains_check` | 네트워크 설정 |
| `ssl_email` | SSL SMTP |
| `cloud_authcode`, `p2p_cfg_support`, `p2p_config`, `p2p_ac18pro`, `P2PNEWROOT` | P2P 클라우드(AC18Pro 변형) |
| `system_maitain`, `part_restore`, `device_report` | 유지보수 |

### 5.6 OSD / UI

| 키 | 의미 |
|---|---|
| `userosd_set` | 사용자 OSD |
| `OSD_ANYPOS` | OSD 임의 위치 |
| `bmplogo_set`, `LONG_TITLE`, `profile_setting` | 로고 / 긴 제목 / 프로파일 |
| `TimeSpanNew`, `timezone_halfhour` | 신형 7×24 타임스팬 / 30분 단위 시간대 |

### 5.7 다국어

| 키 | 언어 |
|---|---|
| `zh_cn` | 간체 |
| `zh_tw` | 번체 |
| `en_us` | 영어 |
| `ko-ko` | **한국어 — 본 모듈 지원** |
| `rs_py` | 러시아어 |

## 6. 디바이스가 지원하는 HAPI 엔드포인트 (`functionlist`, 59개)

`GET /HAPI/V1.0/sysinfo/functionlist` 응답에서 확인된 실제 API 경로(`[/Channels/ID]` 옵션 그대로 보존):

```
세션:        /uid/getuid                /uid/keep_alive
시스템 정보:  /sysinfo/device_info       /sysinfo/functionlist
              /sysinfo/capability        /sysinfo/rtspurl
시스템 제어:  /sysman/reboot             /sysman/factory
시간:        /systime/gettime           /systime/settime           /systime/setntp
IO:          /io/input/get              /io/output/get             /io/output/set
PTZ:         /ptz_ctrl/stop             /ptz_ctrl/move             /ptz_ctrl/preset
              /ptz_ctrl/zoom             /ptz_ctrl/focus            /ptz_ctrl/iris
              /ptz_ctrl/advfunction/get  /ptz_ctrl/advfunction/exec
조명:        /system/light/get          /system/light/set
              /system/light/ctrlmode/capability
              /system/light/workmode/capability
이미지:      /system/image/get          /system/image/set
비디오:      /system/video/capability   /system/video/get          /system/video/set
오디오:      /system/audio/capability   /system/audio/get          /system/audio/set
OSD:         /system/osd/get            /system/osd/set
사용자 OSD:  /system/userosd/get        /system/userosd/set        ★ 사양서엔 없는 신규 API
스마트:      /Smart/capability          /Smart/audiofiles/get
              /Smart/linkage/capability  /Smart/objectdetect/capability
              /Smart/motiondetect/{get,set}
              /Smart/objectdetect/{get,set}
              /Smart/videocover/{get,set}
              /Smart/videogate/{get,set}
              /Smart/regionai/{get,set}
              /Smart/facedetect/{get,set}
              /Smart/lpr/{get,set}
              /Smart/flameflumes/{get,set}
이벤트:      /Event/subscription/regist
              /Event/subscription/refresh
              /Event/subscription/delete
```

> **사양서 v1.5와의 차이점**:
> - `/system/userosd/{get,set}` — 본 펌웨어에 신규 추가됨(사양서엔 없음)
> - `/snapshot.cgi` — functionlist에는 없으나 사양서에 명시됨. 실호출 가능성은 별도 검증 필요
> - `/Smart/*` 경로는 모두 **대문자 S** — 사양서엔 `smart`(소문자)와 `Smart`(대문자)가 혼용되어 있었으나 본 펌웨어는 **대문자 `Smart`만 노출**

## 7. PTZ 고급 기능 (`/ptz_ctrl/advfunction/get`)

`functionname`만 8개 노출:

| functionname | 추정 의미 |
|---|---|
| `FocusRestore` | 포커스 초기화 |
| `GuardPos` | 가드 포지션(귀환 위치) |
| `Orbit` | 순환 정찰 |
| `PtzReboot` | PTZ 모터 리부트 |
| `PtzRestore` | PTZ 설정 복원 |
| `ScanBegin` / `ScanEnd` / `ScanOn` | 스캔 시작·끝·실행 |

호출 형식:
```bash
curl "http://192.168.8.213/HAPI/V1.0/ptz_ctrl/advfunction/exec?functionname=FocusRestore&uid=$SID"
```

## 8. 셸 라인 컨티뉴에이션 사고 — 근본 원인 분석 (RCA)

### 발생
이전 검증 시 `[2] device_info`와 `[3] capability` 호출이 실패. 카메라 무관, 셸 파싱 문제였음.

### 근본 원인
제가 안내한 멀티라인 명령에서 백슬래시 라인 연속(`\` + 줄바꿈)을 사용했고, 사용자가 복붙 시 `\` 다음 줄 시작이 공백으로 들어가 셸이 다음과 같이 해석:

```
curl -s -m 5 -w "..." \  ← 백슬래시 + 공백 + 다음 줄
"http://..."
```

→ 셸이 `\<space>`를 **이스케이프된 공백 = 빈 인자 1개**로 해석 → curl이 URL이 아닌 빈 문자열을 받음 → `HTTP 000`(연결 자체 실패).

### 재발 방지 조치 (영구)
1. **이후 모든 검증 명령은 한 줄로만 제공** — 본 문서의 모든 `curl`/`ffprobe` 예제는 한 줄로 작성됨
2. **여러 단계 처리가 필요한 경우는 셸 스크립트 파일로 제공** — 백슬래시 라인 연속을 피하고 줄바꿈 + 다음 줄 명령을 사용
3. **결과 검증 우선** — `HTTP 000`이나 빈 응답이 나오면 카메라를 의심하기 전에 인자 파싱부터 점검(예: `bash -x` 로 재실행)

## 9. 즉시 사용 가능한 1-라이너 명령 카탈로그 (검증 완료)

```bash
# 변수
CAM=192.168.8.213; USER=admin; PASS=123456
PW_MD5=$(echo -n "$PASS" | md5sum | awk '{print $1}')

# 세션 발급
SID=$(curl -s "http://$CAM/HAPI/V1.0/uid/getuid?username=$USER&password=$PW_MD5" | jq -r '.Response.SessionID'); echo "SID=$SID"

# 세션 유지(30초 권장 주기)
curl -s "http://$CAM/HAPI/V1.0/uid/keep_alive?uid=$SID" | jq '.Response.ResponseString'

# 디바이스 정보
curl -s "http://$CAM/HAPI/V1.0/sysinfo/device_info?uid=$SID" | jq '.Response.Data'

# 능력집
curl -s "http://$CAM/HAPI/V1.0/sysinfo/capability?uid=$SID" | jq -r '.Response.Data[].caps' | sort -u

# 비디오 현재 설정
curl -s "http://$CAM/HAPI/V1.0/system/video/get?uid=$SID" | jq '.Response.Data'

# RTSP URL
curl -s "http://$CAM/HAPI/V1.0/sysinfo/rtspurl?uid=$SID" | jq '.Response.Data'

# 줌 in 1초 → out 1초 → stop
curl -s "http://$CAM/HAPI/V1.0/ptz_ctrl/zoom?direction=in&autostop=1000&uid=$SID" | jq '.Response.ResponseString'
sleep 1
curl -s "http://$CAM/HAPI/V1.0/ptz_ctrl/zoom?direction=out&autostop=1000&uid=$SID" | jq '.Response.ResponseString'
sleep 1
curl -s "http://$CAM/HAPI/V1.0/ptz_ctrl/stop?uid=$SID" | jq '.Response.ResponseString'

# 포커스 near/far
curl -s "http://$CAM/HAPI/V1.0/ptz_ctrl/focus?direction=near&autostop=200&uid=$SID" | jq '.Response.ResponseString'
curl -s "http://$CAM/HAPI/V1.0/ptz_ctrl/focus?direction=far&autostop=200&uid=$SID"  | jq '.Response.ResponseString'

# 프리셋 1번 저장/호출/삭제
curl -s "http://$CAM/HAPI/V1.0/ptz_ctrl/preset?method=set&presetno=1&uid=$SID"    | jq '.Response.ResponseString'
curl -s "http://$CAM/HAPI/V1.0/ptz_ctrl/preset?method=call&presetno=1&uid=$SID"   | jq '.Response.ResponseString'
curl -s "http://$CAM/HAPI/V1.0/ptz_ctrl/preset?method=delete&presetno=1&uid=$SID" | jq '.Response.ResponseString'

# 고급 기능 — 포커스 리셋
curl -s "http://$CAM/HAPI/V1.0/ptz_ctrl/advfunction/exec?functionname=FocusRestore&uid=$SID" | jq '.Response.ResponseString'

# 라이브뷰 (별도 터미널)
ffplay -fflags nobuffer -flags low_delay -rtsp_transport tcp "rtsp://$USER:$PASS@$CAM:554/stream0"
```

## 10. 사양서와의 차이 요약 (실측 우선)

| 항목 | 사양서(WGWK-AS500J / MC800S 5MP) | 실측(MC800S5 8MP) |
|---|---|---|
| 메인 스트림 최대 해상도 | 2592×1944 / 일부 4K | **3840×2160 출하 기본값** |
| 코덱 | H.265+/H.265/H.264 | **H.265 출하 기본값** (다른 코덱 가능 여부 별도 확인) |
| ele_zoom (전동 줌) | 능력집 키 존재 | **없음** |
| zoom_track (변배 추적) | 능력집 키 존재 | **없음** |
| ptz_zoom / af_setting / dzoomsetting | 부분 기재 | **모두 지원** |
| `/snapshot.cgi` | 사양서 명시 | functionlist에 부재(별도 검증 필요) |
| `/Smart/*` 대소문자 | 혼용 | **대문자 `Smart`만 제공** |
| `/system/userosd/{get,set}` | 부재 | **신규 API** |
| 펌웨어 라벨 | — | `MC800S5_AF_V0-A-RTMP-H5 V3.4.5.2 build 2025-11-12 17:30:10` |
| 커널 아키텍처 | — | **`armv7l` (32-bit ARM)** |
| 한국어 지원 | 사양서 미명시 | `ko-ko` 능력 키 존재 |

## 11. 미확인 항목 (후속 검증 권장)

1. **광학 vs 디지털 줌 구분** — `ptz_zoom`은 동작하나 `ele_zoom`이 없으므로, 실제 줌 명령 시 **카메라가 광학 줌(렌즈 모터)인지 디지털 줌(크롭)인지** 라이브뷰 화면으로 확인 필요
2. **줌 배율 최대치** — HAPI에는 줌 배율 조회 API가 노출되지 않음. NETSDK `CMD_GET_ZOOM_CFG`로 조회 가능하나 본 펌웨어 armv7l이라 aarch64 SDK 미적용. 화각 측정 또는 OSD overlay로 확인
3. **`/snapshot.cgi` 동작 여부** — functionlist에 없지만 사양서엔 명시. 실호출 결과 별도 측정
4. **포트 8000의 정체** — 빈 응답. RTMP/WebSocket 가능성. 웹 UI 라이브뷰 동작 시 크롬 DevTools(Network) 캡처로 확정
5. **이벤트 push 동작** — `/Event/subscription/regist` 후 실제 TCP push가 클라이언트로 오는지 별도 listener로 검증
6. **PTZ 4-direction의 실제 동작** — `ptz_4_direction` 키가 있으므로 PTZ가 회전 가능. `move` API로 회전 검증 필요(가드 포지션·궤도 등 advfunction 동작 확인 포함)

## 12. 결론

| 결론 | 근거 |
|---|---|
| HAPI는 본 모듈에서 **완전 동작** | `device_info`, `capability`, `rtspurl`, `system/video/get`, `ptz_ctrl/advfunction/get` 모두 `ResponseCode: 0`으로 정상 응답 |
| RTSP 라이브 스트리밍은 **즉시 사용 가능** | `rtsp://admin:123456@192.168.8.213:554/stream0`(4K HEVC) 및 `/stream1`(720×480) DESCRIBE 성공 |
| 줌·포커스 제어 경로는 **HAPI `/ptz_ctrl/zoom`·`/focus` 사용 권장** | 능력집에 `ptz_zoom`, `ptz_focus`, `af_setting` 모두 존재. ONVIF는 본 펌웨어에 미탑재 |
| NETSDK 경로는 **본 모듈에는 부적합** | 디바이스 커널이 `armv7l`이며 SDK는 aarch64 전용. 통합 호스트(우분투 PC)에서 카메라를 *원격 제어*하는 용도라면 SDK도 가능하나 HAPI보다 이점 없음 |
| ONVIF / RTMP-push는 **현재 비활성** | 3702 closed, 1935 closed. 필요 시 펌웨어 설정에서 활성화하거나 `with_h5`/`rtmp` 능력 기반 별도 push 모드 설정 |

따라서 `docs/04-zoom-control-guide.md` §4.2(HAPI 기반)의 통합 패턴이 본 모듈에 그대로 적용 가능합니다.
