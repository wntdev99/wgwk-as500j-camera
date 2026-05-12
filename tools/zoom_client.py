#!/usr/bin/env python3
"""
zoom_client.py — MC800S5 (WGWK-AS500J 8MP) HAPI 클라이언트.

본 모듈의 실측 capability(`docs/06-live-probe-result.md`)에 맞춘 경량 래퍼.
- HTTP HAPI 1.5 인증(Session ID 60초, 30초 주기 keep_alive)
- 줌/포커스/이리스/PTZ move/프리셋/고급기능 호출
- RTSP URL 조회 및 ffplay/ffmpeg 명령 출력
- CLI 진입점 — 단독 실행으로 즉시 검증 가능

요구 사항: Python 3.10+, requests
설치: pip install requests
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shlex
import sys
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator

import requests


# 본 펌웨어(MC800S5 V3.4.5.2) 실측 정보 — 검증된 기본값
DEFAULT_HOST = "192.168.8.213"
DEFAULT_PORT = 80
DEFAULT_USER = "admin"
DEFAULT_PASS = "123456"
KEEPALIVE_INTERVAL_SEC = 30  # HAPI 1.5 §1.5.2: 60초 만료. 30초 주기로 안전 마진
HTTP_TIMEOUT_SEC = 5


class CameraError(RuntimeError):
    """카메라가 반환한 ResponseCode != 0 또는 통신 실패."""


@dataclass
class CameraClient:
    """HAPI 기반 카메라 제어 클라이언트.

    Usage:
        with CameraClient("192.168.8.213") as cam:
            cam.zoom("in", autostop_ms=500)
            print(cam.rtsp_urls())
    """

    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    username: str = DEFAULT_USER
    password: str = DEFAULT_PASS
    timeout: float = HTTP_TIMEOUT_SEC

    uid: str | None = field(default=None, init=False)
    _stop_event: threading.Event = field(default_factory=threading.Event, init=False)
    _keepalive_thread: threading.Thread | None = field(default=None, init=False)
    _session: requests.Session = field(default_factory=requests.Session, init=False)

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}/HAPI/V1.0"

    @property
    def password_md5(self) -> str:
        return hashlib.md5(self.password.encode()).hexdigest()

    # ─── 세션 ───────────────────────────────────────────────

    def login(self) -> str:
        """uid(Session ID) 발급 + keep_alive 스레드 시작."""
        data = self._raw_get(
            "/uid/getuid",
            params={"username": self.username, "password": self.password_md5},
        )
        sid = data["Response"]["SessionID"]
        if not sid:
            raise CameraError("Empty SessionID — 인증 실패 가능성 확인")
        self.uid = sid
        self._start_keepalive()
        return sid

    def logout(self) -> None:
        self._stop_event.set()
        if self._keepalive_thread is not None:
            self._keepalive_thread.join(timeout=2)
        self.uid = None

    def _start_keepalive(self) -> None:
        if self._keepalive_thread and self._keepalive_thread.is_alive():
            return
        self._stop_event.clear()
        t = threading.Thread(target=self._keepalive_loop, daemon=True, name="cam-keepalive")
        t.start()
        self._keepalive_thread = t

    def _keepalive_loop(self) -> None:
        while not self._stop_event.wait(KEEPALIVE_INTERVAL_SEC):
            if self.uid is None:
                return
            try:
                self._raw_get("/uid/keep_alive", params={"uid": self.uid})
            except (requests.RequestException, CameraError):
                pass  # 잠시 끊긴 거면 다음 주기에 복구 시도

    # ─── HTTP 헬퍼 ──────────────────────────────────────────

    def _raw_get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        resp = self._session.get(url, params=params, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()
        r = data.get("Response", {})
        if r.get("ResponseCode") != 0:
            raise CameraError(
                f"{path}: code={r.get('ResponseCode')} msg={r.get('ResponseString')}"
            )
        return data

    def _call(self, path: str, **params: Any) -> dict[str, Any]:
        if self.uid is None:
            raise CameraError("not logged in — call login() first")
        params["uid"] = self.uid
        return self._raw_get(path, params)["Response"].get("Data", {})

    # ─── 시스템 정보 ─────────────────────────────────────────

    def device_info(self) -> dict[str, Any]:
        return self._call("/sysinfo/device_info")

    def capability(self) -> list[str]:
        data = self._call("/sysinfo/capability")
        return sorted({entry["caps"] for entry in data})

    def function_list(self) -> list[str]:
        data = self._call("/sysinfo/functionlist")
        return sorted({entry["api"] for entry in data})

    def rtsp_urls(self) -> dict[str, str]:
        return self._call("/sysinfo/rtspurl")

    def video_config(self) -> list[dict[str, Any]]:
        return self._call("/system/video/get")

    # ─── PTZ / 줌 ────────────────────────────────────────────

    def zoom(self, direction: str, autostop_ms: int = 0) -> dict[str, Any]:
        """direction: 'in' | 'out'.  autostop_ms: 0=무한, 1~1000(>1000은 펌웨어가 1000으로 클램프)."""
        if direction not in ("in", "out"):
            raise ValueError("direction must be 'in' or 'out'")
        return self._call("/ptz_ctrl/zoom", direction=direction, autostop=autostop_ms)

    def focus(self, direction: str, autostop_ms: int = 0) -> dict[str, Any]:
        if direction not in ("near", "far"):
            raise ValueError("direction must be 'near' or 'far'")
        return self._call("/ptz_ctrl/focus", direction=direction, autostop=autostop_ms)

    def iris(self, direction: str, autostop_ms: int = 0) -> dict[str, Any]:
        if direction not in ("open", "close"):
            raise ValueError("direction must be 'open' or 'close'")
        return self._call("/ptz_ctrl/iris", direction=direction, autostop=autostop_ms)

    def move(self, direction: str, speed: int = 5, autostop_ms: int = 0) -> dict[str, Any]:
        valid = {"left", "right", "up", "down", "left_up", "right_up", "left_down", "right_down"}
        if direction not in valid:
            raise ValueError(f"direction must be one of {valid}")
        if not 1 <= speed <= 10:
            raise ValueError("speed must be 1..10")
        return self._call("/ptz_ctrl/move", direction=direction, speed=speed, autostop=autostop_ms)

    def stop(self) -> dict[str, Any]:
        return self._call("/ptz_ctrl/stop")

    def preset(self, method: str, presetno: int) -> dict[str, Any]:
        if method not in ("set", "call", "delete"):
            raise ValueError("method must be 'set', 'call', or 'delete'")
        if not 1 <= presetno <= 255:
            raise ValueError("presetno must be 1..255")
        return self._call("/ptz_ctrl/preset", method=method, presetno=presetno)

    def advfunction_list(self) -> list[str]:
        data = self._call("/ptz_ctrl/advfunction/get")
        return [entry["functionname"] for entry in data]

    def advfunction_exec(self, functionname: str) -> dict[str, Any]:
        return self._call("/ptz_ctrl/advfunction/exec", functionname=functionname)

    # ─── 컨텍스트 매니저 ─────────────────────────────────────

    def __enter__(self) -> "CameraClient":
        self.login()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.logout()


# ─── 보조 ────────────────────────────────────────────────────

def rtsp_url_with_auth(client: CameraClient, key: str = "ch0_main") -> str:
    """카메라가 알려준 RTSP URL에 admin/pw를 주입.

    이 펌웨어는 /sysinfo/rtspurl 응답에 자격증명을 포함하지 않으나, RTSP DESCRIBE 시
    필요할 수 있으므로 'rtsp://user:pw@host:port/path' 형태로 변환.
    """
    urls = client.rtsp_urls()
    raw = urls[key]  # 예: 'rtsp://192.168.8.213:554/stream0'
    if "@" in raw:
        return raw
    scheme, rest = raw.split("://", 1)
    return f"{scheme}://{client.username}:{client.password}@{rest}"


@contextmanager
def quick_session(args: argparse.Namespace) -> Iterator[CameraClient]:
    cam = CameraClient(host=args.host, port=args.port, username=args.user, password=args.password)
    try:
        cam.login()
        yield cam
    finally:
        cam.logout()


# ─── CLI ─────────────────────────────────────────────────────

def cmd_info(args: argparse.Namespace) -> int:
    with quick_session(args) as cam:
        payload = {
            "device_info": cam.device_info(),
            "rtsp_urls": cam.rtsp_urls(),
            "video_config": cam.video_config(),
            "advfunction": cam.advfunction_list(),
            "capability_count": len(cam.capability()),
            "capability_zoom_keys": [c for c in cam.capability() if any(
                k in c.lower() for k in ("zoom", "ptz", "af_setting", "dzoom")
            )],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_caps(args: argparse.Namespace) -> int:
    with quick_session(args) as cam:
        for c in cam.capability():
            print(c)
    return 0


def cmd_zoom(args: argparse.Namespace) -> int:
    with quick_session(args) as cam:
        print(cam.zoom(args.direction, autostop_ms=args.autostop))
    return 0


def cmd_focus(args: argparse.Namespace) -> int:
    with quick_session(args) as cam:
        print(cam.focus(args.direction, autostop_ms=args.autostop))
    return 0


def cmd_move(args: argparse.Namespace) -> int:
    with quick_session(args) as cam:
        print(cam.move(args.direction, speed=args.speed, autostop_ms=args.autostop))
    return 0


def cmd_stop(args: argparse.Namespace) -> int:
    with quick_session(args) as cam:
        print(cam.stop())
    return 0


def cmd_preset(args: argparse.Namespace) -> int:
    with quick_session(args) as cam:
        print(cam.preset(args.method, args.no))
    return 0


def cmd_rtsp(args: argparse.Namespace) -> int:
    """RTSP URL 출력 + ffplay/ffmpeg 명령 제안."""
    with quick_session(args) as cam:
        urls = cam.rtsp_urls()
        for key, url in urls.items():
            print(f"# {key}")
            print(url)
        main = rtsp_url_with_auth(cam, "ch0_main")
        sub = rtsp_url_with_auth(cam, "ch0_sub")
        print()
        print("# 라이브뷰 (메인 4K HEVC):")
        print(shlex.join(["ffplay", "-fflags", "nobuffer", "-flags", "low_delay",
                          "-rtsp_transport", "tcp", main]))
        print("# 라이브뷰 (서브, 저지연):")
        print(shlex.join(["ffplay", "-fflags", "nobuffer", "-rtsp_transport", "tcp", sub]))
        print("# 30초 무손실 녹화:")
        print(shlex.join(["ffmpeg", "-rtsp_transport", "tcp", "-i", main,
                          "-t", "30", "-c", "copy", "capture.mp4"]))
    return 0


def cmd_selftest(args: argparse.Namespace) -> int:
    """비파괴 자가 점검 — 카메라를 물리적으로 움직이지 않음."""
    ok = True
    with quick_session(args) as cam:
        print("[1/5] device_info")
        info = cam.device_info()
        print(f"  device_type={info.get('device_type')} fs={info.get('fsversion')}")

        print("[2/5] capability (줌/PTZ/AF 키)")
        zoom_keys = [c for c in cam.capability() if any(
            k in c.lower() for k in ("zoom", "ptz", "af_setting", "dzoom")
        )]
        for k in zoom_keys:
            print(f"  - {k}")
        if "ptz_zoom" not in zoom_keys:
            print("  ! ptz_zoom 없음 — 줌 명령이 거부될 수 있음", file=sys.stderr)
            ok = False

        print("[3/5] rtsp_urls")
        for key, url in cam.rtsp_urls().items():
            print(f"  {key}: {url}")

        print("[4/5] video config")
        for stream in cam.video_config():
            print(f"  stream{stream['streamID']}: "
                  f"{'on' if stream['enable'] else 'off'} "
                  f"{stream['encodeFormat']} {stream['resolution']} "
                  f"@{stream['frameRate']}fps "
                  f"{stream['bitRate']}kbps")

        print("[5/5] advfunction")
        for name in cam.advfunction_list():
            print(f"  - {name}")

    print()
    print("✓ selftest passed" if ok else "✗ selftest detected anomalies")
    return 0 if ok else 1


def cmd_zoom_demo(args: argparse.Namespace) -> int:
    """줌 in 1초 → out 1초 → stop 시퀀스. RTSP 뷰어로 화각 변화 관찰용."""
    with quick_session(args) as cam:
        print("zoom in 1000ms ...")
        cam.zoom("in", autostop_ms=1000)
        time.sleep(args.dwell)
        print("zoom out 1000ms ...")
        cam.zoom("out", autostop_ms=1000)
        time.sleep(args.dwell)
        print("stop")
        cam.stop()
    print("done. RTSP 뷰어에서 화각 변화를 확인하세요.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="zoom_client", description=__doc__)
    p.add_argument("--host", default=DEFAULT_HOST)
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.add_argument("--user", default=DEFAULT_USER)
    p.add_argument("--password", default=DEFAULT_PASS)

    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("info", help="요약 정보 JSON 출력").set_defaults(func=cmd_info)
    sub.add_parser("caps", help="전체 capability 리스트 출력").set_defaults(func=cmd_caps)
    sub.add_parser("rtsp", help="RTSP URL과 ffplay/ffmpeg 명령 출력").set_defaults(func=cmd_rtsp)
    sub.add_parser("selftest", help="비파괴 자가 점검(움직이지 않음)").set_defaults(func=cmd_selftest)

    z = sub.add_parser("zoom", help="줌 in/out")
    z.add_argument("direction", choices=["in", "out"])
    z.add_argument("--autostop", type=int, default=500, help="ms (0=무한, ≤1000)")
    z.set_defaults(func=cmd_zoom)

    f = sub.add_parser("focus", help="포커스 near/far")
    f.add_argument("direction", choices=["near", "far"])
    f.add_argument("--autostop", type=int, default=200)
    f.set_defaults(func=cmd_focus)

    m = sub.add_parser("move", help="PTZ 회전")
    m.add_argument("direction",
                   choices=["left", "right", "up", "down",
                            "left_up", "right_up", "left_down", "right_down"])
    m.add_argument("--speed", type=int, default=5)
    m.add_argument("--autostop", type=int, default=500)
    m.set_defaults(func=cmd_move)

    sub.add_parser("stop", help="모든 PTZ 정지").set_defaults(func=cmd_stop)

    pre = sub.add_parser("preset", help="프리셋 set/call/delete")
    pre.add_argument("method", choices=["set", "call", "delete"])
    pre.add_argument("no", type=int, help="1..255")
    pre.set_defaults(func=cmd_preset)

    demo = sub.add_parser("zoom-demo", help="in→out→stop 1초 시퀀스(라이브뷰와 함께 사용)")
    demo.add_argument("--dwell", type=float, default=1.2)
    demo.set_defaults(func=cmd_zoom_demo)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except CameraError as e:
        print(f"[CameraError] {e}", file=sys.stderr)
        return 2
    except requests.RequestException as e:
        print(f"[HTTPError] {e}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
