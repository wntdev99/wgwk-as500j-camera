# 09. wgwk_camera 라이브러리 API 가이드

본 문서는 `src/wgwk_camera/` 패키지의 공개 API 사용법을 정리한 가이드입니다. 외부 프로젝트(로봇 시스템 등)에서 가져다 쓸 수 있도록 설계되었습니다.

## 1. 설치

본 레포지토리를 클론한 뒤 외부 프로젝트의 virtualenv에서 `editable` 설치:

```bash
# 비디오 기능 빼고 (control + image만)
pip install -e /path/to/wgwk-as500j-camera

# 비디오 포함 (opencv-python 설치)
pip install -e "/path/to/wgwk-as500j-camera[video]"
```

요구 사항:
- Python 3.10+
- `requests >= 2.25` (필수)
- `opencv-python >= 4.5` (선택, video 사용 시)

## 2. 설계 원칙

| 원칙 | 의미 |
|---|---|
| 인스턴스 생성 = 부작용 없음 | `Camera(host)` 만으로는 카메라 설정이 바뀌지 않음 |
| 런타임 메서드는 직접 노출 | `cam.zoom_in()`, `cam.set_image()` 등 |
| 카메라 영구 변경은 `cam.admin.*` 네임스페이스 | 부주의 호출 방지 |
| `apply_*` 메서드는 `dry_run=True` 기본 | 변경 사항 확인 후 명시적 `dry_run=False`로 적용 |
| 선택적 의존성 | OpenCV 미설치 시에도 control / image / RTSP URL은 정상 |

## 3. 빠른 시작

```python
from wgwk_camera import Camera

with Camera("192.168.8.101") as cam:
    # 런타임 제어
    cam.zoom_in(500)
    cam.zoom_out(500)
    cam.snapshot("frame.jpg")
    cam.preset_call(1)

    # 비디오 캡처 (OpenCV 필요)
    with cam.video_main().opencv() as cap:
        ok, frame = cap.read()
```

## 4. 컴포넌트 구조

```
wgwk_camera
├── Camera                  ← 통합 Facade (대부분 이거만 쓰면 됨)
│   ├── .control  → ControlClient    (HAPI, raw 접근)
│   ├── .image    → ImageClient      (SCF, raw 접근)
│   └── .admin    → AdminFacade      (설정 변경 메서드)
├── VideoStream             ← RTSP 캡처 (cv2/gst/ffmpeg)
├── EncodingProfile         ← 프로필 데이터 클래스
├── StreamSpec              ← 스트림 1개 명세
├── 프로필 상수
│   ├── PRECISION_PROFILE
│   ├── ROBOT_VISION_PROFILE
│   ├── BANDWIDTH_SAVE_PROFILE
│   └── FAST_TRACKING_PROFILE
└── 예외
    ├── CameraError (베이스)
    ├── AuthError
    ├── EncodingError
    └── StreamError
```

## 5. `Camera` API 카탈로그

### 생성자

```python
Camera(host="192.168.8.101",
       username="admin", password="123456",
       *, port=80,
       scf_userid=None, scf_passwd=None,   # 없으면 env SCF_USERID/SCF_PASSWD
       auto_login=True,
       preflight=True,            # 생성 시 TCP 도달성 확인
       preflight_timeout=2.0)
```

**preflight 동작**:
- `preflight=True` (기본) — 생성 즉시 `socket.create_connection(host, port, timeout)`으로 도달성 확인. 실패 시 `CameraError` raise (전원·네트워크 즉시 진단)
- `preflight=False` — 도달성 확인 생략. 첫 메서드 호출 시점에 오류 발생 (lazy)
- `cam.is_reachable(timeout=2.0)` — 런타임에 다시 확인 (예외 없이 bool)
- `check_reachable(host, port, timeout)` — Camera 인스턴스 없이 단독 호출 가능 (`from wgwk_camera import check_reachable`)

### 런타임 — 줌 / 포커스 / 회전 / 프리셋

| 메서드 | 설명 |
|---|---|
| `cam.zoom_in(ms=500)` | 줌 in N ms |
| `cam.zoom_out(ms=500)` | 줌 out |
| `cam.zoom_stop()` | 즉시 정지 (모든 PTZ) |
| `cam.focus_near(ms=200)` | 포커스 근거리 |
| `cam.focus_far(ms=200)` | 포커스 원거리 |
| `cam.focus_restore()` | AF 기본 위치 복귀 |
| `cam.move(dir, speed=5, ms=500)` | 회전 (`left`/`right`/`up`/`down`/대각선 8방향) |
| `cam.stop()` | 모든 PTZ 정지 |
| `cam.preset_save(n)` | 현재 위치를 프리셋 n에 저장 |
| `cam.preset_call(n)` | 프리셋 n으로 이동 |
| `cam.preset_delete(n)` | 프리셋 n 삭제 |

### 런타임 — 스냅샷 / 이미지 설정

| 메서드 | 설명 |
|---|---|
| `cam.snapshot(path=None) -> bytes` | 720×480 JPEG. path 지정 시 파일 저장 |
| `cam.get_image() -> dict` | 현재 Capture 속성 (SCF 토큰 필요) |
| `cam.set_image(**fields) -> dict` | 부분 업데이트 (예: `WDRMode=1, shutter_mode_night=2`) |

### 런타임 — 비디오 스트림

| 메서드 | 반환 |
|---|---|
| `cam.video_main(transport="udp")` | `VideoStream` (메인 4K/1080P) |
| `cam.video_sub(transport="udp")` | `VideoStream` (서브 720P/D1) |
| `cam.video(kind, transport="udp")` | `VideoStream` (`main`/`sub`/`third`) |

`VideoStream` 사용:

```python
vs = cam.video_main()

# OpenCV (저지연)
with vs.opencv() as cap:
    ok, frame = cap.read()

# GStreamer 파이프라인 문자열만 받기 (ROS gscam2 등)
gst_str = vs.gst_pipeline(codec="h264", appsink=True)

# RTSP URL 직접 (인증 포함)
url = vs.url
url_no_auth = vs.url_no_auth

# ffmpeg로 N초 녹화
vs.ffmpeg_record("/tmp/clip.mp4", duration_sec=30)

# RTSP 1프레임 추출 (snapshot.cgi 720×480 한계 우회, 메인이면 4K)
vs.ffmpeg_grab_frame("/tmp/frame.jpg")
```

### 상태 조회 (read-only, 부작용 없음)

| 메서드 | 설명 |
|---|---|
| `cam.info()` | SN, device_type, model, MAC, kernel, fsversion |
| `cam.capabilities() -> list[str]` | 능력집 키 정렬 리스트 |
| `cam.function_list() -> list[str]` | 지원 HAPI 엔드포인트 |
| `cam.rtsp_urls() -> dict` | `{'ch0_main': '...', 'ch0_sub': '...'}` |
| `cam.get_video_config() -> list[dict]` | 현재 인코딩 (각 stream) |
| `cam.get_osd_enabled() -> bool` | OSD 전체 토글 상태 |
| `cam.get_zoom_setpoint() -> dict` | SCF DzoomConfig {setpoint, max} |
| `cam.get_af() -> dict` | AF enable/type/coordinate |

### `cam.admin` — 카메라 설정 변경 (명시적 호출만)

| 메서드 | 설명 |
|---|---|
| `cam.admin.apply_encoding_profile(profile, dry_run=True)` | 인코딩 변경. dry_run=True면 diff만 반환 |
| `cam.admin.apply_osd(enabled, dry_run=True)` | OSD 토글 |
| `cam.admin.reboot(confirm=True)` | 재부팅 (confirm 필요). 30~60s 다운타임 |

> 공장 초기화는 라이브러리에 노출하지 않습니다. 필요 시 직접 `GET /HAPI/V1.0/sysman/factory` 호출.

## 6. `EncodingProfile` 직접 만들기

사전 정의 외에 커스텀 프로필도 가능:

```python
from wgwk_camera import EncodingProfile, StreamSpec, Camera

CUSTOM = EncodingProfile(
    name="my_setup",
    main =StreamSpec(True,  "H264", "1080P", 30, 4000, 30),
    sub  =StreamSpec(False, "H264", "720X480", 15, 500, 30),
    third=StreamSpec(False, "H264", "720P",  10,  300, 10),
    osd_enabled=False,
    description="개별 사이트 전용",
)

cam = Camera()
print(cam.admin.apply_encoding_profile(CUSTOM))           # dry-run
cam.admin.apply_encoding_profile(CUSTOM, dry_run=False)   # 실제 적용
```

## 7. `ImageClient.set_image()` 필드 카탈로그

전체 47개 속성은 `wgwk_camera.CAPTURE_FIELDS` 또는 `docs/07-scf-api.md` §4.3 참조. 자주 쓰는 항목:

| 필드 | 의미 |
|---|---|
| `Brightness`, `Contrast`, `Saturation`, `Sharpness` | 기본 화질 (0~255, 128 기본) |
| `WDRMode`, `WDRValue` | 와이드 다이내믹 레인지 |
| `shutter_mode`, `shutter_mode_night`, `shutter_speed_day`, `shutter_speed_night` | 주·야 셔터 |
| `TNF`, `SNF` | 3D / 2D 노이즈 감소 |
| `HLC`, `BackLight` | 강한 빛 보정 / 역광 보정 |
| `bManualGain`, `gainValue` | 수동 게인 활성 / 값 |
| `WB_RGB` | 화이트밸런스 |
| `DfrogFlag`, `DfrogValue` | 안개 제거 |
| `forct_antiflicker` | 전원 주파수 (안티플리커) |
| `HFlip`, `VFlip`, `rotate` | 반전·회전 |
| `IrcutMode`, `IrcutNightStartTime`/`EndTime` | IRCUT 주·야 |

런타임 환경 변화 패턴:

```python
# 야간 진입
cam.set_image(shutter_mode_night=2, bManualGain=1, gainValue=80)

# 역광 영역 (창가)
cam.set_image(WDRMode=1, WDRValue=180, BackLight=1)

# 동작 후 원복
cam.set_image(WDRMode=0, BackLight=0, bManualGain=0)
```

## 8. ROS 2 통합 패턴 (스케치)

```python
# my_robot/camera_node.py
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image, CompressedImage
from cv_bridge import CvBridge

from wgwk_camera import Camera

class CameraNode(Node):
    def __init__(self):
        super().__init__("wgwk_camera")
        self.declare_parameter("host", "192.168.8.101")
        self.cam = Camera(self.get_parameter("host").value)
        self.bridge = CvBridge()
        self.pub_main = self.create_publisher(Image, "~/image_raw", 10)
        self.create_timer(1/30.0, self._tick)
        self._cap = self.cam.video_main(transport="udp").opencv().__enter__()

    def _tick(self):
        ok, frame = self._cap.read()
        if not ok:
            return
        msg = self.bridge.cv2_to_imgmsg(frame, encoding="bgr8")
        msg.header.stamp = self.get_clock().now().to_msg()
        self.pub_main.publish(msg)

def main():
    rclpy.init()
    rclpy.spin(CameraNode())
```

## 9. 예외 처리

```python
from wgwk_camera import Camera, CameraError, AuthError, StreamError

try:
    with Camera("192.168.8.101") as cam:
        cam.zoom_in(500)
except AuthError as e:
    print(f"인증 실패: {e}")
except StreamError as e:
    print(f"비디오/스냅샷 오류: {e}")
except CameraError as e:
    print(f"일반 카메라 오류: {e}")
```

## 10. 안전장치 요약

| 상황 | 라이브러리 동작 |
|---|---|
| `Camera(host)` 호출 | HAPI 로그인만. 카메라 설정 변경 없음 |
| `cam.zoom_in()`, `cam.snapshot()` 등 | 일시적 PTZ 동작 또는 read-only |
| `cam.set_image(WDRMode=1)` | 이미지 설정이 영구 저장됨 (의도된 런타임 변경) |
| `cam.admin.apply_encoding_profile(P)` | **기본 dry_run=True** — diff만 반환, 변경 없음 |
| `cam.admin.apply_encoding_profile(P, dry_run=False)` | 카메라 인코딩 영구 변경 (의도된 admin 작업) |
| `cam.admin.reboot()` | `confirm=True` 필요. 없으면 raise |
| 공장 초기화 | 미구현. 라이브러리에 노출하지 않음 |

## 11. 검증된 환경

- Ubuntu 24.04 + Python 3.12 + requests 2.31
- 카메라 펌웨어 `V3.4.5.2 build 2025-11-12`
- 검증 절차: `docs/06-live-probe-result.md`, `docs/07-scf-api.md`
