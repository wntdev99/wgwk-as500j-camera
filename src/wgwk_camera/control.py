"""HAPI 기반 제어 클라이언트 (줌·포커스·프리셋·스냅샷 + 상태 조회).

이 모듈의 메서드는 **카메라 인코딩 설정을 변경하지 않는다**. 인코딩 변경은
admin 모듈(`facade.AdminFacade`)을 통해 명시적으로만 가능하다.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any

import requests

from ._http import DEFAULT_TIMEOUT_SEC, hapi_check, http_session, md5_hex
from .exceptions import AuthError, CameraError, StreamError


KEEPALIVE_INTERVAL_SEC = 30  # HAPI 1.5: 60초 만료, 30초 마진


@dataclass
class ControlClient:
    """HAPI 1.5 클라이언트.

    런타임 사용 메서드:
        login / logout / keep_alive (자동)
        zoom / focus / iris / move / stop / preset
        snapshot / snapshot_bytes
        info / capability / rtsp_urls / video_config / osd_get
        advfunction_list / advfunction_exec

    Admin 권한 메서드 (호출 주의):
        _set_video_config (raw)
        _set_osd_enabled (raw)
        _reboot (raw)
    이들은 underscore prefix로 표시하고, `facade.AdminFacade`에서 명시적
    호출만 노출한다.
    """

    host: str = "192.168.8.213"
    username: str = "admin"
    password: str = "123456"
    port: int = 80
    timeout: float = DEFAULT_TIMEOUT_SEC

    _session: requests.Session = field(default_factory=http_session, init=False)
    _uid: str | None = field(default=None, init=False)
    _keepalive_thread: threading.Thread | None = field(default=None, init=False)
    _stop_keepalive: threading.Event = field(default_factory=threading.Event, init=False)

    # ─── 베이스 URL ──────────────────────────────────────────────

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}/HAPI/V1.0"

    @property
    def is_logged_in(self) -> bool:
        return self._uid is not None

    # ─── HTTP 헬퍼 ──────────────────────────────────────────────

    def _get(self, path: str, **params: Any) -> dict:
        url = f"{self.base_url}{path}"
        if "uid" not in params and "username" not in params:
            if self._uid:
                params["uid"] = self._uid
            else:
                params["username"] = self.username
                params["password"] = md5_hex(self.password)
        try:
            r = self._session.get(url, params=params, timeout=self.timeout)
            r.raise_for_status()
        except requests.RequestException as e:
            raise CameraError(f"HAPI GET {path}: {e}") from e
        return hapi_check(r.json(), path)

    def _put(self, path: str, body: Any) -> dict:
        url = f"{self.base_url}{path}"
        params = {"uid": self._uid} if self._uid else {
            "username": self.username, "password": md5_hex(self.password)
        }
        try:
            r = self._session.put(url, params=params, json=body,
                                  headers={"Content-Type": "application/json"},
                                  timeout=self.timeout)
            r.raise_for_status()
        except requests.RequestException as e:
            raise CameraError(f"HAPI PUT {path}: {e}") from e
        return hapi_check(r.json(), path)

    # ─── 세션 ────────────────────────────────────────────────────

    def login(self) -> str:
        """uid 발급 + 30초 주기 keep_alive 스레드 시작."""
        url = f"{self.base_url}/uid/getuid"
        r = self._session.get(url, params={
            "username": self.username,
            "password": md5_hex(self.password),
        }, timeout=self.timeout)
        r.raise_for_status()
        data = r.json().get("Response", {})
        if data.get("ResponseCode") != 0:
            raise AuthError(f"login failed: {data.get('ResponseString')}")
        sid = data.get("SessionID")
        if not sid:
            raise AuthError("login: empty SessionID")
        self._uid = sid
        self._start_keepalive()
        return sid

    def logout(self) -> None:
        self._stop_keepalive.set()
        if self._keepalive_thread is not None:
            self._keepalive_thread.join(timeout=2.0)
        self._uid = None

    def _start_keepalive(self) -> None:
        if self._keepalive_thread and self._keepalive_thread.is_alive():
            return
        self._stop_keepalive.clear()
        t = threading.Thread(target=self._keepalive_loop,
                             daemon=True, name="wgwk-keepalive")
        t.start()
        self._keepalive_thread = t

    def _keepalive_loop(self) -> None:
        while not self._stop_keepalive.wait(KEEPALIVE_INTERVAL_SEC):
            if not self._uid:
                return
            try:
                self._get("/uid/keep_alive")
            except CameraError:
                # 일시적 끊김 — 다음 주기에 재시도
                pass

    # ─── 정보 조회 (read-only) ─────────────────────────────────

    def info(self) -> dict:
        """device_info: SN, device_type, model, MAC, kernel, fsversion."""
        return self._get("/sysinfo/device_info")

    def capability(self) -> list[str]:
        data = self._get("/sysinfo/capability")
        return sorted({entry["caps"] for entry in data})

    def function_list(self) -> list[str]:
        data = self._get("/sysinfo/functionlist")
        return sorted({entry["api"] for entry in data})

    def rtsp_urls(self) -> dict[str, str]:
        """{'ch0_main': 'rtsp://...', 'ch0_sub': 'rtsp://...'}"""
        return self._get("/sysinfo/rtspurl")

    def video_config(self) -> list[dict]:
        return self._get("/system/video/get")

    def osd_get(self) -> dict:
        return self._get("/system/osd/get")

    def advfunction_list(self) -> list[str]:
        data = self._get("/ptz_ctrl/advfunction/get")
        return [e["functionname"] for e in data]

    # ─── PTZ / 줌 / 포커스 / 프리셋 ────────────────────────────

    def zoom(self, direction: str, autostop_ms: int = 500) -> dict:
        if direction not in ("in", "out"):
            raise ValueError("direction must be 'in' or 'out'")
        return self._get("/ptz_ctrl/zoom",
                         direction=direction, autostop=autostop_ms)

    def focus(self, direction: str, autostop_ms: int = 200) -> dict:
        if direction not in ("near", "far"):
            raise ValueError("direction must be 'near' or 'far'")
        return self._get("/ptz_ctrl/focus",
                         direction=direction, autostop=autostop_ms)

    def iris(self, direction: str, autostop_ms: int = 100) -> dict:
        if direction not in ("open", "close"):
            raise ValueError("direction must be 'open' or 'close'")
        return self._get("/ptz_ctrl/iris",
                         direction=direction, autostop=autostop_ms)

    def move(self, direction: str, speed: int = 5, autostop_ms: int = 500) -> dict:
        valid = {"left", "right", "up", "down",
                 "left_up", "right_up", "left_down", "right_down"}
        if direction not in valid:
            raise ValueError(f"direction must be one of {valid}")
        if not 1 <= speed <= 10:
            raise ValueError("speed must be 1..10")
        return self._get("/ptz_ctrl/move",
                         direction=direction, speed=speed, autostop=autostop_ms)

    def stop(self) -> dict:
        return self._get("/ptz_ctrl/stop")

    def preset(self, method: str, no: int) -> dict:
        if method not in ("set", "call", "delete"):
            raise ValueError("method must be 'set', 'call', or 'delete'")
        if not 1 <= no <= 255:
            raise ValueError("preset no must be 1..255")
        return self._get("/ptz_ctrl/preset", method=method, presetno=no)

    def advfunction_exec(self, functionname: str) -> dict:
        return self._get("/ptz_ctrl/advfunction/exec", functionname=functionname)

    # ─── 스냅샷 ────────────────────────────────────────────────

    def snapshot_bytes(self) -> bytes:
        """720×480 JPEG bytes (메인 스트림이 아닌 서브 해상도)."""
        url = f"{self.base_url}/snapshot.cgi"
        params = {"uid": self._uid} if self._uid else {
            "username": self.username, "password": md5_hex(self.password)
        }
        try:
            r = self._session.get(url, params=params, timeout=self.timeout)
            r.raise_for_status()
        except requests.RequestException as e:
            raise StreamError(f"snapshot: {e}") from e
        if not r.content.startswith(b"\xff\xd8"):
            raise StreamError(f"snapshot: not JPEG (head={r.content[:10]!r})")
        return r.content

    def snapshot(self, path: str) -> int:
        """JPEG을 파일로 저장. 반환: 저장된 바이트 수."""
        data = self.snapshot_bytes()
        with open(path, "wb") as f:
            f.write(data)
        return len(data)

    # ─── Admin 전용 (raw, facade를 통해서만 호출) ─────────────

    def _set_video_config(self, full_list: list[dict]) -> dict:
        """주의: 인코딩 변경. AdminFacade에서만 호출."""
        return self._put("/system/video/set", full_list)

    def _set_osd_full(self, osd_dict: dict) -> dict:
        """주의: OSD 전체 설정 변경. AdminFacade에서만 호출."""
        return self._put("/system/osd/set", osd_dict)

    def _reboot(self) -> dict:
        """주의: 카메라 재부팅 (~30~60s downtime). AdminFacade에서만 호출."""
        return self._get("/sysman/reboot")

    # 공장 초기화는 의도적으로 미구현. 필요 시 직접 HAPI 호출:
    # GET /HAPI/V1.0/sysman/factory?uid=<SID>
    # 모든 설정이 초기화되고 IP 까지 재할당된다. 라이브러리에 노출하지 않음.

    # ─── 컨텍스트 매니저 ─────────────────────────────────────

    def __enter__(self) -> "ControlClient":
        self.login()
        return self

    def __exit__(self, *args: Any) -> None:
        self.logout()
