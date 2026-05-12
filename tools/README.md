# tools/

본 카메라 모듈(MC800S5, 펌웨어 V3.4.5.2)을 위한 유틸리티 모음. 실측 capability(`docs/06-live-probe-result.md`) 기반.

## `zoom_client.py`

HAPI 1.5를 사용한 경량 Python 제어 클라이언트. 라이브러리로도, CLI로도 사용 가능.

### 요구 사항

- Python 3.10 이상
- `requests` (Ubuntu 24.04 기본 제공 또는 `pip install requests`)

### CLI 사용법

```bash
# 비파괴 자가 점검 — 카메라를 움직이지 않음
python3 tools/zoom_client.py selftest

# 요약 정보 JSON 출력
python3 tools/zoom_client.py info

# 전체 capability 97개 출력
python3 tools/zoom_client.py caps

# RTSP URL + ffplay/ffmpeg 명령 자동 생성
python3 tools/zoom_client.py rtsp

# 줌 in 500ms
python3 tools/zoom_client.py zoom in --autostop 500

# 줌 out 500ms
python3 tools/zoom_client.py zoom out --autostop 500

# 모든 PTZ 정지
python3 tools/zoom_client.py stop

# 포커스 near 200ms
python3 tools/zoom_client.py focus near --autostop 200

# 4방향 PTZ 회전 (속도 5, 500ms)
python3 tools/zoom_client.py move left --speed 5 --autostop 500

# 프리셋 1번 저장/호출/삭제
python3 tools/zoom_client.py preset set 1
python3 tools/zoom_client.py preset call 1
python3 tools/zoom_client.py preset delete 1

# 줌 in/out 1초 데모 (라이브뷰와 함께 화각 변화 관찰용)
python3 tools/zoom_client.py zoom-demo
```

다른 카메라/계정을 쓸 때:

```bash
python3 tools/zoom_client.py --host 10.0.0.50 --user operator --password mypw info
```

### 라이브러리 사용법

```python
from tools.zoom_client import CameraClient

with CameraClient("192.168.8.101") as cam:
    info = cam.device_info()
    print(info["device_type"])  # 'MC800S5'

    # 줌 500ms in
    cam.zoom("in", autostop_ms=500)

    # RTSP URL 확보
    urls = cam.rtsp_urls()
    print(urls["ch0_main"])      # 'rtsp://192.168.8.101:554/stream0'
```

`with` 블록을 나가면 자동으로 logout + keep_alive 스레드 종료.

### 동작 원리

1. `login()` 호출 시 `/HAPI/V1.0/uid/getuid`로 Session ID 발급
2. 30초마다 백그라운드 스레드가 `/uid/keep_alive` 호출 (HAPI 1.5의 60초 만료 회피)
3. 모든 제어 호출은 `?uid=<SID>` 인증 사용 (평문 비밀번호 노출 최소화)
4. `logout()` 또는 컨텍스트 매니저 종료 시 keep_alive 스레드 정상 종료

### 라이브뷰와 함께 사용

별도 터미널에서:

```bash
python3 tools/zoom_client.py rtsp        # ffplay 명령 자동 출력 → 복사 실행
```

또는 직접:

```bash
ffplay -fflags nobuffer -flags low_delay -rtsp_transport tcp \
  "rtsp://admin:123456@192.168.8.101:554/stream0"
```

그 다음 다른 터미널에서 `zoom-demo` 실행하면 화각 변화를 실시간 관찰 가능.

### 검증된 환경

- Ubuntu 24.04 + Python 3.12 + requests 2.31.0
- 카메라 펌웨어 `MC800S5_AF_V0-A-RTMP-H5 V3.4.5.2 build 2025-11-12`
- HAPI 1.5 사양 준수

---

## `scf_client.py`

웹 UI가 사용하는 **비공식 SOAP 채널(SCF)** 클라이언트. HAPI에 노출되지 않는 기능 — 줌 배율 read, WDR/셔터/DNR/HLC/게인/화이트밸런스 등 모든 고급 이미지 설정 — 을 제공합니다. 명세는 `docs/07-scf-api.md`.

### 토큰 발급 (초기 1회)

SCF 인증은 HAPI와 별개로 16-hex DES 토큰을 사용합니다. 자동 발급은 미구현이므로 한 번만 수동 추출이 필요합니다.

1. 크롬으로 `http://192.168.8.101/` 로그인
2. **F12 → Network** 탭, **Preserve log** 체크
3. 설정 페이지 진입 또는 PTZ 버튼 한 번 클릭
4. `setPTZCmd`, `getPtzConfig` 같은 POST 요청 선택 → **Payload** 또는 **Request** 탭
5. `<userid>...</userid><passwd>...</passwd>` 16-hex 두 값을 추출
6. 환경변수로 보관:
   ```bash
   export SCF_USERID=52851dbd7918bbae
   export SCF_PASSWD=a17faccd02661e4c
   ```

> 한 번 발급된 토큰은 장수명입니다(시간 경과 후에도 동작). 재부팅·펌웨어 업데이트 후에는 재캡처 필요.

### CLI 사용법

```bash
# 비파괴 자가 점검 — 줌·AF·이미지·프리셋 4종 검증
python3 tools/scf_client.py selftest

# 줌 배율 read
python3 tools/scf_client.py get-zoom
#   current: 1.9x
#   max:     10.0x

# 줌 in 500ms (zoomtele → stop)
python3 tools/scf_client.py zoom-step in --ms 500

# 폐루프 절대 배율 도달 (목표 2.5x, ±0.1 허용)
python3 tools/scf_client.py goto-zoom 2.5 --tolerance 0.1 --step-ms 200

# 포커스 near 300ms
python3 tools/scf_client.py focus near --ms 300

# 모든 이미지 설정 read
python3 tools/scf_client.py get-image

# 특정 필드만
python3 tools/scf_client.py get-image Brightness WDRMode shutter_mode

# 이미지 설정 변경 (밝기 128→200, WDR mode 0→1)
python3 tools/scf_client.py set-image Brightness=200 WDRMode=1

# AF 상태 read
python3 tools/scf_client.py get-af

# 프리셋 목록
python3 tools/scf_client.py preset-list

# 원시 XML 덤프 (디버깅용)
python3 tools/scf_client.py dump-ptz
python3 tools/scf_client.py dump-media
```

### 라이브러리 사용법

```python
from tools.scf_client import SCFClient, goto_zoom

# 토큰은 SCF_USERID / SCF_PASSWD 환경변수에서 자동 로드
with SCFClient(host="192.168.8.101") as scf:
    # 줌 배율 실시간 read
    zoom = scf.get_zoom()
    print(zoom)  # {'current': 1.9, 'max': 10.0}

    # 절대 배율 도달
    result = goto_zoom(scf, target=3.0, tolerance=0.1)
    print(result)  # {'reached': True, 'final': 2.95, 'iterations': 4, 'history': [...]}

    # 이미지 설정 부분 업데이트
    updated = scf.set_image(Brightness=200, WDRMode=1, shutter_mode_night=2)

    # AF 활성 여부 확인
    af = scf.get_af()
    if af["enable"]:
        print("AF on")
```

### Capture 필드 카탈로그

`docs/07-scf-api.md` §4.3 표 참고. 주요 항목:

| 키 | 의미 |
|---|---|
| `Brightness`, `Contrast`, `Saturation`, `Sharpness` | 기본 이미지 (0~255) |
| `WDRMode`, `WDRValue` | 와이드 다이내믹 레인지 |
| `shutter_mode`, `shutter_mode_night`, `shutter_speed_day`, `shutter_speed_night` | 주·야 셔터 |
| `TNF`, `SNF` | 3D / 2D 노이즈 감소 |
| `BackLight`, `HLC` | 역광 / 강한 빛 보정 |
| `bManualGain`, `gainValue` | 게인 |
| `WB_RGB` | 화이트밸런스 |
| `DfrogFlag`, `DfrogValue` | 안개 제거 |
| `forct_antiflicker` | 전원 주파수 (안티플리커) |
| `HFlip`, `VFlip`, `rotate` | 화면 반전·회전 |
| `IrcutMode`, `IrcutNightStartTime`/`EndTime` | IRCUT 주·야 |

### HAPI와의 사용 분리

| 작업 | 권장 도구 |
|---|---|
| 줌 in/out (시간 기반) | `zoom_client.py zoom in --autostop 500` (HAPI) |
| 줌 절대값 도달 | **`scf_client.py goto-zoom 2.5`** (SCF + 폐루프) |
| 줌 배율 read | **`scf_client.py get-zoom`** (SCF만 가능) |
| 포커스 near/far | `zoom_client.py focus` (HAPI, autostop 지원) 또는 `scf_client.py focus` |
| 프리셋 set/call | `zoom_client.py preset set 1` (HAPI) |
| 스냅샷 JPEG | `curl http://CAM/HAPI/V1.0/snapshot.cgi?...` (HAPI, 720×480) |
| 라이브 스트리밍 | `ffplay rtsp://...` (RTSP 직접) |
| 밝기·대비·채도·샤프니스 | 어느 쪽이든 가능 |
| **WDR·셔터·DNR·HLC·게인·WB·Defog·안티플리커** | **`scf_client.py set-image`** (SCF만 가능) |

### 검증된 환경

- Ubuntu 24.04 + Python 3.12 + requests 2.31.0
- 카메라 펌웨어 `V3.4.5.2 build 2025-11-12`
- 검증 일자: 2026-05-12, `selftest` 정상 통과 (1.9x 현재 / 10.0x 최대, AF on)
