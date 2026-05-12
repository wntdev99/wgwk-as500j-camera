"""인코딩 프로필 데이터 타입 (참조용).

이 모듈은 **카메라 설정을 변경하지 않는다**. EncodingProfile은 admin 메서드의
인자로만 사용되며, 변경 호출은 `Camera.admin.apply_encoding_profile()`이다.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Iterable


@dataclass(frozen=True)
class StreamSpec:
    """비디오 스트림 한 채널의 인코딩 명세.

    HAPI `/system/video/get` 응답의 단일 stream 항목과 1:1 매핑.

    Attributes:
        enable: 스트림 활성화 여부.
        codec: "H264" / "H265" / "H265+".
        resolution: "3840X2160", "1080P", "720P", "720X480", "VGA", "640X360", "CIF" 등.
        fps: 1~60 (해상도·코덱 의존).
        bitrate_kbps: 코덱·해상도별 min/max는 카메라 capability 참조.
        gop: 1~200 (IDR 간격 = gop / fps 초).
    """
    enable: bool
    codec: str
    resolution: str
    fps: int
    bitrate_kbps: int
    gop: int


@dataclass(frozen=True)
class EncodingProfile:
    """3개 스트림 + OSD 토글을 한 묶음으로 정의하는 프로필."""
    name: str
    main: StreamSpec       # streamID = 1
    sub: StreamSpec        # streamID = 2
    third: StreamSpec      # streamID = 3
    osd_enabled: bool = False
    description: str = ""

    def to_hapi_list(self) -> list[dict]:
        """HAPI `/system/video/set` 페이로드 형식의 list 반환.

        주의: 카메라가 기존에 갖고 있던 bitRateControl, qp_enable 같은 부수 필드는
        보존되어야 하므로, 실제 admin 호출에서는 **현재 응답을 GET해 merge**한다.
        본 메서드는 핵심 필드만 채운 dict를 만든다.
        """
        return [self._stream_dict(1, self.main),
                self._stream_dict(2, self.sub),
                self._stream_dict(3, self.third)]

    @staticmethod
    def _stream_dict(stream_id: int, spec: StreamSpec) -> dict:
        return {
            "streamID": stream_id,
            "enable": int(spec.enable),
            "encodeFormat": spec.codec,
            "resolution": spec.resolution,
            "frameRate": spec.fps,
            "bitRate": spec.bitrate_kbps,
            "gop": spec.gop,
        }


def gop_will_clamp(gop: int, fps: int) -> int | None:
    """gop이 fps의 정수배가 아닐 때 펌웨어가 클램프할 예상 값.

    실측: MC800S5 V3.4.5.2 펌웨어는 `/setMediaVideoEncodeConfig`로 임의 GOP를
    보내면 fps의 가장 가까운 정수배로 강제 정렬한다.

    Args:
        gop: 요청한 GOP.
        fps: 같은 스트림의 frameRate.

    Returns:
        펌웨어가 실제 적용할 GOP. 정수배면 None (클램프 없음).

    Examples:
        gop_will_clamp(100, 60) -> 120   # 60×2
        gop_will_clamp(60, 60)  -> None  # 정수배
        gop_will_clamp(30, 30)  -> None
        gop_will_clamp(50, 30)  -> 60    # 30×2
    """
    if fps <= 0:
        return None
    if gop % fps == 0:
        return None
    return round(gop / fps) * fps


def validate_against_capability(
    profile: EncodingProfile,
    capability: list[dict],
) -> list[str]:
    """프로필이 카메라 capability와 호환되는지 검사.

    HAPI `/system/video/capability` 응답과 비교해서 다음을 검증:
      - 각 스트림의 (codec, resolution) 조합이 capability에 존재
      - fps가 [min_framerate, max_framerate] 범위 내
      - bitrate가 [min_bitrate, max_bitrate] 범위 내

    Args:
        profile: 검사 대상 프로필.
        capability: `ControlClient.video_capability()` 응답.

    Returns:
        오류 메시지 리스트. 비어 있으면 통과. 비활성 스트림(enable=False)은 검사 생략.
    """
    errors: list[str] = []
    stream_label = {0: "main", 1: "sub", 2: "third"}
    for stream_type, spec in enumerate(
        [profile.main, profile.sub, profile.third]
    ):
        if not spec.enable:
            continue
        label = stream_label.get(stream_type, f"stream{stream_type}")
        matches = [
            c for c in capability
            if c.get("stream_type") == stream_type
            and c.get("codec_name") == spec.codec
            and c.get("res_name") == spec.resolution
        ]
        if not matches:
            available = sorted({
                f'{c.get("codec_name")}/{c.get("res_name")}'
                for c in capability if c.get("stream_type") == stream_type
            })
            errors.append(
                f"{label}: codec={spec.codec} resolution={spec.resolution} "
                f"not in capability. available: {', '.join(available) or '<none>'}"
            )
            continue
        entry = matches[0]
        fmin, fmax = entry.get("min_framerate", 0), entry.get("max_framerate", 0)
        if not (fmin <= spec.fps <= fmax):
            errors.append(
                f"{label}: fps={spec.fps} out of [{fmin}, {fmax}] for "
                f"{spec.codec}/{spec.resolution}"
            )
        bmin, bmax = entry.get("min_bitrate", 0), entry.get("max_bitrate", 0)
        if not (bmin <= spec.bitrate_kbps <= bmax):
            errors.append(
                f"{label}: bitrate={spec.bitrate_kbps}kbps out of [{bmin}, {bmax}] "
                f"for {spec.codec}/{spec.resolution}"
            )
    return errors


def merge_into_current(current: list[dict], profile: EncodingProfile) -> tuple[list[dict], dict]:
    """현재 video config와 profile을 병합.

    - 카메라가 갖고 있던 bitRateControl, qp_enable 등의 부수 필드는 그대로 유지
    - 프로필이 지정한 필드만 덮어쓴다
    - 변경된 항목은 diff dict로 반환

    Args:
        current: HAPI `/system/video/get` 응답의 Data list (각 dict는 streamID 포함).
        profile: 적용할 프로필.

    Returns:
        (merged_list, diff_per_stream).
        diff_per_stream 형식: {stream_id: {field: (old, new)}}.
    """
    target_by_id = {entry["streamID"]: entry for entry in profile.to_hapi_list()}
    merged = []
    diff: dict[int, dict[str, tuple]] = {}

    for cur in current:
        sid = cur["streamID"]
        tgt = target_by_id.get(sid)
        if tgt is None:
            merged.append(dict(cur))
            continue
        new = dict(cur)
        per_stream_diff: dict[str, tuple] = {}
        for key, new_val in tgt.items():
            if key == "streamID":
                continue
            old_val = new.get(key)
            if old_val != new_val:
                per_stream_diff[key] = (old_val, new_val)
                new[key] = new_val
        merged.append(new)
        if per_stream_diff:
            diff[sid] = per_stream_diff

    return merged, diff
