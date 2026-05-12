"""wgwk_camera 라이브러리 예외 계층."""
from __future__ import annotations


class CameraError(RuntimeError):
    """카메라 통신/응답 오류의 베이스 예외."""


class AuthError(CameraError):
    """HAPI 또는 SCF 인증 실패."""


class EncodingError(CameraError):
    """인코딩 설정 적용 실패 또는 잘못된 프로필."""


class StreamError(CameraError):
    """RTSP 또는 비디오 캡처 오류."""
