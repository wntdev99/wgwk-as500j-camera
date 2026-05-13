"""Focus peak vs zoom KF 특성화 — LUT 접근 가능성 검증.

목적:
  - 동일 장면(거리)에서 zoom KF가 변할 때 focus peak step이 어떻게 이동하는지 측정
  - parfocal (peak 고정) vs varifocal (peak이 zoom에 따라 이동) 정량화
  - LUT 1D(거리 고정) 접근의 타당성 평가

방법:
  - 동일 카메라 위치, 동일 장면
  - 3개 zoom KF에서 focus sweep 수행 → 각각의 peak step 기록
  - peak step의 ΔKF 대비 변화량 분석
"""
from __future__ import annotations
import sys, time, json
sys.path.insert(0, "/home/jeongmin/Downloads/optical_zoom/src")

from wgwk_camera import Camera

CAM_IP = "192.168.8.101"
ZOOM_KFS = [1, 18, 36]  # wide, middle, tele
SWEEP_STEPS = 16  # 8s sweep × 3회 = 24s, 전체 ~5분


def main():
    print(f"[setup] connecting to {CAM_IP}")
    results = []
    with Camera(CAM_IP) as cam:
        print("[setup] anchor_wide …")
        cam.anchor_wide()  # 7.6s
        print(f"  zoom_level={cam.zoom_level}")

        for i, target_kf in enumerate(ZOOM_KFS):
            current = cam.zoom_level
            delta_kf = target_kf - current
            print(f"\n[step {i+1}/{len(ZOOM_KFS)}] zoom to KF {target_kf} (Δ={delta_kf:+.1f})")
            if abs(delta_kf) > 0.3:
                if delta_kf > 0:
                    ms = int(delta_kf * cam._zoom.ms_per_kf)
                    print(f"  zoom_in {ms}ms")
                    if ms > 4500:
                        cam.anchor_tele() if target_kf >= cam._zoom.max_kf - 0.5 else cam.zoom_in(ms)
                    else:
                        cam.zoom_in(ms)
                else:
                    ms = int(-delta_kf * cam._zoom.ms_per_kf)
                    print(f"  zoom_out {ms}ms")
                    if ms > 4500:
                        cam.anchor_wide() if target_kf <= cam._zoom.min_kf + 0.5 else cam.zoom_out(ms)
                    else:
                        cam.zoom_out(ms)
            time.sleep(1.5)
            print(f"  zoom_level after move: {cam.zoom_level:.1f}")

            print(f"  focus_sweep_best (steps={SWEEP_STEPS}) …")
            t0 = time.perf_counter()
            sweep_result = cam.focus_sweep_best(
                sweep_steps=SWEEP_STEPS,
                step_ms=500,
                anchor_steps=10,
                anchor_direction="near",
                fine_tune=False,
                af_off=False,  # AF는 외부에서 이미 disabled (SCF 토큰 회피)
                restore_af=False,
            )
            dt = time.perf_counter() - t0
            print(f"  ✓ done in {dt:.1f}s")
            print(f"    peak_step      = {sweep_result.get('peak_step')}")
            print(f"    peak_variance  = {sweep_result.get('peak_var'):.1f}")
            print(f"    sweep_steps    = {SWEEP_STEPS}")
            results.append({
                "zoom_kf_target": target_kf,
                "zoom_kf_actual": cam.zoom_level,
                "peak_step": sweep_result.get("peak_step"),
                "peak_var": sweep_result.get("peak_var"),
                "final_var": sweep_result.get("final_var"),
                "sweep_steps": SWEEP_STEPS,
                "duration_s": dt,
            })

    # 분석
    print("\n[results]")
    print(f"  {'KF target':>10s} {'KF actual':>10s} {'peak step':>10s} {'peak var':>10s}")
    for r in results:
        print(f"  {r['zoom_kf_target']:>10d} {r['zoom_kf_actual']:>10.1f} "
              f"{str(r['peak_step']):>10s} {r['peak_var']:>10.1f}")

    # 저장
    out = "/home/jeongmin/Downloads/optical_zoom/data/focus_lut_characterization.json"
    import os
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as f:
        json.dump({"results": results, "note": "동일 장면, zoom별 focus peak 특성화"}, f, indent=2)
    print(f"\n[saved] {out}")

    # 평가
    print("\n[evaluation]")
    if all(r["peak_step"] is not None for r in results):
        peaks = [r["peak_step"] for r in results]
        spread = max(peaks) - min(peaks)
        if spread <= 1:
            print(f"  peak spread: {spread} step → ≈ parfocal (LUT 매우 단순, 또는 불필요)")
        elif spread <= SWEEP_STEPS // 4:
            print(f"  peak spread: {spread} step (sweep의 {spread/SWEEP_STEPS*100:.0f}%)")
            print(f"  → varifocal but predictable. LUT 1D 적용 가능.")
        else:
            print(f"  peak spread: {spread} step (sweep의 {spread/SWEEP_STEPS*100:.0f}%)")
            print(f"  → strongly varifocal. LUT 필수, 2D(zoom × distance) 고려.")


if __name__ == "__main__":
    main()
