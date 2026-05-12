"""Camera 통합 Facade.

외부 사용자가 가장 자주 접하는 클래스. 런타임 메서드는 직접 노출하고,
카메라 설정을 영구 변경하는 메서드는 `cam.admin.*` 네임스페이스로 분리한다.
"""
from __future__ import annotations

import socket
import warnings
from typing import Any

from .control import ControlClient
from .encoding import (
    EncodingProfile,
    gop_will_clamp,
    merge_into_current,
    validate_against_capability,
)
from .exceptions import CameraError, EncodingError
from .image import ImageClient
from .video import VideoStream


def check_reachable(host: str, port: int = 80, timeout: float = 2.0) -> None:
    """카메라 TCP 포트가 열려 있는지 빠르게 확인.

    Raises:
        CameraError: 시간 내에 연결되지 않으면.
    """
    try:
        with socket.create_connection((host, port), timeout=timeout):
            pass
    except (socket.timeout, OSError) as e:
        raise CameraError(
            f"카메라 {host}:{port}에 도달할 수 없습니다 ({e}). "
            "전원·네트워크 케이블·IP 설정을 확인하세요."
        ) from e


class Camera:
    """WGWK-AS500J / MC800S5 카메라 통합 클라이언트.

    Args:
        host: 카메라 IP.
        username, password: HAPI basic auth (출하 기본 admin/123456).
        port: HTTP 포트 (기본 80).
        scf_userid, scf_passwd: SCF 16-hex DES 토큰. 미지정 시 환경변수
            SCF_USERID/SCF_PASSWD에서 자동 로드.
        auto_login: True면 생성과 동시에 HAPI login + keep_alive 시작.

    인스턴스 생성만으로 카메라의 인코딩이나 OSD 설정이 바뀌지 않는다.
    설정 변경은 명시적으로 `cam.admin.*`을 호출해야 한다.

    Examples:
        런타임 사용:
            with Camera() as cam:
                cam.zoom_in(500)
                with cam.video_main().opencv() as cap:
                    ok, frame = cap.read()

        Admin (1회 설정):
            from wgwk_camera import Camera, PRECISION_PROFILE
            cam = Camera()
            diff = cam.admin.apply_encoding_profile(PRECISION_PROFILE)  # dry_run
            print(diff)
            cam.admin.apply_encoding_profile(PRECISION_PROFILE, dry_run=False)
    """

    def __init__(
        self,
        host: str = "192.168.8.101",
        username: str = "admin",
        password: str = "123456",
        *,
        port: int = 80,
        scf_userid: str | None = None,
        scf_passwd: str | None = None,
        auto_login: bool = True,
        preflight: bool = True,
        preflight_timeout: float = 2.0,
    ) -> None:
        """
        Args:
            preflight: True(기본)면 생성 시 TCP 도달성 확인. 카메라가 응답
                안 하면 즉시 CameraError. False면 첫 메서드 호출까지 지연.
            preflight_timeout: 도달성 확인 timeout (초).
            auto_login: True(기본)면 preflight 통과 후 HAPI 로그인 + keep_alive.
        """
        if preflight:
            check_reachable(host, port, timeout=preflight_timeout)
        self._control = ControlClient(host=host, username=username,
                                      password=password, port=port)
        self._image = ImageClient(host=host, port=port,
                                  userid=scf_userid or "", passwd=scf_passwd or "")
        self._admin = AdminFacade(self)
        self._host = host
        self._user = username
        self._password = password
        self._port = port
        if auto_login:
            self._control.login()

    def is_reachable(self, *, timeout: float = 2.0) -> bool:
        """런타임에 카메라 도달성을 다시 확인. 예외 없이 bool 반환."""
        try:
            check_reachable(self._host, self._port, timeout=timeout)
            return True
        except CameraError:
            return False

    def close(self) -> None:
        self._control.logout()

    def __enter__(self) -> "Camera":
        if not self._control.is_logged_in:
            self._control.login()
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    # ─── 컴포넌트 직접 접근 (고급 사용자) ────────────────────

    @property
    def control(self) -> ControlClient:
        """HAPI 제어 클라이언트 (raw 접근용)."""
        return self._control

    @property
    def image(self) -> ImageClient:
        """SCF 이미지 설정 클라이언트 (raw 접근용)."""
        return self._image

    @property
    def admin(self) -> "AdminFacade":
        """카메라 설정을 변경하는 메서드들. 명시적 호출만 권장."""
        return self._admin

    # ─── 런타임 — 줌 / 포커스 / 프리셋 / 스냅샷 ────────────

    def zoom_in(self, ms: int = 500) -> None:
        self._control.zoom("in", autostop_ms=ms)

    def zoom_out(self, ms: int = 500) -> None:
        self._control.zoom("out", autostop_ms=ms)

    def zoom_stop(self) -> None:
        self._control.stop()

    def focus_near(self, ms: int = 200) -> None:
        self._control.focus("near", autostop_ms=ms)

    def focus_far(self, ms: int = 200) -> None:
        self._control.focus("far", autostop_ms=ms)

    def focus_restore(self) -> None:
        """AF 기본 위치(focus far 부근)로 복귀. PTZ advfunction FocusRestore."""
        self._control.advfunction_exec("FocusRestore")

    def move(self, direction: str, speed: int = 5, ms: int = 500) -> None:
        self._control.move(direction, speed=speed, autostop_ms=ms)

    def stop(self) -> None:
        """모든 PTZ 동작(줌·포커스·회전) 정지."""
        self._control.stop()

    def preset_save(self, no: int) -> None:
        self._control.preset("set", no)

    def preset_call(self, no: int) -> None:
        self._control.preset("call", no)

    def preset_delete(self, no: int) -> None:
        self._control.preset("delete", no)

    def snapshot(self, path: str | None = None) -> bytes:
        """JPEG 스냅샷 (720×480). path 지정 시 파일 저장, 항상 bytes 반환."""
        data = self._control.snapshot_bytes()
        if path is not None:
            with open(path, "wb") as f:
                f.write(data)
        return data

    # ─── 런타임 — 이미지 환경 조정 ──────────────────────────

    def get_image(self) -> dict[str, str]:
        """현재 Capture 설정. SCF 토큰 필요."""
        return self._image.get_image()

    def set_image(self, **fields: Any) -> dict[str, str]:
        """이미지 환경 변경 (런타임 — 야간 진입, WDR ON 등). SCF 토큰 필요.

        Example:
            cam.set_image(WDRMode=1, shutter_mode_night=2, bManualGain=1, gainValue=80)
        """
        return self._image.set_image(**fields)

    # ─── 런타임 — 비디오 스트림 ──────────────────────────────

    def video_main(self, *, transport: str = "udp") -> VideoStream:
        return VideoStream(host=self._host, kind="main",
                           user=self._user, password=self._password,
                           transport=transport)

    def video_sub(self, *, transport: str = "udp") -> VideoStream:
        return VideoStream(host=self._host, kind="sub",
                           user=self._user, password=self._password,
                           transport=transport)

    def video(self, kind: str = "main", *, transport: str = "udp") -> VideoStream:
        return VideoStream(host=self._host, kind=kind,
                           user=self._user, password=self._password,
                           transport=transport)

    # ─── 상태 조회 (read-only) ──────────────────────────────

    def info(self) -> dict:
        return self._control.info()

    def capabilities(self) -> list[str]:
        return self._control.capability()

    def function_list(self) -> list[str]:
        return self._control.function_list()

    def rtsp_urls(self) -> dict[str, str]:
        return self._control.rtsp_urls()

    def get_video_config(self) -> list[dict]:
        """현재 인코딩 설정 read. **변경하지 않음**."""
        return self._control.video_config()

    def video_capabilities(self) -> list[dict]:
        """카메라가 지원하는 codec/해상도/비트레이트/프레임레이트 범위."""
        return self._control.video_capability()

    def audio_capabilities(self) -> list[dict]:
        """카메라가 지원하는 오디오 코덱 목록."""
        return self._control.audio_capability()

    def get_osd_enabled(self) -> bool:
        return bool(self._control.osd_get().get("enable", 0))

    def get_zoom_setpoint(self) -> dict[str, float]:
        """SCF DzoomConfig setpoint+max. SCF 토큰 필요."""
        return self._image.get_zoom()

    def get_af(self) -> dict[str, int]:
        return self._image.get_af()


# ──────────────────────────────────────────────────────────────────
# Admin Facade — 카메라 설정 변경 메서드만 모음
# ──────────────────────────────────────────────────────────────────

class AdminFacade:
    """카메라 설정을 영구 변경하는 메서드들.

    `Camera.admin`을 통해 접근. 부주의 호출을 막기 위해 별도 네임스페이스로 분리.
    `apply_*` 메서드는 기본적으로 `dry_run=True`로, diff만 반환하고 카메라엔
    실제 변경을 가하지 않는다. 적용하려면 `dry_run=False`를 명시한다.
    """

    def __init__(self, cam: "Camera") -> None:
        self._cam = cam

    # ─── 인코딩 ─────────────────────────────────────────────

    def apply_encoding_profile(self, profile: EncodingProfile,
                               *, dry_run: bool = True,
                               strict_gop: bool = False,
                               validate: bool = True) -> dict[int, dict]:
        """인코딩 프로필을 카메라에 적용.

        1. (validate=True) `/system/video/capability`로 사전 검증
        2. 현재 video_config(HAPI) GET — 표시·진단 용도
        3. profile과 merge — bitRateControl, qp_enable 등 부수 필드는 보존
        4. GOP 클램프 가드 — fps의 정수배가 아니면 경고(또는 strict_gop=True면 raise)
        5. dry_run=False면 SCF /setMediaVideoEncodeConfig로 PUT

        주의: 본 카메라(MC800S5 V3.4.5.2)의 HAPI `/system/video/set`은 응답
        없이 끊기고 변경도 적용되지 않는다. 따라서 인코딩 변경은 SCF로 라우팅하며,
        SCF 토큰(SCF_USERID/SCF_PASSWD)이 필요하다.

        Args:
            profile: EncodingProfile.
            dry_run: True(기본)면 변경 사항만 보여주고 실제 적용 안 함.
            strict_gop: True면 gop이 fps의 정수배가 아닐 때 EncodingError raise.
                False(기본)면 warnings.warn 후 진행 — 펌웨어가 클램프함.
            validate: True(기본)면 적용 전 카메라 capability로 codec/해상도/fps/
                bitrate 범위를 검증. 호환되지 않으면 EncodingError raise.

        Returns:
            {stream_id: {field: (old, new)}} 차이 dict.
            빈 dict면 이미 프로필 상태와 동일.

        Raises:
            EncodingError: 검증 실패(validate=True) 또는 strict_gop=True 위반.
            AuthError: dry_run=False인데 SCF 토큰이 미설정.
        """
        if validate:
            capability = self._cam.control.video_capability()
            errors = validate_against_capability(profile, capability)
            if errors:
                raise EncodingError(
                    "profile incompatible with camera capability:\n  - "
                    + "\n  - ".join(errors)
                )

        current = self._cam.control.video_config()
        merged, diff = merge_into_current(current, profile)

        # GOP 클램프 가드 — fps 정수배 위반 시 경고
        for s in merged:
            gop = s.get("gop")
            fps = s.get("frameRate")
            if not (isinstance(gop, int) and isinstance(fps, int)):
                continue
            clamped = gop_will_clamp(gop, fps)
            if clamped is None:
                continue
            msg = (
                f"stream{s.get('streamID')}: gop={gop}는 fps={fps}의 정수배가 "
                f"아닙니다. 펌웨어가 {clamped}로 클램프할 가능성이 큼."
            )
            if strict_gop:
                raise EncodingError(msg)
            warnings.warn(msg, stacklevel=2)

        if dry_run or not diff:
            return diff
        # SCF 채널로 라우팅 (HAPI는 본 펌웨어에서 동작 안 함)
        self._cam.image.set_video_encoding(merged)
        return diff

    # ─── AF (Auto Focus) ────────────────────────────────────

    def set_af(
        self,
        *,
        enable: bool | None = None,
        af_type: int | None = None,
        send_on_start: bool | None = None,
        send_coordinate: bool | None = None,
        dry_run: bool = True,
    ) -> dict[str, Any]:
        """AF 설정 변경. SCF `/setPtzAfConfig` 사용.

        지정하지 않은 필드는 현재 값을 유지한다. `dry_run=True`(기본)이면
        예상 diff만 반환하고 카메라 설정은 변경하지 않는다.

        주의: `enable=False`로 AF를 끄면 줌 동작 후 자동 포커싱이 되지 않아
        영상이 흐려질 수 있다. 작업 완료 후 `enable=True`로 복원 권장.

        Args:
            enable: AF on(True)/off(False)/유지(None).
            af_type: AF 알고리즘 타입(펌웨어 의존, 보통 0).
            send_on_start: 카메라 부팅 시 AF 명령 자동 발사.
            send_coordinate: 좌표 정보 전송 여부.
            dry_run: True면 변경 사항만 표시.

        Returns:
            dry_run=True: {"changed": bool, "before": dict, "would": dict}.
            dry_run=False: {"changed": bool, "before": dict, "after": dict}.
        """
        before = self._cam.image.get_af()
        proposed = {
            "enable":         (1 if enable        is True else 0 if enable        is False else before["enable"]),
            "type":           (af_type            if af_type is not None         else before["type"]),
            "send_on_start":  (1 if send_on_start is True else 0 if send_on_start is False else before["send_on_start"]),
            "send_coordinate":(1 if send_coordinate is True else 0 if send_coordinate is False else before["send_coordinate"]),
        }
        changed = proposed != before
        if dry_run or not changed:
            return {"changed": changed, "before": before, "would": proposed}
        after = self._cam.image.set_af(
            enable=enable,
            af_type=af_type,
            send_on_start=send_on_start,
            send_coordinate=send_coordinate,
        )
        return {"changed": True, "before": before, "after": after}

    # ─── OSD ────────────────────────────────────────────────

    def apply_osd(self, enabled: bool, *, dry_run: bool = True) -> dict:
        """OSD 전체 토글 (시간 + Camera 타이틀).

        주의: 줌 동작 중 표시되는 KF 인디케이터는 본 토글에 영향받지 않을 수
        있다. docs/06-live-probe-result.md 참고.
        """
        current = self._cam.control.osd_get()
        if bool(current.get("enable")) == bool(enabled):
            return {"changed": False, "current": current}
        if dry_run:
            return {"changed": True, "from": current.get("enable"),
                    "to": int(enabled), "dry_run": True}
        new = dict(current)
        new["enable"] = int(enabled)
        self._cam.control._set_osd_full(new)
        return {"changed": True, "from": current.get("enable"),
                "to": int(enabled), "dry_run": False}

    # ─── 재부팅 ─────────────────────────────────────────────

    def reboot(self, *, confirm: bool = False) -> dict:
        """카메라 재부팅. 30~60초 가량 다운타임 발생.

        Args:
            confirm: True를 명시적으로 전달해야 동작. False면 raise.

        Raises:
            CameraError: confirm=False일 때.
        """
        if not confirm:
            raise CameraError(
                "reboot은 명시적 confirm=True 인자가 필요합니다. "
                "재부팅은 ~30~60s 다운타임을 동반합니다."
            )
        return self._cam.control._reboot()

    # 공장 초기화는 의도적으로 미구현. 필요 시 직접 HAPI 호출:
    #   GET /HAPI/V1.0/sysman/factory?uid=<SID>
    # 모든 설정 + 네트워크 구성까지 출하 기본값으로 복원되어 IP가 바뀐다.
    # 라이브러리에는 노출하지 않음.
