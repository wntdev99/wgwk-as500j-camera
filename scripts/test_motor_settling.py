"""HAPI ack 이후 모터 settling time 측정.

`docs/08 §8.H` 후속 검증: HAPI ack ≠ motor 완료. 실제 capture timing 결정용.

측정 방법:
  1. RTSP VideoCapture 열기, AF off
  2. zoom (또는 focus) 명령을 thread로 발사, ack 시각 기록
  3. 명령 발사 시점부터 ~2초간 frame을 continuous capture
  4. frame-to-frame diff (zoom용) 또는 Laplacian variance (focus용)로
     이미지가 변화하는 시간 구간 식별
  5. ack 시점과 "이미지 안정화" 시점의 gap = 추가 settle 필요 시간
"""
from __future__ import annotations
import sys, time, threading
sys.path.insert(0, "/home/jeongmin/Downloads/optical_zoom/src")

import numpy as np
import cv2

from wgwk_camera import Camera

CAM_IP = "192.168.8.101"
CMD_MS = 500
CAPTURE_DURATION_S = 2.5


def measure_motor_event(cam: Camera, cap: cv2.VideoCapture, mode: str, direction: str):
    """모터 명령 발사 후 영상 변화량을 시간순으로 기록.

    mode: 'zoom' or 'focus'
    direction: zoom='in'/'out', focus='near'/'far'
    """
    # buffer flush — 충분히 비워서 이전 motion residue 제거
    for _ in range(45):
        cap.read()

    ack_time = [None]
    cmd_start = time.perf_counter()

    def cmd_worker():
        if mode == "zoom":
            if direction == "in":
                cam.zoom_in(CMD_MS)
            else:
                cam.zoom_out(CMD_MS)
        else:
            if direction == "near":
                cam.focus_near(CMD_MS)
            else:
                cam.focus_far(CMD_MS)
        ack_time[0] = time.perf_counter() - cmd_start

    t = threading.Thread(target=cmd_worker)
    t.start()

    frames = []
    times = []
    while time.perf_counter() - cmd_start < CAPTURE_DURATION_S:
        ok, frame = cap.read()
        if not ok:
            continue
        # downsample for speed
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        small = cv2.resize(gray, (320, 180))
        times.append(time.perf_counter() - cmd_start)
        frames.append(small)
    t.join()

    return ack_time[0], times, frames


def find_motion_window(times: list[float], frames: list[np.ndarray], mode: str,
                       quiet_consec: int = 20):
    """frames에서 motor motion의 시작·종료 시점을 찾음.

    - motion_start: 명령 발사 후 signal이 threshold를 처음 초과한 시점
                    (RTSP buffer + encode latency 포함)
    - motion_end:   signal이 threshold 위로 마지막 spike를 보인 시점
                    그 후 quiet_consec frame 연속 quiet하면 종료로 인정
    - settle = motion_end (motor settles right after last visible motion)

    zoom: frame-to-frame absolute pixel diff
    focus: frame-to-frame pixel diff도 사용 (Laplacian variance가 noisy)
    """
    if len(frames) < quiet_consec + 1:
        return None, None, [], 0.0, 0.0

    if mode == "zoom":
        # pixel diff: zoom은 픽셀을 이동시키므로 frame diff에 민감
        signal = []
        for i in range(1, len(frames)):
            d = float(np.mean(np.abs(frames[i].astype(np.int16) - frames[i-1].astype(np.int16))))
            signal.append(d)
        thr_abs = 5.0
    else:
        # focus: Laplacian variance 변화량 (sharpness가 motor 위치에 따라 변함)
        variances = [float(cv2.Laplacian(f, cv2.CV_64F).var()) for f in frames]
        signal = []
        for i in range(1, len(variances)):
            signal.append(abs(variances[i] - variances[i-1]))
        thr_abs = 5.0  # variance 변화가 5+ 정도이면 motor 운동 중

    tail_start = int(len(signal) * 0.7)
    baseline = float(np.percentile(signal[tail_start:], 50)) if tail_start < len(signal) else 0.0
    threshold = max(baseline * 10.0, thr_abs)

    # motion_start: signal이 처음으로 threshold 초과
    motion_start_idx = None
    for i, s in enumerate(signal):
        if s > threshold:
            motion_start_idx = i
            break

    if motion_start_idx is None:
        return None, None, signal, baseline, threshold

    # motion_end: 마지막 threshold 초과 후 quiet_consec frame 연속 quiet
    motion_end_idx = motion_start_idx
    consec_quiet = 0
    for i in range(motion_start_idx, len(signal)):
        if signal[i] > threshold:
            motion_end_idx = i
            consec_quiet = 0
        else:
            consec_quiet += 1
            if consec_quiet >= quiet_consec:
                break

    motion_start_t = times[motion_start_idx + 1]
    motion_end_t = times[motion_end_idx + 1] if motion_end_idx + 1 < len(times) else times[-1]
    return motion_start_t, motion_end_t, signal, baseline, threshold


def main():
    print(f"[setup] connecting to {CAM_IP}")
    with Camera(CAM_IP) as cam:
        try:
            cam.admin.image.set_af(False)
            print("[setup] AF off")
        except Exception as e:
            print(f"[setup] AF off skip: {e}")

        # anchor wide → 중간 KF
        print("[setup] anchor_wide …")
        cam.anchor_wide()
        cam.zoom_in(2000)
        time.sleep(2.5)
        print(f"  zoom_level={cam.zoom_level:.1f}")

        # RTSP open
        url = cam.video_main().url
        print(f"[setup] RTSP open: {url.split('@')[-1]}")
        cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if not cap.isOpened():
            print("RTSP open failed"); return

        # warm up
        for _ in range(30):
            cap.read()

        tests = [
            ("zoom", "in"),
            ("zoom", "out"),
            ("focus", "near"),
            ("focus", "far"),
        ]
        results = []
        for mode, direction in tests:
            print(f"\n[test] {mode} {direction} {CMD_MS}ms")
            ack_t, times, frames = measure_motor_event(cam, cap, mode, direction)
            motion_start, motion_end, sig, baseline, threshold = find_motion_window(times, frames, mode)
            gap = (motion_end - ack_t) if (motion_end is not None and ack_t is not None) else None
            print(f"  frames captured: {len(frames)}, FPS≈{len(frames)/CAPTURE_DURATION_S:.0f}")
            print(f"  HAPI ack at:     {ack_t*1000:.0f}ms")
            print(f"  signal baseline: {baseline:.3f}  threshold: {threshold:.3f}")
            if motion_start is not None and motion_end is not None:
                duration = motion_end - motion_start
                print(f"  motion start:    {motion_start*1000:.0f}ms (RTSP latency ≈ {(motion_start - ack_t)*1000:+.0f}ms vs ack)")
                print(f"  motion end:      {motion_end*1000:.0f}ms")
                print(f"  motion duration: {duration*1000:.0f}ms")
                print(f"  ack → motion end gap (after-ack settle): {gap*1000:+.0f}ms")
            else:
                print(f"  motion: not detected in window")
            # 전체 signal dump (40ms 단위 정도로 sample)
            print(f"  full signal (every {max(1, len(sig)//50)} frames):")
            stride = max(1, len(sig) // 50)
            for i in range(0, len(sig), stride):
                marker = " *" if sig[i] > threshold else ""
                print(f"    {times[i+1]*1000:5.0f}ms: {sig[i]:7.2f}{marker}")
            results.append((mode, direction, ack_t, motion_start, motion_end, gap))
            time.sleep(2.0)

        cap.release()

        print("\n[summary] HAPI ack → image-stable gap (postive = settle wait, negative = image stable before ack)")
        print(f"  {'test':14s} {'ack (ms)':>10s} {'mstart (ms)':>12s} {'mend (ms)':>10s} {'gap (ms)':>10s}")
        for mode, dir_, ack, mstart, mend, gap in results:
            ack_s = f"{ack*1000:.0f}" if ack else "—"
            ms = f"{mstart*1000:.0f}" if mstart else "—"
            me = f"{mend*1000:.0f}" if mend else "—"
            g = f"{gap*1000:+.0f}" if gap is not None else "—"
            print(f"  {mode+' '+dir_:14s} {ack_s:>10s} {ms:>12s} {me:>10s} {g:>10s}")


if __name__ == "__main__":
    main()
