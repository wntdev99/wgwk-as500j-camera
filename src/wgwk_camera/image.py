"""SCF SOAP 기반 이미지 설정 클라이언트.

HAPI가 노출하지 않는 고급 이미지 설정(WDR, 셔터, DNR, HLC, 게인, 화이트밸런스,
Defog, 안티플리커 등)을 제공한다. 인증은 16-hex DES 토큰(`userid`/`passwd`).
자동 발급은 미구현 — 환경변수 `SCF_USERID`/`SCF_PASSWD` 또는 생성자 인자.

자세한 명세: docs/07-scf-api.md
"""
from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field
from typing import Any

import requests

from ._http import DEFAULT_TIMEOUT_SEC, http_session
from .exceptions import AuthError, CameraError


# Capture 노드의 모든 속성. setMediaVideoCaptureConfig PUT 시 전체 페이로드를
# 보내야 하므로 순서대로 보관.
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

# text/xml이면 표준 ONVIF/gSOAP 처리기로 분기되어 실패함 — 반드시 form-urlencoded
_CONTENT_TYPE = "application/x-www-form-urlencoded"


@dataclass
class ImageClient:
    """SCF SOAP 클라이언트.

    모든 메서드는 카메라의 이미지 설정을 다룬다. 인코딩(코덱·해상도·fps)은
    이 클래스의 범위 밖이며, ControlClient + AdminFacade에서 처리한다.

    런타임 메서드:
        get_image / set_image  ← 환경 변화 대응 (의도된 런타임 변경)
        get_zoom / get_af      ← read-only
        get_preset_list

    raw:
        get_ptz_config / get_media_video_config  ← XML 전체
    """

    host: str = "192.168.8.101"
    port: int = 80
    userid: str = ""
    passwd: str = ""
    timeout: float = DEFAULT_TIMEOUT_SEC
    _session: requests.Session = field(default_factory=http_session, init=False)

    def __post_init__(self) -> None:
        if not self.userid:
            self.userid = os.environ.get("SCF_USERID", "")
        if not self.passwd:
            self.passwd = os.environ.get("SCF_PASSWD", "")

    @property
    def is_configured(self) -> bool:
        return bool(self.userid and self.passwd)

    # ─── HTTP / SOAP 헬퍼 ────────────────────────────────────

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def _ensure_auth(self) -> None:
        if not self.is_configured:
            raise AuthError(
                "SCF userid/passwd 미설정. 환경변수 SCF_USERID/SCF_PASSWD 또는 "
                "생성자 인자로 전달. 토큰 추출 방법은 docs/07-scf-api.md §3 참고."
            )

    def _envelope(self, body_inner: str) -> str:
        return (
            '<?xml version="1.0"?>'
            '<soap:Envelope xmlns:soap="http://www.w3.org/2001/12/soap-envelope">'
            f"<soap:Header><userid>{self.userid}</userid><passwd>{self.passwd}</passwd></soap:Header>"
            f"<soap:Body>{body_inner}</soap:Body>"
            "</soap:Envelope>"
        )

    def _post(self, endpoint: str, body_inner: str = "") -> str:
        self._ensure_auth()
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        try:
            r = self._session.post(
                url, data=self._envelope(body_inner),
                headers={"Content-Type": _CONTENT_TYPE}, timeout=self.timeout,
            )
        except requests.RequestException as e:
            raise CameraError(f"SCF POST {endpoint}: {e}") from e
        if r.status_code >= 400:
            raise CameraError(f"SCF {endpoint} HTTP {r.status_code}: {r.text[:200]}")
        return r.text

    @staticmethod
    def _attrs(xml: str, tag: str) -> dict[str, str]:
        m = re.search(rf"<{re.escape(tag)}\b([^/>]*)/?>", xml)
        if not m:
            return {}
        return dict(re.findall(r'(\w+)="([^"]*)"', m.group(1)))

    # ─── PTZ / 줌 / AF read ─────────────────────────────────

    def get_ptz_config(self) -> str:
        return self._post("/getPtzConfig")

    def get_zoom(self) -> dict[str, float]:
        """현재 줌 setpoint와 최대 배율.

        주의: `multiple_set`은 모터 실시간 위치가 아니라 ActiveX 등에서 한 번
        설정된 setpoint이다. HAPI 시간 기반 줌 in/out으로는 갱신되지 않는다.
        """
        xml = self.get_ptz_config()
        attrs = self._attrs(xml, "DzoomConfig")
        if not attrs:
            raise CameraError("DzoomConfig 노드를 응답에서 찾지 못함")
        return {
            "setpoint": float(attrs.get("multiple_set", "0")),
            "max": float(attrs.get("multiple_max", "0")),
        }

    def get_af(self) -> dict[str, int]:
        xml = self.get_ptz_config()
        attrs = self._attrs(xml, "AfConfig")
        if not attrs:
            raise CameraError("AfConfig 노드를 응답에서 찾지 못함")
        return {
            "enable": int(attrs.get("enable", "0")),
            "type": int(attrs.get("type", "0")),
            "send_on_start": int(attrs.get("bSendOnStart", "0")),
            "send_coordinate": int(attrs.get("bSendCoordinate", "0")),
        }

    def get_preset_list(self) -> list[int]:
        xml = self._post("/getPresetList")
        return [int(n) for n in re.findall(r"<p>(\d+)</p>", xml)]

    # ─── 이미지 (Capture) ────────────────────────────────────

    def get_media_video_config(self) -> str:
        return self._post("/getMediaVideoConfig")

    def get_image(self) -> dict[str, str]:
        """현재 Capture 속성을 dict로 반환 (모든 값은 문자열)."""
        xml = self.get_media_video_config()
        attrs = self._attrs(xml, "Capture")
        if not attrs:
            raise CameraError("Capture 노드를 응답에서 찾지 못함")
        return attrs

    def set_image(self, **changes: Any) -> dict[str, str]:
        """Capture 속성 부분 업데이트.

        1. 현재 Capture read
        2. changes로 받은 키만 덮어쓰기
        3. 전체 PUT
        4. read한 결과 반환

        Args:
            **changes: 변경할 속성. 예) `set_image(Brightness=200, WDRMode=1)`.

        Returns:
            업데이트 후의 Capture dict.
        """
        current = self.get_image()
        new = dict(current)
        for key, value in changes.items():
            if key not in CAPTURE_FIELDS:
                raise ValueError(
                    f"unknown Capture field {key!r}; "
                    f"valid: {', '.join(CAPTURE_FIELDS)}"
                )
            new[key] = str(value)

        attrs_str = " ".join(
            f'{k}="{new.get(k, current.get(k, ""))}"' for k in CAPTURE_FIELDS
        )
        body = (
            f"<Video><Capture {attrs_str}>"
            '<FishEyeCfg Enable="0" autocrop="0" diameter_ppm="0" center_ppm_x="0" center_ppm_y="0"/>'
            "</Capture></Video>"
        )
        self._post("/setMediaVideoCaptureConfig", body)
        return self.get_image()
