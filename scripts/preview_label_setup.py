"""LUT 캘리브레이션 전 송장 위치 확인용 snapshot 캡처.

KF 1, 6, 12, 18, 24, 30, 36 의 7개 zoom 위치에서 snapshot을 저장.
사용자가 각 파일을 열어보고 송장 위치/크기를 확인 후 캘리브레이션 진행.

저장 위치: /tmp/lut_setup/setup_kf{N}.jpg
"""
from __future__ import annotations
import sys, time, os
sys.path.insert(0, "/home/jeongmin/Downloads/optical_zoom/src")

from wgwk_camera import Camera

CAM_IP = "192.168.8.101"
KFS = [1, 6, 12, 18, 24, 30, 36]
OUTDIR = "/tmp/lut_setup"


def main():
    os.makedirs(OUTDIR, exist_ok=True)
    print(f"[setup] connecting to {CAM_IP}")
    with Camera(CAM_IP) as cam:
        print("[setup] anchor_wide (모든 측정의 기준)…")
        cam.anchor_wide()
        time.sleep(1.0)
        print(f"  zoom_level={cam.zoom_level}")

        # focus는 AF가 이미 off, 사용자가 setup 보기에 적당한 위치로 한번 sweep
        # 단 sweep은 너무 오래 걸리니 focus는 그냥 'far' 방향으로 12회 → 중간
        print("[setup] focus 중간 위치로 이동 (focus_near 6회)…")
        for _ in range(6):
            cam.focus_near(500)
        time.sleep(0.5)
        for _ in range(6):
            cam.focus_far(500)
        time.sleep(0.5)

        for i, target_kf in enumerate(KFS):
            current = cam.zoom_level
            delta = target_kf - current
            print(f"\n[step {i+1}/{len(KFS)}] zoom to KF {target_kf} (Δ={delta:+.1f})")
            if abs(delta) > 0.3:
                if delta > 0:
                    ms = int(delta * cam._zoom.ms_per_kf)
                    if target_kf >= 35.5:
                        cam.anchor_tele()
                    else:
                        cam.zoom_in(min(ms, 4500))
                else:
                    ms = int(-delta * cam._zoom.ms_per_kf)
                    if target_kf <= 1.5:
                        cam.anchor_wide()
                    else:
                        cam.zoom_out(min(ms, 4500))
            time.sleep(1.5)

            out = f"{OUTDIR}/setup_kf{target_kf:02d}.jpg"
            try:
                cam.snapshot(out)
                size = os.path.getsize(out)
                print(f"  saved {out} ({size/1024:.0f} KB)")
            except Exception as e:
                print(f"  snapshot failed: {e}")

        print(f"\n[done] snapshots saved to {OUTDIR}/")
        print("       다음 명령으로 이미지 보기:")
        print(f"         xdg-open {OUTDIR}/  # 또는 파일 매니저로 열기")
        print("       송장이 KF 18에서 30~50%, KF 36에서 80~100% 차도록 위치 조정")


if __name__ == "__main__":
    main()
