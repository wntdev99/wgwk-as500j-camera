#!/usr/bin/env python3
"""런타임 사용 예시 — 카메라 설정 변경 없음.

전제:
- 카메라는 미리 정밀 검출 프로필(1080P H.264 60fps)로 설정되어 있다고 가정
- OSD는 OFF 상태로 설정되어 있다고 가정
- 환경변수 SCF_USERID / SCF_PASSWD (이미지 설정에만 필요)
"""
from wgwk_camera import Camera


def main():
    with Camera("192.168.8.213") as cam:
        # 1) 디바이스 정보 확인
        info = cam.info()
        print(f"model={info['device_type']}  fs={info['fsversion']}")

        # 2) 현재 인코딩 설정 확인 (read만, 변경 X)
        for s in cam.get_video_config():
            print(f"  stream{s['streamID']}: enable={s['enable']} "
                  f"{s['encodeFormat']} {s['resolution']} "
                  f"{s['frameRate']}fps {s['bitRate']}kbps GOP={s['gop']}")

        # 3) RTSP URL
        urls = cam.rtsp_urls()
        print(f"main: {urls['ch0_main']}")
        print(f"sub:  {urls['ch0_sub']}")

        # 4) 스냅샷 (720x480 JPEG)
        cam.snapshot("/tmp/snap.jpg")

        # 5) 줌 in 500ms → out 500ms
        cam.zoom_in(500)
        cam.zoom_out(500)

        # 6) 프리셋 1번 호출 (사전에 저장되어 있어야 함)
        # cam.preset_call(1)

        # 7) 비디오 캡처 (저지연 RTSP UDP, 메인 1080P)
        # OpenCV 필요: pip install opencv-python
        try:
            with cam.video_main(transport="udp").opencv() as cap:
                for i in range(30):           # 30 프레임만 시연
                    ok, frame = cap.read()
                    if not ok:
                        break
                    print(f"frame {i}: shape={frame.shape}")
        except Exception as e:
            print(f"(video skipped: {e})")


if __name__ == "__main__":
    main()
