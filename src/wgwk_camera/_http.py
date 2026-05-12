"""HAPI / SCF 공통 HTTP 헬퍼.

라이브러리 사용자는 직접 import하지 않는다. 모듈 이름이 underscore로 시작.
"""
from __future__ import annotations

import hashlib
from typing import Any

import requests

from .exceptions import AuthError, CameraError


DEFAULT_TIMEOUT_SEC = 5.0


def md5_hex(text: str) -> str:
    """admin/password 평문 → 32자 hex MD5 (HAPI 인증용)."""
    return hashlib.md5(text.encode()).hexdigest()


def hapi_check(resp_json: dict[str, Any], endpoint: str) -> dict[str, Any]:
    """HAPI 응답을 검사하고 Response.Data를 반환.

    Raises:
        AuthError: ResponseCode 인증 실패류
        CameraError: 그 외 ResponseCode != 0
    """
    r = resp_json.get("Response", {})
    code = r.get("ResponseCode")
    if code == 0:
        return r.get("Data", {})
    msg = r.get("ResponseString", "<no message>")
    if isinstance(msg, str) and any(t in msg.lower() for t in ("auth", "login", "user")):
        raise AuthError(f"{endpoint}: code={code} msg={msg}")
    raise CameraError(f"{endpoint}: code={code} msg={msg}")


def http_session() -> requests.Session:
    """단일 카메라와의 통신용 requests.Session."""
    s = requests.Session()
    # HAPI/SCF 모두 단기 연결이지만 keep-alive로 latency 절약
    s.headers.update({"Accept": "application/json, text/xml, */*"})
    return s
