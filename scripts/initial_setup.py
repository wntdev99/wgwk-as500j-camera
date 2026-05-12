#!/usr/bin/env python3
"""카메라 초기 셋업 스크립트.

새 카메라를 받았을 때 또는 운영 환경에 처음 투입할 때 사용. 한 번 실행하면
다음을 자동 처리한다:

1. 도달성 확인 (TCP + HAPI 응답)
2. 디바이스 정보 / 펌웨어 / 능력집 출력
3. 인코딩 프로필 적용 (기본 PRECISION)
4. OSD off
5. (선택) 시간 동기화
6. (선택) 재부팅

기본은 **dry_run=True** 라 카메라엔 어떤 변경도 가하지 않는다. 출력된 diff를
검토한 뒤 `--apply` 플래그로 실제 적용한다.

사용:
    # 1) 도달성과 현재 상태만 보기
    python3 scripts/initial_setup.py --host 192.168.8.101

    # 2) 변경 사항(diff) 미리 보기
    python3 scripts/initial_setup.py --host 192.168.8.101 --profile precision

    # 3) 실제 적용
    python3 scripts/initial_setup.py --host 192.168.8.101 --profile precision --apply

    # 4) 적용 + 재부팅
    python3 scripts/initial_setup.py --host 192.168.8.101 --profile precision --apply --reboot
"""
from __future__ import annotations

import argparse
import json
import sys

from wgwk_camera import (
    ALL_PROFILES,
    Camera,
    CameraError,
    check_reachable,
)


def step(n: int, total: int, title: str) -> None:
    print(f"\n[{n}/{total}] {title}")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--host", default="192.168.8.101", help="카메라 IP")
    p.add_argument("--port", type=int, default=80)
    p.add_argument("--user", default="admin")
    p.add_argument("--password", default="123456")
    p.add_argument("--profile", choices=list(ALL_PROFILES.keys()),
                   help="적용할 인코딩 프로필 (생략 시 상태만 표시)")
    p.add_argument("--apply", action="store_true",
                   help="dry_run=False로 실제 적용")
    p.add_argument("--keep-osd", action="store_true",
                   help="OSD를 끄지 않음 (기본은 끄기)")
    p.add_argument("--reboot", action="store_true",
                   help="적용 끝나면 재부팅 (apply 필요)")
    p.add_argument("--timeout", type=float, default=2.0)
    args = p.parse_args()

    total = 4
    if args.profile:
        total += 1   # 인코딩 단계
    if not args.keep_osd:
        total += 1   # OSD 단계
    if args.reboot and args.apply:
        total += 1   # 재부팅 단계

    # ─── 1) 도달성 (HTTP 80 TCP) ─────────────────────────────
    step(1, total, f"TCP 도달성 확인 ({args.host}:{args.port})")
    try:
        check_reachable(args.host, args.port, timeout=args.timeout)
        print("  ✓ 카메라가 응답합니다.")
    except CameraError as e:
        print(f"  ✗ {e}")
        return 2

    # ─── 2) HAPI 응답 + 디바이스 정보 ────────────────────────
    step(2, total, "HAPI 응답 확인 + 디바이스 정보")
    try:
        cam = Camera(args.host, args.user, args.password,
                     port=args.port, preflight=False)   # 위에서 이미 확인
    except CameraError as e:
        print(f"  ✗ HAPI 로그인 실패: {e}")
        print("  사용자/비밀번호를 확인하거나 출하 기본값(admin/123456)을 시도하세요.")
        return 3

    info = cam.info()
    print(f"  device_type: {info.get('device_type')}")
    print(f"  SN:          {info.get('SN')}")
    print(f"  MAC:         {info.get('ether')}")
    print(f"  fsversion:   {info.get('fsversion')}")

    # ─── 3) 현재 인코딩 ──────────────────────────────────────
    step(3, total, "현재 인코딩 설정")
    for s in cam.get_video_config():
        flag = "ON " if s["enable"] else "off"
        print(f"  stream{s['streamID']}: {flag} "
              f"{s['encodeFormat']:6s} {s['resolution']:10s} "
              f"{s['frameRate']:>3}fps  {s['bitRate']:>5}kbps  GOP {s['gop']}")
    print(f"  OSD enabled: {cam.get_osd_enabled()}")
    print(f"  RTSP main:   {cam.rtsp_urls().get('ch0_main')}")

    # ─── 4) 능력집 요약 ───────────────────────────────────────
    step(4, total, "능력집 (PTZ/줌/AF 관련)")
    caps = cam.capabilities()
    keywords = ("ptz", "zoom", "af_setting", "wdr", "dzoom", "shutter")
    related = [c for c in caps if any(k in c.lower() for k in keywords)]
    for c in related[:20]:
        print(f"  - {c}")
    print(f"  (총 {len(caps)}개 capability)")

    cur = 4

    # ─── 5) 인코딩 프로필 적용 ────────────────────────────────
    if args.profile:
        cur += 1
        profile = ALL_PROFILES[args.profile]
        step(cur, total, f"인코딩 프로필: {profile.name} ({profile.description})")
        diff = cam.admin.apply_encoding_profile(profile, dry_run=not args.apply)
        if not diff:
            print("  ✓ 카메라가 이미 프로필과 동일한 상태")
        else:
            tag = "[적용됨]" if args.apply else "[dry-run]"
            print(f"  {tag} 변경 사항:")
            print(json.dumps({str(k): v for k, v in diff.items()},
                             ensure_ascii=False, indent=4))

    # ─── 6) OSD ──────────────────────────────────────────────
    if not args.keep_osd:
        cur += 1
        step(cur, total, "OSD enable → 0 (깨끗한 영상 프레임)")
        r = cam.admin.apply_osd(enabled=False, dry_run=not args.apply)
        if not r.get("changed"):
            print("  ✓ 이미 OSD off")
        else:
            tag = "[적용됨]" if args.apply else "[dry-run]"
            print(f"  {tag} OSD: {r.get('from')} → {r.get('to')}")

    # ─── 7) 재부팅 ────────────────────────────────────────────
    if args.reboot and args.apply:
        cur += 1
        step(cur, total, "재부팅 (confirm=True)")
        cam.admin.reboot(confirm=True)
        print("  → 30~60초 후 카메라가 다시 응답합니다.")

    cam.close()

    if not args.apply:
        print("\n실제 적용하려면 같은 명령에 `--apply`를 추가하세요.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
