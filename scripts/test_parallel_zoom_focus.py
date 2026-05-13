"""HAPI concurrent zoom+focus 명령 검증.

검증 항목:
1. 두 HAPI 명령(zoom, focus)을 threading으로 동시 발사 가능한가
2. wall-clock이 sequential 합이 아닌 max(zoom, focus)에 가까운가
3. 두 모터 모두 실제로 움직이는가 (zoom_level 변화 + AF off 상태 focus 변화)
"""
from __future__ import annotations
import sys, time, threading
sys.path.insert(0, "/home/jeongmin/Downloads/optical_zoom/src")

from wgwk_camera import Camera

CAM_IP = "192.168.8.101"
ZOOM_MS = 500
FOCUS_MS = 500


def run_sequential(cam: Camera, direction_zoom: str, direction_focus: str) -> float:
    t0 = time.perf_counter()
    if direction_zoom == "in":
        cam.zoom_in(ZOOM_MS)
    else:
        cam.zoom_out(ZOOM_MS)
    if direction_focus == "near":
        cam.focus_near(FOCUS_MS)
    else:
        cam.focus_far(FOCUS_MS)
    return time.perf_counter() - t0


def run_parallel(cam: Camera, direction_zoom: str, direction_focus: str) -> tuple[float, float, float]:
    """두 명령을 threading으로 동시 발사.

    Returns:
        (total_wall, zoom_dur, focus_dur)
    """
    zoom_dur = [0.0]
    focus_dur = [0.0]

    def zoom_worker():
        s = time.perf_counter()
        if direction_zoom == "in":
            cam.zoom_in(ZOOM_MS)
        else:
            cam.zoom_out(ZOOM_MS)
        zoom_dur[0] = time.perf_counter() - s

    def focus_worker():
        s = time.perf_counter()
        if direction_focus == "near":
            cam.focus_near(FOCUS_MS)
        else:
            cam.focus_far(FOCUS_MS)
        focus_dur[0] = time.perf_counter() - s

    t0 = time.perf_counter()
    tz = threading.Thread(target=zoom_worker)
    tf = threading.Thread(target=focus_worker)
    tz.start(); tf.start()
    tz.join(); tf.join()
    total = time.perf_counter() - t0
    return total, zoom_dur[0], focus_dur[0]


def main():
    print(f"[setup] connecting to {CAM_IP}")
    with Camera(CAM_IP) as cam:
        # AF off (focus 모터 우리가 제어)
        print("[setup] AF off")
        try:
            cam.admin.image.set_af(False) if hasattr(cam.admin, "image") else None
        except Exception as e:
            print(f"  AF off failed (계속 진행): {e}")

        # anchor wide (기준점)
        print("[setup] anchor_wide …")
        s = time.perf_counter()
        cam.anchor_wide()
        anchor_dur = time.perf_counter() - s
        print(f"  anchor_wide: {anchor_dur:.2f}s, zoom_level={cam.zoom_level}")

        # 약간 zoom in 해두기 (모니터 위치)
        cam.zoom_in(1500)
        time.sleep(2.0)
        z_before = cam.zoom_level
        print(f"  zoom_level before tests: {z_before}")

        # --- Test 1: Sequential (zoom_in → focus_near) ---
        print("\n[test 1] SEQUENTIAL: zoom_in(500ms) → focus_near(500ms)")
        t_seq = run_sequential(cam, "in", "near")
        time.sleep(2.0)
        z_after_seq = cam.zoom_level
        print(f"  wall-clock: {t_seq*1000:.0f}ms, zoom_level: {z_before:.1f} → {z_after_seq:.1f}")

        # --- Test 2: Parallel (zoom_out || focus_far) ---
        print("\n[test 2] PARALLEL: zoom_out(500ms) || focus_far(500ms)")
        z_before2 = cam.zoom_level
        t_par, dz, df = run_parallel(cam, "out", "far")
        time.sleep(2.0)
        z_after_par = cam.zoom_level
        print(f"  wall-clock: {t_par*1000:.0f}ms")
        print(f"  zoom thread: {dz*1000:.0f}ms, focus thread: {df*1000:.0f}ms")
        print(f"  zoom_level: {z_before2:.1f} → {z_after_par:.1f}")

        # --- Test 3: 반복 비교 (3회 each) ---
        print("\n[test 3] 3회 반복 측정")
        seq_times = []
        par_times = []
        for i in range(3):
            # zoom_in 후 focus_near
            t = run_sequential(cam, "in" if i % 2 == 0 else "out", "near" if i % 2 == 0 else "far")
            seq_times.append(t)
            time.sleep(1.5)
            # 반대 방향 parallel
            tp, _, _ = run_parallel(cam, "out" if i % 2 == 0 else "in", "far" if i % 2 == 0 else "near")
            par_times.append(tp)
            time.sleep(1.5)
            print(f"  iter {i+1}: seq={seq_times[-1]*1000:.0f}ms, par={par_times[-1]*1000:.0f}ms")

        seq_avg = sum(seq_times) / len(seq_times) * 1000
        par_avg = sum(par_times) / len(par_times) * 1000
        print(f"\n[result]")
        print(f"  sequential avg: {seq_avg:.0f}ms")
        print(f"  parallel   avg: {par_avg:.0f}ms")
        print(f"  saving:         {seq_avg - par_avg:.0f}ms ({(1 - par_avg/seq_avg)*100:.0f}%)")
        if par_avg < seq_avg * 0.7:
            print("  ✓ 병렬 명령 효과 확인 (≥30% 단축)")
        elif par_avg < seq_avg * 0.9:
            print("  △ 약한 병렬 이득 (개선됨)")
        else:
            print("  ✗ 병렬 이득 없음 (펌웨어 직렬화 의심)")


if __name__ == "__main__":
    main()
