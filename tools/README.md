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

with CameraClient("192.168.8.213") as cam:
    info = cam.device_info()
    print(info["device_type"])  # 'MC800S5'

    # 줌 500ms in
    cam.zoom("in", autostop_ms=500)

    # RTSP URL 확보
    urls = cam.rtsp_urls()
    print(urls["ch0_main"])      # 'rtsp://192.168.8.213:554/stream0'
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
  "rtsp://admin:123456@192.168.8.213:554/stream0"
```

그 다음 다른 터미널에서 `zoom-demo` 실행하면 화각 변화를 실시간 관찰 가능.

### 검증된 환경

- Ubuntu 24.04 + Python 3.12 + requests 2.31.0
- 카메라 펌웨어 `MC800S5_AF_V0-A-RTMP-H5 V3.4.5.2 build 2025-11-12`
- HAPI 1.5 사양 준수
