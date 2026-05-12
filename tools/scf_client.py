#!/usr/bin/env python3
"""
scf_client.py — MC800S5 SCF API 클라이언트.

웹 UI가 사용하는 비공식 SOAP 채널 — HAPI에 없는 기능(줌 배율 read, WDR, 셔터,
DNR, HLC, 게인, 화이트밸런스 등)을 제공한다. 자세한 명세는 docs/07-scf-api.md.

요구 사항: Python 3.10+, requests
설치: pip install requests

토큰 발급:
  웹 UI(http://CAM/) 로그인 후 크롬 DevTools(F12 → Network)에서 setPTZCmd 등
  POST 요청의 body에서 <userid>...</userid><passwd>...</passwd> 16-hex 문자열을
  추출. 환경변수 SCF_USERID, SCF_PASSWD 로 보관하거나 CLI 인자로 전달.

CLI 사용:
  export SCF_USERID=52851dbd7918bbae
  export SCF_PASSWD=a17faccd02661e4c

  python3 tools/scf_client.py get-zoom
  python3 tools/scf_client.py zoom-step in        # zoomtele + stop 1회
  python3 tools/scf_client.py get-image
  python3 tools/scf_client.py set-image brightness=200 contrast=140
  python3 tools/scf_client.py get-af
  python3 tools/scf_client.py preset-list
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time
from dataclasses import dataclass, field
from typing import Any

import requests


DEFAULT_HOST = "192.168.8.213"
DEFAULT_PORT = 80
HTTP_TIMEOUT_SEC = 5

# 채널 진입의 핵심 — text/xml이면 표준 ONVIF 처리기로 분기되어 실패함
_CONTENT_TYPE = "application/x-www-form-urlencoded"

# Capture 속성의 안전한 기본 키 순서 (응답에서 본 순서와 일치)
CAPTURE_FIELDS = [
    "Brightness", "Contrast", "Saturation", "Sharpness", "TVSystem",
    "forct_antiflicker", "cropxpix", "cropypix", "HFlip", "VFlip", "rotate",
    "WB_RGB", "BackLight", "HLC", "TNF", "SNF", "IrcutMode", "IrcutSensitivity",
    "IrcutOpenLedDelay", "led_brightness_mode", "led_brightness_value",
    "led_brightness_alarm", "IrcutNightStartTime", "IrcutNightEndTime",
    "IrcutKeepColor", "led_mode", "ispadvmode", "bManualGain", "gainValue",
    "WDRMode", "WDRValue", "DfrogFlag", "DfrogValue", "WDRStartTime",
    "WDREndTime", "shutter_mode", "shutter_mode_night", "shutter_speed_day",
    "shutter_speed_night", "isp_mode_color", "isp_mode_night",
    "videoEncodeMode", "aov_mode", "aov_fps", "light_off_sensitivity",
    "face_exposure_sensitivity",
]


class SCFError(RuntimeError):
    """SCF SOAP 호출 실패 (HTTP non-2xx, 또는 응답 파싱 실패)."""


@dataclass
class SCFClient:
    """MC800S5 SCF 채널 클라이언트.

    Usage:
        with SCFClient(host="192.168.8.213",
                       userid="52851dbd7918bbae",
                       passwd="a17faccd02661e4c") as scf:
            print(scf.get_zoom())          # {'current': 1.9, 'max': 10.0}
            scf.zoom_step("in", duration_ms=500)
            cfg = scf.get_image()          # dict of Capture attrs
            scf.set_image(Brightness=200)
    """

    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    userid: str = ""
    passwd: str = ""
    timeout: float = HTTP_TIMEOUT_SEC
    _session: requests.Session = field(default_factory=requests.Session, init=False)

    def __post_init__(self) -> None:
        if not self.userid:
            self.userid = os.environ.get("SCF_USERID", "")
        if not self.passwd:
            self.passwd = os.environ.get("SCF_PASSWD", "")
        if not (self.userid and self.passwd):
            raise SCFError(
                "SCF userid/passwd가 비어있음. "
                "환경변수 SCF_USERID, SCF_PASSWD를 설정하거나 생성자 인자로 전달. "
                "토큰 추출 방법은 docs/07-scf-api.md §3 참고."
            )

    # ─── HTTP 헬퍼 ─────────────────────────────────────────────

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def _envelope(self, body_inner: str) -> str:
        return (
            '<?xml version="1.0"?>'
            '<soap:Envelope xmlns:soap="http://www.w3.org/2001/12/soap-envelope">'
            f"<soap:Header><userid>{self.userid}</userid><passwd>{self.passwd}</passwd></soap:Header>"
            f"<soap:Body>{body_inner}</soap:Body>"
            "</soap:Envelope>"
        )

    def _post(self, endpoint: str, body_inner: str = "") -> str:
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        resp = self._session.post(
            url,
            data=self._envelope(body_inner),
            headers={"Content-Type": _CONTENT_TYPE},
            timeout=self.timeout,
        )
        # PTZ 명령은 202+빈 바디, get류는 200+XML, ONVIF 분기 시 500+SOAP Fault
        if resp.status_code >= 400:
            raise SCFError(
                f"{endpoint} HTTP {resp.status_code}: {resp.text[:200]}"
            )
        return resp.text

    # ─── XML 파싱 (lxml 의존 없이 정규표현식) ─────────────────

    @staticmethod
    def _attrs(xml: str, tag: str) -> dict[str, str]:
        """첫 매칭 <tag attr1="v1" attr2="v2" .../> 의 속성을 dict로."""
        m = re.search(rf"<{re.escape(tag)}\b([^/>]*)/?>", xml)
        if not m:
            return {}
        return dict(re.findall(r'(\w+)="([^"]*)"', m.group(1)))

    # ─── PTZ / 줌 / AF ─────────────────────────────────────────

    def get_ptz_config(self) -> str:
        """전체 PTZConfig XML 응답을 그대로 반환 (디버깅용)."""
        return self._post("/getPtzConfig")

    def get_zoom(self) -> dict[str, float]:
        """현재 줌 배율과 최대 줌 배율을 반환.

        Returns:
            {'current': 1.9, 'max': 10.0}
        """
        xml = self.get_ptz_config()
        attrs = self._attrs(xml, "DzoomConfig")
        if not attrs:
            raise SCFError("DzoomConfig 노드를 응답에서 찾지 못함")
        return {
            "current": float(attrs.get("multiple_set", "0")),
            "max": float(attrs.get("multiple_max", "0")),
        }

    def get_af(self) -> dict[str, Any]:
        """AF 상태 (enable, type 등)."""
        xml = self.get_ptz_config()
        attrs = self._attrs(xml, "AfConfig")
        if not attrs:
            raise SCFError("AfConfig 노드를 응답에서 찾지 못함")
        return {
            "enable": int(attrs.get("enable", "0")),
            "type": int(attrs.get("type", "0")),
            "send_on_start": int(attrs.get("bSendOnStart", "0")),
            "send_coordinate": int(attrs.get("bSendCoordinate", "0")),
        }

    def ptz_cmd(self, cmd: str) -> None:
        """원시 PTZ cmd 토큰 전송. 응답 없음 (202).

        알려진 cmd: zoomtele, zoomwide, FocusNearAutoOff, FocusFarAutoOff,
        IrisOpenAutoOff, IrisCloseAutoOff, stop.
        """
        self._post("/setPTZCmd", f"<xml><cmd>{cmd}</cmd></xml>")

    def zoom_step(self, direction: str, duration_ms: int = 500) -> None:
        """줌 in/out을 지정 시간(ms) 동안 실행 후 stop.

        Args:
            direction: 'in'(=zoomtele) 또는 'out'(=zoomwide).
            duration_ms: 명령 후 stop까지의 대기 시간.
        """
        if direction == "in":
            self.ptz_cmd("zoomtele")
        elif direction == "out":
            self.ptz_cmd("zoomwide")
        else:
            raise ValueError("direction must be 'in' or 'out'")
        time.sleep(duration_ms / 1000.0)
        self.ptz_cmd("stop")

    def focus_step(self, direction: str, duration_ms: int = 300) -> None:
        """포커스 near/far + stop. AutoOff 변형 사용."""
        if direction == "near":
            self.ptz_cmd("FocusNearAutoOff")
        elif direction == "far":
            self.ptz_cmd("FocusFarAutoOff")
        else:
            raise ValueError("direction must be 'near' or 'far'")
        time.sleep(duration_ms / 1000.0)
        self.ptz_cmd("stop")

    def stop(self) -> None:
        self.ptz_cmd("stop")

    # ─── 미디어 / 이미지 ─────────────────────────────────────

    def get_media_video_config(self) -> str:
        """전체 Video XML (Capture + Encode + Overlay + ... + CodeList)."""
        return self._post("/getMediaVideoConfig")

    def get_image(self) -> dict[str, str]:
        """Capture 노드의 모든 속성을 dict로 반환 (값은 모두 문자열)."""
        xml = self.get_media_video_config()
        attrs = self._attrs(xml, "Capture")
        if not attrs:
            raise SCFError("Capture 노드를 응답에서 찾지 못함")
        return attrs

    def set_image(self, **changes: Any) -> dict[str, str]:
        """Capture 속성을 부분 업데이트.

        1. 현재 전체 Capture를 read
        2. 인자로 받은 키만 덮어쓰기
        3. 전체를 다시 PUT

        Args:
            changes: 변경할 속성. 예) Brightness=200, WDRMode=1.

        Returns:
            업데이트 후 read된 새로운 Capture dict.
        """
        current = self.get_image()
        new = dict(current)
        for key, value in changes.items():
            if key not in CAPTURE_FIELDS:
                raise ValueError(
                    f"unknown Capture field {key!r}; "
                    f"valid fields: {', '.join(CAPTURE_FIELDS)}"
                )
            new[key] = str(value)

        # XML attribute 문자열 빌드 — CAPTURE_FIELDS 순서대로
        attrs = " ".join(f'{k}="{new.get(k, current.get(k, ""))}"' for k in CAPTURE_FIELDS)
        body = (
            f"<Video><Capture {attrs}>"
            '<FishEyeCfg Enable="0" autocrop="0" diameter_ppm="0" center_ppm_x="0" center_ppm_y="0"/>'
            "</Capture></Video>"
        )
        self._post("/setMediaVideoCaptureConfig", body)
        return self.get_image()

    # ─── 프리셋 ─────────────────────────────────────────────

    def get_preset_list(self) -> list[int]:
        """저장된 프리셋 번호 리스트."""
        xml = self._post("/getPresetList")
        return [int(n) for n in re.findall(r"<p>(\d+)</p>", xml)]

    # ─── 컨텍스트 매니저 ────────────────────────────────────

    def __enter__(self) -> "SCFClient":
        return self

    def __exit__(self, *args: Any) -> None:
        self._session.close()


# ─── 고수준 헬퍼 ──────────────────────────────────────────────

def goto_zoom(
    scf: SCFClient,
    target: float,
    *,
    tolerance: float = 0.1,
    step_ms: int = 200,
    max_iter: int = 20,
    poll_after_step_ms: int = 250,
) -> dict[str, Any]:
    """폐루프 절대 줌 배율 도달.

    1. 현재 배율 read
    2. target과의 차이가 tolerance 이내면 종료
    3. 차이 부호에 따라 zoomtele/zoomwide step_ms 실행
    4. 잠시 대기 후 다시 read
    5. max_iter까지 반복

    Returns:
        {'reached': bool, 'final': X.X, 'iterations': N, 'history': [...]}
    """
    history = []
    for i in range(max_iter):
        current = scf.get_zoom()["current"]
        history.append(current)
        delta = target - current
        if abs(delta) <= tolerance:
            return {"reached": True, "final": current, "iterations": i, "history": history}
        scf.zoom_step("in" if delta > 0 else "out", duration_ms=step_ms)
        time.sleep(poll_after_step_ms / 1000.0)
    final = scf.get_zoom()["current"]
    history.append(final)
    return {"reached": False, "final": final, "iterations": max_iter, "history": history}


# ─── CLI ──────────────────────────────────────────────────────

def _print_kv(d: dict[str, Any]) -> None:
    for k, v in d.items():
        print(f"  {k} = {v}")


def cmd_get_zoom(scf: SCFClient, args: argparse.Namespace) -> int:
    z = scf.get_zoom()
    print(f"current: {z['current']}x")
    print(f"max:     {z['max']}x")
    return 0


def cmd_zoom_step(scf: SCFClient, args: argparse.Namespace) -> int:
    before = scf.get_zoom()["current"]
    scf.zoom_step(args.direction, duration_ms=args.ms)
    time.sleep(0.3)
    after = scf.get_zoom()["current"]
    print(f"{before}x -> {after}x  (Δ={after - before:+.2f})")
    return 0


def cmd_goto_zoom(scf: SCFClient, args: argparse.Namespace) -> int:
    print(f"target: {args.target}x")
    result = goto_zoom(scf, args.target, tolerance=args.tolerance,
                      step_ms=args.step_ms, max_iter=args.max_iter)
    print(f"reached={result['reached']}  final={result['final']}x  iters={result['iterations']}")
    print(f"history: {result['history']}")
    return 0 if result["reached"] else 1


def cmd_focus(scf: SCFClient, args: argparse.Namespace) -> int:
    scf.focus_step(args.direction, duration_ms=args.ms)
    print(f"focus {args.direction} {args.ms}ms done")
    return 0


def cmd_stop(scf: SCFClient, args: argparse.Namespace) -> int:
    scf.stop()
    print("stop sent")
    return 0


def cmd_get_image(scf: SCFClient, args: argparse.Namespace) -> int:
    img = scf.get_image()
    if args.keys:
        for k in args.keys:
            print(f"  {k} = {img.get(k, '<missing>')}")
    else:
        _print_kv(img)
    return 0


def cmd_set_image(scf: SCFClient, args: argparse.Namespace) -> int:
    changes: dict[str, Any] = {}
    for assignment in args.assignments:
        if "=" not in assignment:
            print(f"잘못된 형식: {assignment} (key=value 형식 필요)", file=sys.stderr)
            return 2
        k, v = assignment.split("=", 1)
        changes[k] = v
    print(f"applying: {changes}")
    updated = scf.set_image(**changes)
    for k in changes:
        print(f"  {k}: -> {updated.get(k)}")
    return 0


def cmd_get_af(scf: SCFClient, args: argparse.Namespace) -> int:
    _print_kv(scf.get_af())
    return 0


def cmd_preset_list(scf: SCFClient, args: argparse.Namespace) -> int:
    print(scf.get_preset_list())
    return 0


def cmd_dump_ptz(scf: SCFClient, args: argparse.Namespace) -> int:
    print(scf.get_ptz_config())
    return 0


def cmd_dump_media(scf: SCFClient, args: argparse.Namespace) -> int:
    print(scf.get_media_video_config())
    return 0


def cmd_selftest(scf: SCFClient, args: argparse.Namespace) -> int:
    print("[1/4] get_zoom")
    z = scf.get_zoom()
    print(f"  current={z['current']}x  max={z['max']}x")

    print("[2/4] get_af")
    af = scf.get_af()
    print(f"  enable={af['enable']}  type={af['type']}")

    print("[3/4] get_image (4 key fields)")
    img = scf.get_image()
    for k in ("Brightness", "Contrast", "WDRMode", "shutter_mode"):
        print(f"  {k}={img.get(k)}")

    print("[4/4] get_preset_list")
    print(f"  {scf.get_preset_list()}")

    print("\n✓ SCF selftest passed")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="scf_client", description=__doc__)
    p.add_argument("--host", default=DEFAULT_HOST)
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.add_argument("--userid", default=os.environ.get("SCF_USERID", ""),
                   help="16-hex DES userid (env SCF_USERID로 대체 가능)")
    p.add_argument("--passwd", default=os.environ.get("SCF_PASSWD", ""),
                   help="16-hex DES passwd (env SCF_PASSWD)")

    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("selftest", help="비파괴 자가 점검").set_defaults(func=cmd_selftest)
    sub.add_parser("get-zoom", help="현재/최대 줌 배율").set_defaults(func=cmd_get_zoom)

    z = sub.add_parser("zoom-step", help="줌 in/out 1회 (zoomtele/wide + stop)")
    z.add_argument("direction", choices=["in", "out"])
    z.add_argument("--ms", type=int, default=500, help="명령 후 stop까지 ms")
    z.set_defaults(func=cmd_zoom_step)

    g = sub.add_parser("goto-zoom", help="폐루프 절대 배율 도달")
    g.add_argument("target", type=float, help="목표 배율 (예: 2.5)")
    g.add_argument("--tolerance", type=float, default=0.1)
    g.add_argument("--step-ms", type=int, default=200)
    g.add_argument("--max-iter", type=int, default=20)
    g.set_defaults(func=cmd_goto_zoom)

    f = sub.add_parser("focus", help="포커스 near/far + stop")
    f.add_argument("direction", choices=["near", "far"])
    f.add_argument("--ms", type=int, default=300)
    f.set_defaults(func=cmd_focus)

    sub.add_parser("stop", help="PTZ 모든 동작 정지").set_defaults(func=cmd_stop)
    sub.add_parser("get-af", help="AF 상태").set_defaults(func=cmd_get_af)
    sub.add_parser("preset-list", help="프리셋 번호 목록").set_defaults(func=cmd_preset_list)
    sub.add_parser("dump-ptz", help="raw PTZConfig XML").set_defaults(func=cmd_dump_ptz)
    sub.add_parser("dump-media", help="raw Video XML").set_defaults(func=cmd_dump_media)

    gi = sub.add_parser("get-image", help="Capture 속성")
    gi.add_argument("keys", nargs="*", help="특정 필드만 출력 (생략 시 전체)")
    gi.set_defaults(func=cmd_get_image)

    si = sub.add_parser("set-image", help="Capture 속성 부분 업데이트")
    si.add_argument("assignments", nargs="+", metavar="key=value",
                    help="예: Brightness=200 WDRMode=1")
    si.set_defaults(func=cmd_set_image)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        scf = SCFClient(host=args.host, port=args.port,
                        userid=args.userid, passwd=args.passwd)
    except SCFError as e:
        print(f"[init error] {e}", file=sys.stderr)
        return 2
    try:
        return args.func(scf, args)
    except SCFError as e:
        print(f"[SCFError] {e}", file=sys.stderr)
        return 3
    except requests.RequestException as e:
        print(f"[HTTPError] {e}", file=sys.stderr)
        return 4


if __name__ == "__main__":
    sys.exit(main())
