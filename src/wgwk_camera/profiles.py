"""사전 정의 인코딩 프로필 (참조 상수).

이 상수들은 admin 호출 시 인자로 전달해야 카메라에 적용된다.
라이브러리는 자동으로 카메라 설정을 변경하지 않는다.
"""
from __future__ import annotations

from .encoding import EncodingProfile, StreamSpec


# ──────────────────────────────────────────────────────────────────
# 정밀 검출 (작은 결함·OCR) — 지휘관 결정 시나리오
# ──────────────────────────────────────────────────────────────────
PRECISION_PROFILE = EncodingProfile(
    name="precision",
    description="정밀 검출 + 서브 활용 + OSD off",
    main =StreamSpec(True,  "H264", "1080P", 60, 3000, 60),
    sub  =StreamSpec(True,  "H264", "720P",  20,  800, 20),
    third=StreamSpec(False, "H264", "720P",  10,  300, 10),
    osd_enabled=False,
)

# ──────────────────────────────────────────────────────────────────
# 일반 로봇 비전 (균형)
# ──────────────────────────────────────────────────────────────────
ROBOT_VISION_PROFILE = EncodingProfile(
    name="robot_vision",
    description="저지연·디코딩 부담 적음 (NUC/Jetson 기본 시나리오)",
    main =StreamSpec(True,  "H264", "1080P", 30, 4000, 30),
    sub  =StreamSpec(True,  "H264", "720X480", 15, 500, 30),
    third=StreamSpec(False, "H264", "720P",  10,  300, 10),
    osd_enabled=False,
)

# ──────────────────────────────────────────────────────────────────
# 대역폭 절약 (WiFi / 4G)
# ──────────────────────────────────────────────────────────────────
BANDWIDTH_SAVE_PROFILE = EncodingProfile(
    name="bandwidth_save",
    description="H.265+ 사용, 비트레이트 최소",
    main =StreamSpec(True,  "H265+", "1080P", 25, 2000, 25),
    sub  =StreamSpec(True,  "H265",  "720X480", 15, 300, 30),
    third=StreamSpec(False, "H264",  "720P",  10,  300, 10),
    osd_enabled=False,
)

# ──────────────────────────────────────────────────────────────────
# 빠른 추적 (60fps, 작은 객체 추적 최적화)
# ──────────────────────────────────────────────────────────────────
FAST_TRACKING_PROFILE = EncodingProfile(
    name="fast_tracking",
    description="고프레임율로 빠른 움직임 캡처",
    main =StreamSpec(True,  "H264", "1080P", 60, 4500, 30),
    sub  =StreamSpec(True,  "H264", "720P",  30,  800, 30),
    third=StreamSpec(False, "H264", "720P",  10,  300, 10),
    osd_enabled=False,
)

ALL_PROFILES: dict[str, EncodingProfile] = {
    p.name: p for p in (PRECISION_PROFILE, ROBOT_VISION_PROFILE,
                        BANDWIDTH_SAVE_PROFILE, FAST_TRACKING_PROFILE)
}
