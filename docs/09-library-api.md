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
| `cam.zoom_level -> float \| None` | SW-side 추정 줌 배율 (1.0=wide, max=tele). 미앵커면 `None`. 자세한 한계는 §12 |
| `cam.anchor_wide(hard_limit_ms=15000)` | wide hard-limit 도달 + 추정을 1.0으로 고정 (~15s 소요) |
| `cam.anchor_tele(hard_limit_ms=15000)` | tele hard-limit 도달 + 추정을 max로 고정 |
| `cam.set_zoom_estimate(x)` | 외부 정보로 추정값 직접 주입 |
| `cam.preset_save(n)` | 현재 위치를 프리셋 n에 저장 ⚠ |
| `cam.preset_call(n)` | 프리셋 n으로 이동 ⚠ |
| `cam.preset_delete(n)` | 프리셋 n 삭제 |

> ⚠ **preset 줌 위치 복귀 신뢰성 한계**: 본 카메라(MC800S5 V3.4.5.2)는 모터 absolute encoder를 노출하지 않아 preset의 줌 위치 복귀가 비결정적이다. 실측 시 4단계 zoom-in 위치 저장 후 wide-end에서 호출했을 때 1/4건만 정확 복귀, 나머지는 어긋났고 한 건은 최대 zoom-in을 저장했음에도 호출 시 최대 wide-out으로 갔다. save/list/delete API 자체는 정상 동작. 자세한 검증은 `docs/08-endpoint-probe-2026-05-12.md §8.D`. 시스템 예약 preset(79/82/84/92/93/94/98/99)은 회피.

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
| `cam.wait_for_af_lock(*, max_wait_s, min_wait_s, stable_window, rel_tol, interval_s, warmup_s, min_var) -> dict` | 메인 스트림 Laplacian variance plateau 감지로 AF settling 추정. fps에서 interval 자동 산출 (`max(1/fps, 0.2s)`). 자세한 한계는 §11.A 참고 |
| `cam.get_video_config() -> list[dict]` | 현재 인코딩 (각 stream) |
| `cam.video_capabilities() -> list[dict]` | 지원 codec×해상도×fps×bitrate (`/system/video/capability`) |
| `cam.audio_capabilities() -> list[dict]` | 지원 오디오 코덱 (`/system/audio/capability`) |
| `cam.get_osd_enabled() -> bool` | OSD 전체 토글 상태 |
| `cam.get_zoom_setpoint() -> dict` | SCF DzoomConfig {setpoint, max} |
| `cam.get_af() -> dict` | AF enable/type/coordinate |

#### `video_capabilities()` 응답 예시

```python
caps = cam.video_capabilities()  # 45 entries on MC800S5 V3.4.5.2
caps[0]
# {'codec_name': 'H264', 'res_name': '3840X2160', 'stream_type': 0,
#  'def_bitrate': 7000, 'min_bitrate': 512, 'max_bitrate': 12288,
#  'def_framerate': 20, 'min_framerate': 5, 'max_framerate': 20,
#  'def_config': 0}
```

stream_type: `0=main`, `1=sub`, `2=third`. 본 펌웨어(V3.4.5.2) capability 요약:
- main: H264/H265/H265+, up to 3840×2160 / 60 fps / 12 288 kbps
- **sub: D1급 이하만** (720X480, VGA, 640X360, 480X360, CIF), up to 30 fps / 2048 kbps
- third: 1080P/720P/CIF, up to 10 fps

### `cam.admin` — 카메라 설정 변경 (명시적 호출만)

| 메서드 | 설명 |
|---|---|
| `cam.admin.apply_encoding_profile(profile, dry_run=True, strict_gop=False, validate=True)` | 인코딩 변경. dry_run=True면 diff만 반환. validate=True면 capability 사전 검증. SCF 채널 사용(토큰 필요). |
| `cam.admin.set_af(enable=None, af_type=None, send_on_start=None, send_coordinate=None, dry_run=True)` | AF 설정 변경. SCF `/setPtzAfConfig`. 지정한 필드만 변경, 나머지는 유지. `enable=False`로 끄면 줌 후 영상이 흐려질 수 있음 |
| `cam.admin.apply_osd(enabled, dry_run=True)` | OSD 토글 |
| `cam.admin.reboot(confirm=True)` | 재부팅 (confirm 필요). 30~60s 다운타임 |

#### `apply_encoding_profile` 동작 상세

본 카메라의 HAPI `/system/video/set`은 응답 없이 연결을 끊으며 변경도 적용하지
않는다(실증). 따라서 라이브러리는 **SCF `/setMediaVideoEncodeConfig` 채널로
라우팅**한다. 결과:

- **Capability 사전 검증** — `validate=True`(기본)면 `/system/video/capability`로
  각 스트림의 (codec, resolution, fps, bitrate) 호환성을 사전 검사. 위반 시
  `EncodingError`를 raise하여 카메라에 잘못된 값을 보내지 않는다. 검증 우회는
  `validate=False`. 헬퍼:
  ```python
  from wgwk_camera import validate_against_capability
  errors = validate_against_capability(profile, cam.video_capabilities())
  # errors: list[str], 비어 있으면 통과
  ```
- **SCF 토큰 필요** — `Camera(scf_userid=..., scf_passwd=...)` 또는 환경변수
  `SCF_USERID` / `SCF_PASSWD`. 미설정 시 `AuthError`.
- **GOP는 fps의 정수배로 클램프됨** — 펌웨어 동작. 정수배 위반 시 기본은
  `warnings.warn`, `strict_gop=True`면 `EncodingError` raise. 헬퍼:
  ```python
  from wgwk_camera import gop_will_clamp
  gop_will_clamp(100, 60)  # 120 (펌웨어가 클램프할 값)
  gop_will_clamp(60, 60)   # None (클램프 없음)
  ```
- **atomic** — PUT 실패 시 부분 반영 없음.

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

`wgwk_camera.CAPTURE_FIELDS` 에 46개 속성 전체가 정의되어 있고, 라이브러리는 펌웨어가 응답하는 모든 필드를 100% 커버한다 (2026-05-12 V3.4.5.2 기준 round-trip 검증). 자주 쓰는 항목:

| 필드 | 의미 |
|---|---|
| `Brightness`, `Contrast`, `Saturation`, `Sharpness` | 기본 화질 (0~255, 128 기본) |
| `WDRMode`, `WDRValue` | 와이드 다이내믹 레인지 |
| `shutter_mode`, `shutter_mode_night`, `shutter_speed_day`, `shutter_speed_night` | 주·야 셔터 |
| `TNF`, `SNF` | 3D / 2D 노이즈 감소 |
| `HLC`, `BackLight` | 강한 빛 보정 / 역광 보정 |
| `bManualGain`, `gainValue` | 수동 게인 활성 / 값 |
| `WB_RGB` | 화이트밸런스 (32-bit 패킹: `(enable<<24) \| (R<<16) \| (G<<8) \| B`) |
| `DfrogFlag`, `DfrogValue` | 안개 제거 |
| `forct_antiflicker` | 전원 주파수 (안티플리커) |
| `HFlip`, `VFlip`, `rotate` | 반전·회전 |
| `IrcutMode`, `IrcutNightStartTime`/`EndTime` | IRCUT 주·야 |
| `led_mode`, `led_brightness_mode`, `led_brightness_value` | 보조 LED |
| `aov_mode`, `aov_fps` | Always-On-Video |
| `isp_mode_color`, `isp_mode_night`, `videoEncodeMode`, `ispadvmode` | ISP 모드 |
| `cropxpix`, `cropypix` | 비디오 크롭 |
| `TVSystem` | 0=NTSC 60Hz, 1=PAL 50Hz |
| `light_off_sensitivity`, `face_exposure_sensitivity` | LED 차단/얼굴 노출 감도 |

### 7.A 검증 결과 (round-trip 실측, 2026-05-12 V3.4.5.2)

46개 필드를 baseline 값에서 소폭 변경 후 GET back으로 검증:

- **44개 accepted** — SET 호출 시 펌웨어가 즉시 수락하고 GET back으로 변경값 확인. 종료 시 baseline 완전 복원.
- **1개 conditional rejection — `IrcutKeepColor`**: `IrcutMode=0`(auto) 상태에서 `IrcutKeepColor=1` SET 시 GET back은 `0`. 펌웨어가 조건부 거부 (아마 IRcut auto 모드에서는 keep-color 정책이 무의미). `IrcutMode≠0` 상태에서는 수락 가능성 있으나 미검증.
- **1개 retry needed — `WDRStartTime`**: 일시 HTTP 연결 오류 1건 (필드 자체는 정상; 다음 호출에서 정상 수락 기대).

### 7.B `set_image()` 사용 권장 패턴

```python
# 변경 후 반환값으로 실제 적용 확인 — 펌웨어가 일부 필드를 조건부 거부할 수 있음
updated = cam.set_image(Brightness=200, IrcutKeepColor=1)
if updated.get("IrcutKeepColor") != "1":
    print("IrcutKeepColor not applied — check IrcutMode preconditions")
```

`set_image()`는 항상 GET back된 dict를 반환하므로 caller가 반드시 실제 적용값을 확인하는 것이 권장. 일부 필드는 다른 필드의 상태에 따라 조건부로만 수락된다.

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

## 11.A `wait_for_af_lock()` 한계와 사용 가이드

### 본질적 한계

펌웨어가 AF lock 시점을 HAPI / SCF / ONVIF / Event subscription 어느 채널로도 노출하지 않는다 (`docs/08-endpoint-probe-2026-05-12.md` §8.5). 따라서 본 메서드는 카메라에 묻지 않고 **클라이언트 측에서 메인 스트림 프레임의 Laplacian variance plateau를 감지**한다.

**측정하는 것**: "선명도가 시간에 따라 변하지 않는다"
**측정 못 하는 것**: "AF가 실제로 lock 됐다"

흐린 정적 장면도 variance가 안정이므로 lock으로 판정될 수 있다 (false positive). 실측 예 (192.168.8.101, V3.4.5.2):

| 시나리오 | locked | final_var | 실제 |
|---|---|---|---|
| 선명한 정적 장면 | True (1.85s) | 3537 | ✓ 선명 |
| AF off 후 줌 모터 이동 → 흐림 정적 | True (1.86s) | 315 | **흐림** — 함수는 plateau를 보고 lock으로 판정 |

### 실용 사용 패턴

**A. 줌 모션 직후 호출 — 가장 안전**

AF가 발사된 직후라면 plateau 도달 = AF lock 완료일 가능성 큼.

```python
cam.zoom_in(800)              # AF trigger
res = cam.wait_for_af_lock()  # 모터 정지 + AF settle까지 대기
if res["locked"]:
    cam.snapshot("frame.jpg")
```

**B. `min_var` 임계 + 베이스라인 calibration**

장면별 baseline variance를 미리 측정해서 임계로 사용.

```python
import cv2
with cam.video_main().opencv() as cap:
    for _ in range(15): cap.read()  # warmup
    _, frame = cap.read()
base = cv2.Laplacian(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var()
# 이후
res = cam.wait_for_af_lock(min_var=base * 0.7)
```

장면의 텍스처 dynamic range가 좁으면(흐림/선명 var 차이 < 2배) `min_var`도 신뢰성 낮음. 카메라 시야가 풍부한 디테일을 포함할 때 효과적.

**C. 100% 정확한 lock 신호가 필요하면**

본 라이브러리로는 불가. NETSDK 포트 8091(XML_TOPSEE) 풀 클라이언트 구현으로 `CMD_NOTIFY_AF_*` 푸시 수신 필요 — 별도의 큰 작업.

### 파라미터 가이드

| 파라미터 | 의미 | 권장 |
|---|---|---|
| `max_wait_s` | 최대 대기 (timeout) | 5~15s |
| `min_wait_s` | 안정 검사 시작 전 최소 측정 시간. 너무 짧으면 RTSP 첫 프레임만 보고 false stable | 1.5s 이상 |
| `stable_window` | 안정 판정용 슬라이딩 윈도우 | 3~5 |
| `rel_tol` | `(max-min)/mean` 임계. 작을수록 엄격 | 0.05 (5%) |
| `interval_s` | sampling 간격 | None (자동: `max(1/fps, 0.2s)`) |
| `warmup_s` | 측정 시작 전 grace | 0.3~1.0s |
| `min_var` | lock 인정 최소 variance | None 또는 baseline의 50~70% |

## 12. SW-side 줌 배율 추정 (`zoom_level`, `anchor_wide/tele`)

본 카메라는 모터 absolute encoder를 어느 채널로도 노출하지 않는다 (`docs/08 §8.5`, `§8.D`). 따라서 정확한 모터 위치 읽기는 불가능. `Camera.zoom_level`은 **클라이언트 측 시간 적분 추정**을 반환한다.

### 동작 원리

```
velocity = (max_multiplier - min_multiplier) / full_travel_ms
estimate += velocity × ms   (zoom_in 시)
estimate -= velocity × ms   (zoom_out 시)
clamp at [min_multiplier, max_multiplier]
```

생성 시 `zoom_level == None` (미앵커). `anchor_wide()` 또는 `anchor_tele()` 호출 후 추적 시작.

### 사용 패턴

```python
cam = Camera("192.168.8.101", zoom_full_travel_ms=12000)
print(cam.zoom_level)  # None (미앵커)

cam.anchor_wide()       # 15s 소요. wide hard-limit + estimate=1.0
print(cam.zoom_level)   # 1.0

cam.zoom_in(3000)
print(cam.zoom_level)   # 3.25 (3000ms × 9/12000 = +2.25)

# 장기 운영 시 drift 보정
if 어떤_조건:
    cam.anchor_wide()   # 추정 재초기화
```

### 정확도 한계

실측 (192.168.8.101 V3.4.5.2, 2026-05-12):
- 기본값 `full_travel_ms=12000` 으로 `zoom_in 10000ms` 후 SW estimate=10.0(clamped)이었으나 **시각적으로는 모터가 5~6x 부근에 머묾**.
- 본 카메라의 실제 full travel은 12s보다 길다 (대략 18~20s 추정). `full_travel_ms` 파라미터를 카메라별 calibration으로 조정 권장.
- 캘리브레이션 절차:
  1. `anchor_wide(hard_limit_ms=15000)` — wide 끝
  2. `cam.zoom_in(N_ms); cam.wait_for_af_lock(...)` 반복하면서 frame 캡처
  3. 시야 변화가 멈추는 시점의 누적 ms = 실제 full travel
  4. `Camera(zoom_full_travel_ms=measured)` 로 재생성

### `preset_call` 후 자동 invalidate

`cam.preset_call(n)` 호출 시 `zoom_level`이 자동으로 `None`이 된다. preset 복귀가 신뢰 불가하므로 (`docs/08 §8.D`) 이동 결과를 추적할 수 없기 때문. 이후 `anchor_*()`로 재초기화 필요.

### API 정리

| 메서드 | 의미 |
|---|---|
| `cam.zoom_level -> float \| None` | 추정 배율 (1.0=wide). `None`이면 미앵커 |
| `cam.anchor_wide(*, hard_limit_ms=15000, settle_extra_s=2.0)` | wide hard-limit + 1.0으로 앵커 |
| `cam.anchor_tele(*, hard_limit_ms=15000, settle_extra_s=2.0)` | tele hard-limit + max로 앵커 |
| `cam.set_zoom_estimate(x)` | 외부 정보 주입 (예: 사용자가 실제 배율을 안다) |
| `cam.zoom_in(ms)` / `cam.zoom_out(ms)` | 명령 발사 + estimate 자동 갱신 |
| `cam.preset_call(n)` | 발사 + estimate invalidate |

### 생성자 파라미터

| 파라미터 | 디폴트 | 의미 |
|---|---|---|
| `zoom_full_travel_ms` | 12000 | wide↔tele 전체 이동 시간. **카메라별 실측 권장** |
| `zoom_max_multiplier` | 10.0 | SCF `multiple_max` 값. AS500J/MC800S5 = 10x |
