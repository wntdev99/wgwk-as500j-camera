#!/usr/bin/env python3
"""카메라 헬스체크 — 운영 중 한 줄로 상태 점검.

확인 항목:
    1. TCP 80 도달성
    2. HAPI 로그인 + device_info
    3. 비디오 인코딩 현재 상태
    4. RTSP stream0 DESCRIBE (별도 의존 없이 socket 레벨)
    5. (선택) snapshot.cgi 1장 받기

종료 코드:
    0: 모두 정상
    2: 도달 불가
    3: 인증 실패
    4: 일부 채널 실패

사용:
    python3 scripts/healthcheck.py --host 192.168.8.101
    python3 scripts/healthcheck.py --host 192.168.8.101 --snapshot /tmp/h.jpg
"""
from __future__ import annotations

import argparse
import socket
import sys

from wgwk_camera import Camera, CameraError, check_reachable


def check_rtsp(host: str, port: int = 554, timeout: float = 2.0) -> bool:
    """RTSP 포트 개방만 빠르게 확인 (DESCRIBE까지는 안 감)."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--host", default="192.168.8.101")
    p.add_argument("--port", type=int, default=80)
    p.add_argument("--user", default="admin")
    p.add_argument("--password", default="123456")
    p.add_argument("--snapshot", metavar="PATH",
                   help="스냅샷도 받아 파일로 저장")
    args = p.parse_args()

    rc = 0
    print(f"target: {args.host}:{args.port}")

    print(" [1] HTTP TCP", end=" ... ", flush=True)
    try:
        check_reachable(args.host, args.port, timeout=2.0)
        print("OK")
    except CameraError as e:
        print(f"FAIL ({e})")
        return 2

    print(" [2] HAPI login", end=" ... ", flush=True)
    try:
        cam = Camera(args.host, args.user, args.password,
                     port=args.port, preflight=False)
    except CameraError as e:
        print(f"FAIL ({e})")
        return 3
    print("OK")

    print(" [3] device_info", end=" ... ", flush=True)
    info = cam.info()
    print(f"{info.get('device_type')} / {info.get('fsversion','').split(' build')[0]}")

    print(" [4] video config", end=" ... ", flush=True)
    streams = cam.get_video_config()
    on = [s for s in streams if s["enable"]]
    print(f"active streams: " +
          ", ".join(f"{s['encodeFormat']} {s['resolution']}@{s['frameRate']}" for s in on))

    print(" [5] RTSP 554 TCP", end=" ... ", flush=True)
    if check_rtsp(args.host, 554):
        print("OPEN")
    else:
        print("CLOSED")
        rc = 4

    print(" [6] OSD enabled", end=" ... ", flush=True)
    osd = cam.get_osd_enabled()
    print(f"{osd}")

    if args.snapshot:
        print(f" [7] snapshot → {args.snapshot}", end=" ... ", flush=True)
        try:
            data = cam.snapshot(args.snapshot)
            print(f"OK ({len(data)} bytes)")
        except CameraError as e:
            print(f"FAIL ({e})")
            rc = 4

    cam.close()
    print(f"\nresult: {'OK' if rc == 0 else f'partial (rc={rc})'}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
