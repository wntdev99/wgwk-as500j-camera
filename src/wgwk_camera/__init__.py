"""wgwk_camera — WGWK-AS500J / MC800S5 IP 카메라 통합 라이브러리.

빠른 시작:
    from wgwk_camera import Camera

    with Camera("192.168.8.101") as cam:
        cam.zoom_in(500)
        cam.snapshot("frame.jpg")
        with cam.video_main().opencv() as cap:
            ok, frame = cap.read()

고급 사용:
    from wgwk_camera import (
        Camera, VideoStream, EncodingProfile, StreamSpec,
        PRECISION_PROFILE, ROBOT_VISION_PROFILE,
        ControlClient, ImageClient,
        CameraError, AuthError, EncodingError, StreamError,
    )

라이브러리 인스턴스 생성만으로 카메라 설정이 바뀌지 않는다. 인코딩·OSD 변경은
`cam.admin.apply_*(..., dry_run=False)` 명시적 호출에서만 발생한다.
"""
from __future__ import annotations

from .control import ControlClient
from .encoding import EncodingProfile, StreamSpec, gop_will_clamp, merge_into_current
from .exceptions import AuthError, CameraError, EncodingError, StreamError
from .facade import AdminFacade, Camera, check_reachable
from .image import CAPTURE_FIELDS, ImageClient
from .profiles import (
    ALL_PROFILES,
    BANDWIDTH_SAVE_PROFILE,
    FAST_TRACKING_PROFILE,
    PRECISION_PROFILE,
    ROBOT_VISION_PROFILE,
)
from .video import VideoStream

__version__ = "0.1.0"

__all__ = [
    # 주 진입점
    "Camera",
    # 컴포넌트
    "ControlClient", "ImageClient", "VideoStream", "AdminFacade",
    # 헬퍼
    "check_reachable",
    # 인코딩 / 프로필
    "EncodingProfile", "StreamSpec", "merge_into_current", "gop_will_clamp",
    "PRECISION_PROFILE", "ROBOT_VISION_PROFILE",
    "BANDWIDTH_SAVE_PROFILE", "FAST_TRACKING_PROFILE", "ALL_PROFILES",
    # Capture 필드 카탈로그
    "CAPTURE_FIELDS",
    # 예외
    "CameraError", "AuthError", "EncodingError", "StreamError",
    # 메타
    "__version__",
]
