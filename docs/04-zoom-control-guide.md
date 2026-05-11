# 04. 광학 줌 제어 통합 가이드

이 문서는 `WGWK-AS500J` 카메라의 **광학 줌(optical/electric zoom)** 제어를 위한 실용 가이드입니다. 두 제어 경로(HAPI / NETSDK) 모두에 대해 절차·예제 코드·주의사항을 정리합니다.

## 4.1 도입 전 체크리스트

1. **하드웨어 구성 확인** (사양서 §광학 줌 인용)
   - 카메라 본체에 **줌 렌즈(zoom lens)**, **줌 제어 보드(zoom control board)**, **줌 프로그램(zoom program/펌웨어)**이 모두 결합되었는지 벤더에 확인.
   - 본체만 별도 구매했을 경우 광학 줌 미동작.
2. **네트워크 도달성 확인**
   ```bash
   ping <카메라 IP>
   curl "http://<카메라 IP>/HAPI/V1.0/sysinfo/device_info?username=admin&password=<MD5>"
   ```
3. **줌 capability 확인**
   ```bash
   curl "http://<카메라 IP>/HAPI/V1.0/sysinfo/capability?uid=<SessionID>"
   ```
   응답의 `Data` 배열에서 다음 키 중 하나 이상이 있어야 광학 줌 제어가 가능합니다:
   - `"ptz_control"` (PTZ 제어 일반)
   - `"ptz_zoom"` (줌 채널)
   - `"ele_zoom"` (전동 줌)
   - `"zoom_track"` (변배 추적)
   - `"af_setting"` (AF)

   해당 키가 없으면 HAPI `/ptz_ctrl/zoom` 호출은 성공해도 실제 광학 줌이 동작하지 않습니다.

## 4.2 경로 A: HAPI 기반 제어 (권장)

### 4.2.1 세션 발급

```bash
# password는 MD5 해시 권장. "admin" / "123456"의 MD5: e10adc3949ba59abbe56e057f20f883e
SID=$(curl -s "http://192.168.1.202/HAPI/V1.0/uid/getuid?username=admin&password=e10adc3949ba59abbe56e057f20f883e" \
      | python3 -c "import sys,json;print(json.load(sys.stdin)['Response']['SessionID'])")
echo "$SID"   # 예: 3CC2457
```

### 4.2.2 줌 in / out

```bash
# 500ms 확대
curl "http://192.168.1.202/HAPI/V1.0/ptz_ctrl/zoom?direction=in&autostop=500&uid=$SID"

# 200ms 축소
curl "http://192.168.1.202/HAPI/V1.0/ptz_ctrl/zoom?direction=out&autostop=200&uid=$SID"

# autostop 없이 시작 → 별도 stop 호출 필요
curl "http://192.168.1.202/HAPI/V1.0/ptz_ctrl/zoom?direction=in&uid=$SID"
curl "http://192.168.1.202/HAPI/V1.0/ptz_ctrl/stop?uid=$SID"
```

- `autostop` 단위는 **밀리초**. `0` 또는 미지정이면 무한 동작.
- `autostop > 1000`은 디바이스에서 1000ms로 클램프됨(사양서 §2.6.4 명시).

### 4.2.3 포커스(AF가 자동이 아닐 때)

```bash
curl "http://192.168.1.202/HAPI/V1.0/ptz_ctrl/focus?direction=near&autostop=100&uid=$SID"
curl "http://192.168.1.202/HAPI/V1.0/ptz_ctrl/focus?direction=far&autostop=100&uid=$SID"
```

### 4.2.4 줌-프리셋 패턴

특정 화각을 즉시 복원하기 위한 일반적 패턴:

```bash
# 1) 원하는 위치/줌까지 이동
curl "http://192.168.1.202/HAPI/V1.0/ptz_ctrl/move?direction=right&speed=5&autostop=500&uid=$SID"
curl "http://192.168.1.202/HAPI/V1.0/ptz_ctrl/zoom?direction=in&autostop=800&uid=$SID"
curl "http://192.168.1.202/HAPI/V1.0/ptz_ctrl/focus?direction=far&autostop=200&uid=$SID"

# 2) 프리셋 1번으로 저장
curl "http://192.168.1.202/HAPI/V1.0/ptz_ctrl/preset?method=set&presetno=1&uid=$SID"

# 3) 이후 즉시 복원
curl "http://192.168.1.202/HAPI/V1.0/ptz_ctrl/preset?method=call&presetno=1&uid=$SID"

# 4) 프리셋 삭제
curl "http://192.168.1.202/HAPI/V1.0/ptz_ctrl/preset?method=delete&presetno=1&uid=$SID"
```

### 4.2.5 Python 클라이언트 스켈레톤

```python
import hashlib
import time
import threading
import requests

class CameraClient:
    def __init__(self, host, username, password, *, port=80):
        self.base = f"http://{host}:{port}/HAPI/V1.0"
        self.username = username
        self.password_md5 = hashlib.md5(password.encode()).hexdigest()
        self.uid = None
        self._stop_keepalive = threading.Event()
        self._keepalive_thread = None

    def login(self):
        r = requests.get(f"{self.base}/uid/getuid", params={
            "username": self.username,
            "password": self.password_md5,
        }, timeout=5)
        r.raise_for_status()
        resp = r.json()["Response"]
        if resp["ResponseCode"] != 0:
            raise RuntimeError(f"login failed: {resp['ResponseString']}")
        self.uid = resp["SessionID"]
        self._start_keepalive()

    def _start_keepalive(self):
        def loop():
            while not self._stop_keepalive.wait(30):  # 30초 주기(만료 60초)
                try:
                    requests.get(f"{self.base}/uid/keep_alive",
                                 params={"uid": self.uid}, timeout=5)
                except requests.RequestException:
                    pass  # 실패 시 다음 주기 재시도
        self._keepalive_thread = threading.Thread(target=loop, daemon=True)
        self._keepalive_thread.start()

    def logout(self):
        self._stop_keepalive.set()
        self.uid = None

    def _call(self, path, **params):
        params["uid"] = self.uid
        r = requests.get(f"{self.base}{path}", params=params, timeout=5)
        r.raise_for_status()
        return r.json()["Response"]

    # PTZ
    def zoom(self, direction, autostop_ms=0):
        """direction: 'in' | 'out', autostop_ms: 0=무한, 1~1000"""
        return self._call("/ptz_ctrl/zoom",
                          direction=direction, autostop=autostop_ms)

    def focus(self, direction, autostop_ms=0):
        return self._call("/ptz_ctrl/focus",
                          direction=direction, autostop=autostop_ms)

    def move(self, direction, speed=5, autostop_ms=0):
        return self._call("/ptz_ctrl/move",
                          direction=direction, speed=speed, autostop=autostop_ms)

    def stop(self):
        return self._call("/ptz_ctrl/stop")

    def preset(self, method, presetno):
        """method: 'set' | 'call' | 'delete', presetno: 1~255"""
        return self._call("/ptz_ctrl/preset", method=method, presetno=presetno)

    def capability(self):
        return self._call("/sysinfo/capability")

    def rtsp_url(self):
        return self._call("/sysinfo/rtspurl")
```

### 4.2.6 ROS 2 통합 스케치 (wattrobotics 환경 가정)

`std_srvs/srv/SetBool`을 응용하거나 커스텀 메시지로 줌 명령을 받는 노드 예:

```python
# ros2: optical_zoom_camera/optical_zoom_camera_node.py
import rclpy
from rclpy.node import Node
from std_msgs.msg import Int32
from optical_zoom_camera.srv import ZoomControl  # direction:str, autostop_ms:int

class ZoomNode(Node):
    def __init__(self):
        super().__init__('optical_zoom_camera')
        self.declare_parameter('host', '192.168.1.202')
        self.declare_parameter('username', 'admin')
        self.declare_parameter('password', '123456')
        self.cam = CameraClient(
            self.get_parameter('host').value,
            self.get_parameter('username').value,
            self.get_parameter('password').value,
        )
        self.cam.login()
        self.create_service(ZoomControl, '~/zoom', self._zoom_cb)

    def _zoom_cb(self, req, resp):
        try:
            r = self.cam.zoom(req.direction, req.autostop_ms)
            resp.success = (r['ResponseCode'] == 0)
            resp.message = r['ResponseString']
        except Exception as e:
            resp.success = False
            resp.message = str(e)
        return resp

def main():
    rclpy.init()
    rclpy.spin(ZoomNode())
```

## 4.3 경로 B: NETSDK 기반 제어

### 4.3.1 빌드 준비 (aarch64)

```bash
cd ref/NETSDK_LINUX_aarch64_V2.1_2023-07-25/demo

# 1) Makefile 수정: PLATFORM=aarch64, libz는 시스템 의존
sed -i 's/^PLATFORM=x86_64/PLATFORM=aarch64/' Makefile
sed -i 's|../lib/$(PLATFORM)/libz.a|-lz|' Makefile
sed -i 's/^USE_FFMPEG_SO=0/USE_FFMPEG_SO=0/' Makefile  # 그대로 유지

# 2) (선택) 헤더 GBK→UTF-8 변환
for f in ../include/*.h; do
  iconv -f GBK -t UTF-8 "$f" -o "$f.utf8" && mv "$f.utf8" "$f"
done

# 3) 빌드
make
```

> 교차 컴파일 시 `CROSS_COMPILE=aarch64-linux-gnu-` 또는 사용 중인 SBC 툴체인 prefix를 지정.

### 4.3.2 최소 줌 제어 코드

```cpp
#include <unistd.h>
#include <cstdio>
#include "NetSDKDLL.h"

int main() {
    IP_NET_DVR_Init();

    IP_NET_DVR_DEVICEINFO devInfo = {};
    LONG userID = IP_NET_DVR_Login(
        (char*)"192.168.1.202", 80,
        (char*)"admin", (char*)"123456",
        &devInfo);
    if (userID < 0) {
        fprintf(stderr, "login failed: %ld\n", userID);
        return 1;
    }
    IP_NET_DVR_SetAutoReconnect(userID, 1);

    // 방법 1: enum 기반 PTZControl
    IP_NET_DVR_PTZControl(userID, ZOOM_IN_VALUE, /*nTspeed=*/5, /*nSpeed=*/5);
    usleep(500 * 1000);                          // 500ms 동작
    IP_NET_DVR_PTZControl(userID, STOPACTION, 0, 0);

    // 방법 2: XML 기반 PTZControlEx (데모와 동일한 방식)
    const char *xml =
      "<xml>\n"
      "<cmd>zoom_in</cmd>"
      "<panspeed>5</panspeed>"
      "<tiltspeed>5</tiltspeed>"
      "</xml>";
    IP_NET_DVR_PTZControlEx(userID, xml);
    usleep(500 * 1000);
    IP_NET_DVR_PTZControlEx(userID,
        "<xml><cmd>stop</cmd></xml>");

    // 프리셋 저장/호출
    IP_NET_DVR_PTZPreset(userID, SET_PRESET, /*index=*/1);
    // 이후 시점에:
    IP_NET_DVR_PTZPreset(userID, GOTO_PRESET, 1);

    IP_NET_DVR_Logout(userID);
    IP_NET_DVR_Cleanup();
    return 0;
}
```

빌드:
```bash
g++ -DLINUX -DNETSDK -I../include zoom_min.cpp \
    ../lib/aarch64/libNetSDK_no_live555.a \
    ../lib/aarch64/libtinyxml.a \
    ../lib/aarch64/libixml.a \
    -lz -lrt -lpthread \
    -o zoom_min
```

### 4.3.3 PTZ 상태/배율 조회

```cpp
char xmlBuf[4096] = {};
DWORD bytes = 0;
IP_NET_DVR_GetDVRConfig(userID,
    CMD_GET_PTZ_STATUS,   // PTZ 상태(XML)
    /*lChannel=*/0,
    xmlBuf, sizeof(xmlBuf), &bytes);
printf("PTZ status: %.*s\n", (int)bytes, xmlBuf);

// 현재 줌 배율 + 최대 배율
IP_NET_DVR_GetDVRConfig(userID,
    CMD_GET_ZOOM_CFG,
    0, xmlBuf, sizeof(xmlBuf), &bytes);
printf("Zoom cfg: %.*s\n", (int)bytes, xmlBuf);
```

> 응답 XML의 정확한 스키마는 `LINUX NETSDK说明文档.pdf`(중문)와 실기 응답으로 확인 권장.

## 4.4 RTSP 라이브 스트림과 결합

HAPI / NETSDK 모두 라이브 프리뷰는 별도 RTSP 클라이언트에 위임합니다.

### 4.4.1 RTSP URL 조회 (HAPI)

```bash
curl "http://192.168.1.202/HAPI/V1.0/sysinfo/rtspurl?uid=$SID"
# 응답:
# { "Data": {
#     "ch0_main": "rtsp://192.168.1.202:554/stream0",
#     "ch0_sub":  "rtsp://192.168.1.202:554/stream1"
#   } }
```

### 4.4.2 GStreamer로 미리보기

```bash
gst-launch-1.0 \
  rtspsrc location=rtsp://admin:123456@192.168.1.202:554/stream0 latency=200 \
  ! rtph265depay ! h265parse ! avdec_h265 ! autovideosink
```

### 4.4.3 OpenCV에서 줌 + 캡처 연동

```python
import cv2, time
from camera_client import CameraClient  # §4.2.5

cam = CameraClient('192.168.1.202', 'admin', '123456')
cam.login()
rtsp = cam.rtsp_url()['Data']['ch0_main']  # 'rtsp://192.168.1.202:554/stream0'

cap = cv2.VideoCapture(rtsp, cv2.CAP_FFMPEG)

cam.zoom('in', autostop_ms=800)
time.sleep(1.0)

ok, frame = cap.read()
if ok:
    cv2.imwrite('zoomed.jpg', frame)

cap.release()
cam.logout()
```

## 4.5 실패 케이스 및 디버깅

| 증상 | 원인 후보 | 진단 |
|---|---|---|
| `ResponseCode != 0` + "auth" 류 | 인증 실패. 평문 비밀번호 사용 시 `%` 인코딩, 또는 MD5 케이스 불일치 | MD5는 소문자 32자리 사용 |
| `zoom` 응답은 성공인데 화면 변화 없음 | 줌 렌즈/보드 미장착 | `/sysinfo/capability`에 `ele_zoom`·`ptz_zoom` 부재 확인 |
| `autostop=2000`인데 1000ms에서 정지 | 사양상 의도된 동작 | 사양서 §2.6.4 명시(>1000은 1000으로 클램프) |
| `keep_alive` 누락 후 401/세션 만료 | uid 60초 만료 | 30~45초 주기로 `keep_alive` 호출 |
| NETSDK `IP_NET_DVR_RealPlay`가 동작 안 함 | `no_live555` 빌드 한계 | 외부 RTSP 클라이언트 사용 |
| 데모 빌드 실패 — `iconv` 미해결 심볼 | x86_64 빌드에만 `-liconv` 필요 | aarch64 빌드에서는 `-liconv` 제거 |
| 헤더 주석이 깨져 보임 | GBK→ISO-8859 오인 | iconv로 GBK→UTF-8 변환 |

## 4.6 보안 고려

1. **HTTPS 사용**: 능력집에 `with_https`(=`FUNCTION_HTTPS`)가 있으면 https로 전환. 평문 HTTP는 사내망에서만 사용.
2. **MD5 비밀번호도 평문 인증과 등가** — 네트워크를 캡처한 공격자는 그대로 재사용 가능. 따라서 HTTPS 필수, 또는 격리된 VLAN 사용.
3. **기본 계정 변경** — `admin`/`123456`은 출하 기본값일 가능성이 매우 높음(사양서 모든 예제가 `123456`의 MD5 `e10adc3949ba59abbe56e057f20f883e` 사용). 운용 전 반드시 변경.
4. **`/sysman/factory`** 호출은 공장 초기화 — 운영 코드에서는 차단하거나 명시적 confirm 후에만 호출.
5. **세션 토큰 노출** — URL에 `uid`를 두면 액세스 로그/프록시에 남음. 가능하면 PUT + 바디 사용.

## 4.7 다음 단계 권장 작업

1. **실기 도입 후 capability 스냅샷 수집** — `/sysinfo/capability`, `/sysinfo/functionlist`, `/sysinfo/device_info` 응답을 JSON으로 저장해 본 문서와 차이 확인.
2. **줌 배율 측정** — `CMD_GET_ZOOM_CFG`(NETSDK) 또는 별도 HAPI(현재 사양서 1.5에는 부재)로 실시간 배율 측정 가능성 검토. 부재 시 OSD overlay에 배율 표시 옵션 활용.
3. **이벤트 → 자동 줌 트래킹** — `PdAction.auto_zoom_enable`(NETSDK) 또는 HAPI `/smart/objectdetect/set`의 `"auto_zoom_enable": 1`로 객체 검출 시 자동 변배 활성화.
4. **펌웨어 업그레이드 경로 확립** — HAPI에는 별도 업그레이드 API가 없음. NETSDK `IP_NET_DVR_Upgrade()` 또는 ONVIF/벤더 전용 채널 사용 여부 결정.
