"""RTSP 저지연 비디오 캡처 헬퍼.

OpenCV (cv2)는 선택적 의존성이다. opencv 없이도 `gst_pipeline()`,
`url`, `ffmpeg_record()`는 동작한다. `opencv()` 컨텍스트 매니저만
opencv-python을 요구.
"""
from __future__ import annotations

import os
import subprocess
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator

from .exceptions import StreamError


_STREAM_SUFFIX = {
    "main": "stream0",   # streamID = 1
    "sub": "stream1",    # streamID = 2
    "third": "stream2",  # streamID = 3
}


@dataclass
class VideoStream:
    """카메라의 한 RTSP 스트림(메인/서브/3rd)에 대한 캡처 헬퍼.

    핵심 사용:
        with cam.video_main() as cap:
            ok, frame = cap.read()

    또는 직접 GStreamer 파이프라인 문자열 받기:
        gst_str = cam.video_main().gst_pipeline()

    Args:
        host: 카메라 IP.
        kind: "main" / "sub" / "third".
        user, password: RTSP basic auth.
        port: RTSP 포트 (기본 554).
        transport: "udp"(저지연 권장) 또는 "tcp"(신뢰성).
    """
    host: str
    kind: str = "main"
    user: str = "admin"
    password: str = "123456"
    port: int = 554
    transport: str = "udp"

    def __post_init__(self) -> None:
        if self.kind not in _STREAM_SUFFIX:
            raise ValueError(
                f"kind must be one of {list(_STREAM_SUFFIX)}, got {self.kind!r}"
            )
        if self.transport not in ("udp", "tcp"):
            raise ValueError("transport must be 'udp' or 'tcp'")

    # ─── URL ─────────────────────────────────────────────────

    @property
    def url(self) -> str:
        """`rtsp://user:pass@host:port/stream{N}` 형태."""
        path = _STREAM_SUFFIX[self.kind]
        return f"rtsp://{self.user}:{self.password}@{self.host}:{self.port}/{path}"

    @property
    def url_no_auth(self) -> str:
        path = _STREAM_SUFFIX[self.kind]
        return f"rtsp://{self.host}:{self.port}/{path}"

    # ─── OpenCV 캡처 (선택적 의존: opencv-python) ──────────

    @contextmanager
    def opencv(self) -> Iterator[Any]:
        """`cv2.VideoCapture` 객체를 저지연 옵션으로 열어 yield.

        Yields:
            cv2.VideoCapture
        Raises:
            StreamError: opencv 미설치 또는 RTSP 연결 실패.
        """
        try:
            import cv2  # noqa: F401 — lazy import
        except ImportError as e:
            raise StreamError(
                "opencv-python이 필요합니다. `pip install opencv-python` 또는 "
                "`pip install wgwk-camera[video]`."
            ) from e

        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
            f"rtsp_transport;{self.transport}|"
            f"fflags;nobuffer|flags;low_delay|max_delay;0"
        )
        cap = cv2.VideoCapture(self.url, cv2.CAP_FFMPEG)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if not cap.isOpened():
            raise StreamError(f"RTSP open failed: {self.url_no_auth}")
        try:
            yield cap
        finally:
            cap.release()

    # ─── GStreamer 파이프라인 문자열 ─────────────────────────

    def gst_pipeline(self, *, codec: str = "h264", appsink: bool = True) -> str:
        """ROS gscam2, Python gst, 또는 gst-launch-1.0 용 파이프라인 문자열.

        Args:
            codec: "h264" 또는 "h265". 카메라 설정과 일치해야 함.
            appsink: True면 appsink로 끝남(프로그램 처리용), False면 fpsdisplaysink.
        """
        if codec not in ("h264", "h265"):
            raise ValueError("codec must be 'h264' or 'h265'")
        depay = f"rtp{codec}depay"
        parse = f"{codec}parse"
        decode = f"avdec_{codec} max-threads=4"
        sink = ("appsink sync=false drop=true max-buffers=1"
                if appsink else "fpsdisplaysink sync=false text-overlay=true")
        return (
            f'rtspsrc location="{self.url}" latency=0 protocols={self.transport} '
            f'drop-on-latency=true ! {depay} ! {parse} config-interval=-1 ! '
            f'{decode} ! videoconvert ! {sink}'
        )

    # ─── FFmpeg 단발 녹화 ────────────────────────────────────

    def ffmpeg_record(self, out_path: str, duration_sec: int = 30,
                      *, copy_codec: bool = True) -> None:
        """ffmpeg로 N초 녹화 (재인코딩 없이 그대로 저장).

        Args:
            out_path: 출력 파일 (.mp4 권장).
            duration_sec: 녹화 시간.
            copy_codec: True면 `-c copy`. False면 재인코딩.
        """
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error",
               "-rtsp_transport", self.transport, "-i", self.url,
               "-t", str(duration_sec)]
        if copy_codec:
            cmd += ["-c", "copy"]
        cmd += ["-y", out_path]
        try:
            subprocess.run(cmd, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            raise StreamError(f"ffmpeg 실패: {e}") from e

    def ffmpeg_grab_frame(self, out_path: str) -> None:
        """RTSP에서 1프레임 추출 (스냅샷보다 고해상도 가능)."""
        try:
            subprocess.run(
                ["ffmpeg", "-hide_banner", "-loglevel", "error",
                 "-rtsp_transport", self.transport, "-i", self.url,
                 "-frames:v", "1", "-y", out_path],
                check=True, timeout=10,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired,
                FileNotFoundError) as e:
            raise StreamError(f"ffmpeg grab 실패: {e}") from e
