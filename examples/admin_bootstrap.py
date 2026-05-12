#!/usr/bin/env python3
"""1회 카메라 admin 작업 — 인코딩 프로필 + OSD 적용.

기본은 **dry_run=True** 라 카메라에 변경을 가하지 않는다. 출력된 diff를
검토한 뒤 `--apply` 플래그로 실제 적용한다.

사용:
    python3 examples/admin_bootstrap.py
    python3 examples/admin_bootstrap.py --apply
    python3 examples/admin_bootstrap.py --profile robot_vision
    python3 examples/admin_bootstrap.py --reboot           # admin.reboot(confirm=True)
"""
import argparse
import json
import sys

from wgwk_camera import ALL_PROFILES, Camera, PRECISION_PROFILE


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--host", default="192.168.8.213")
    p.add_argument("--profile", default="precision",
                   choices=list(ALL_PROFILES.keys()))
    p.add_argument("--apply", action="store_true",
                   help="dry_run=False로 실제 적용")
    p.add_argument("--osd-off", action="store_true",
                   help="OSD enable=0으로 적용 (profile에 osd_enabled가 있어도 별도 명시)")
    p.add_argument("--reboot", action="store_true",
                   help="apply 끝나면 reboot (confirm=True)")
    args = p.parse_args()

    profile = ALL_PROFILES[args.profile]
    dry_run = not args.apply

    with Camera(args.host) as cam:
        # 1) 인코딩 프로필
        print(f"=== profile: {profile.name} ({profile.description}) ===")
        diff = cam.admin.apply_encoding_profile(profile, dry_run=dry_run)
        if not diff:
            print("  ✓ 카메라가 이미 프로필과 동일한 상태")
        else:
            print(f"  {'[dry-run]' if dry_run else '[applied]'} 차이:")
            print(json.dumps({str(k): v for k, v in diff.items()},
                             ensure_ascii=False, indent=2))

        # 2) OSD
        target_osd = args.osd_off or not profile.osd_enabled
        if target_osd:
            print("\n=== OSD ===")
            r = cam.admin.apply_osd(enabled=False, dry_run=dry_run)
            print(json.dumps(r, ensure_ascii=False))

        # 3) 재부팅 (선택)
        if args.reboot and not dry_run:
            print("\n=== reboot (confirm=True) ===")
            cam.admin.reboot(confirm=True)
            print("재부팅 명령 전송. 30~60초 후 다시 접근 가능.")

    if dry_run:
        print("\n실제 적용하려면 --apply 추가.")


if __name__ == "__main__":
    sys.exit(main())
