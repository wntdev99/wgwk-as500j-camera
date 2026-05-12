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

    # SCF SET endpoint 명명 패턴: 'set' + 대문자 시작 (setPTZCmd, setMediaVideoCaptureConfig 등)
    _SET_ENDPOINT_RE = re.compile(r"^/?set[A-Z]")

    def _post(self, endpoint: str, body_inner: str = "",
              *, allow_unsafe_empty: bool = False) -> str:
        """SCF SOAP POST.

        본 펌웨어는 `/setXxxConfig`에 빈 body를 보내면 해당 영역을 0/기본값으로
        **silent reset**한다 (응답은 HTTP 202). 실측으로 Capture 19개 필드가
        모두 0으로 망가지는 사고가 발생했으므로 `_post`가 SET endpoint + 빈 body
        조합을 차단한다. 의도적 호출이라면 `allow_unsafe_empty=True`로 명시.
        """
        if (not allow_unsafe_empty
                and not body_inner.strip()
                and self._SET_ENDPOINT_RE.match(endpoint)):
            raise CameraError(
                f"SCF SET endpoint {endpoint!r}에 빈 body 전송 차단됨. "
                f"본 펌웨어에서 SET + empty body는 해당 영역을 0/기본값으로 "
                f"silent reset한다 (예: setMediaVideoCaptureConfig empty → "
                f"Brightness/Contrast/Saturation/Sharpness/WDR/Shutter 등 19개 "
                f"필드 모두 0으로 리셋). 전체 구조체 XML을 body_inner로 전달하거나, "
                f"명시적 의도가 있으면 allow_unsafe_empty=True를 지정하라. "
                f"근거: docs/08-endpoint-probe-2026-05-12.md §A."
            )
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

    def set_af(
        self,
        *,
        enable: bool | None = None,
        af_type: int | None = None,
        send_on_start: bool | None = None,
        send_coordinate: bool | None = None,
    ) -> dict[str, int]:
        """AF 설정 부분 업데이트.

        지정하지 않은 필드는 현재 값을 유지. SCF `/setPtzAfConfig` 사용 — 본문은
        `<AfConfig enable=".." type=".." bSendOnStart=".." bSendCoordinate=".." />`.

        Args:
            enable: True/False면 AF on/off. None이면 현재 값 유지.
            af_type: AF 알고리즘 타입 (펌웨어 의존, 보통 0).
            send_on_start: 카메라 부팅 시 AF 명령 자동 발사.
            send_coordinate: 좌표 정보 전송 여부.

        Returns:
            적용 후 GET back한 새로운 AF 상태.

        Note:
            `enable=False`로 끄면 광학 줌 후 자동 포커싱이 되지 않아 영상이
            흐려질 수 있다. 필요할 때만 사용하고, 작업 후 enable=True로 복원 권장.
        """
        current = self.get_af()
        new = {
            "enable":          1 if enable          is True  else 0 if enable          is False else current["enable"],
            "type":            af_type              if af_type is not None              else current["type"],
            "bSendOnStart":    1 if send_on_start    is True  else 0 if send_on_start    is False else current["send_on_start"],
            "bSendCoordinate": 1 if send_coordinate  is True  else 0 if send_coordinate  is False else current["send_coordinate"],
        }
        body = (
            f'<AfConfig enable="{new["enable"]}" type="{new["type"]}" '
            f'bSendOnStart="{new["bSendOnStart"]}" '
            f'bSendCoordinate="{new["bSendCoordinate"]}" />'
        )
        self._post("/setPtzAfConfig", body)
        return self.get_af()

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

    # ─── 인코딩 (Encode) ─────────────────────────────────────

    # HAPI /system/video/get 응답 필드 ↔ SCF Encode XML 속성 매핑
    _HAPI_TO_SCF_ENCODE = {
        "streamID":       "Stream",
        "enable":         "Enable",
        "encodeFormat":   "EncodeFormat",
        "resolution":     "Resolution",
        "frameRate":      "FrameRate",
        "bitRate":        "BitRate",
        "gop":            "Initquant",   # 펌웨어 명명 — GOP가 Initquant로 매핑
        "bitRateControl": "BitRateControl",
        "bitRateQuality": "BitRateQuality",
        "qp_enable":      "qp_enable",
        "qp_min":         "qp_min",
        "qp_max":         "qp_max",
    }

    def set_video_encoding(self, hapi_streams: list[dict]) -> None:
        """SCF setMediaVideoEncodeConfig로 인코딩 변경.

        HAPI `/system/video/set`은 본 펌웨어에서 응답 없이 끊기며 변경도 적용되지
        않으므로(설계 결정 docs/09 참고), SCF 채널을 사용한다.

        Args:
            hapi_streams: HAPI `/system/video/get` 응답 형식의 list. AdminFacade에서
                현재값과 merge한 결과를 그대로 전달.
        """
        # AdvanceEncodeConfig 블록은 현재값을 그대로 보존
        xml = self.get_media_video_config()
        adv_m = re.search(r'<AdvanceEncodeConfig\b[^/]*/?>', xml, re.DOTALL)
        adv_xml = adv_m.group(0) if adv_m else ""

        # 각 stream을 SCF EncodeConfig XML로 직렬화
        configs: list[str] = []
        for s in hapi_streams:
            attrs: list[str] = []
            for k_hapi, k_scf in self._HAPI_TO_SCF_ENCODE.items():
                if k_hapi in s:
                    attrs.append(f'{k_scf}="{s[k_hapi]}"')
            configs.append("<EncodeConfig " + " ".join(attrs) + "/>")

        body = f"<Video><Encode>{''.join(configs)}{adv_xml}</Encode></Video>"
        self._post("/setMediaVideoEncodeConfig", body)

    # ─── Capture (이미지 설정) ───────────────────────────────

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
