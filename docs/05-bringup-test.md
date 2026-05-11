# 05. 하드웨어 연결 및 기본 동작 테스트 가이드 (Ubuntu 24.04)

이 문서는 **WGWK-AS500J 계열 8 MP 카메라 모듈**을 처음 수령한 시점에서 하드웨어 결선, 네트워크 도달성, HTTP API(HAPI) 응답, RTSP 라이브 스트림, 광학 줌 동작까지 단계별로 검증하기 위한 브링업(bring-up) 가이드입니다. 테스트 호스트 OS는 **Ubuntu 24.04 LTS**를 가정합니다.

## 0. 사전 인지 — 8 MP 모듈의 변형 가능성

`ref/simple_spec.pdf`의 기준 사양은 **5 MP IMX335**입니다. 지휘관께서 수령하신 모듈은 8 MP 변형이므로 다음 가능성이 있습니다.

| 가능성 | 변경 항목 | 확인 방법 |
|---|---|---|
| 동일 보드 + 다른 센서 | `IMX415`(8 MP 1/2.8") 또는 `IMX678`(8 MP 1/1.8")로 교체 | `/HAPI/V1.0/sysinfo/device_info` 응답의 `model`, `fsversion` |
| 다른 메인보드 | SSC377D 대신 SSC338Q/SSC358Q 등 | 위와 동일 |
| 펌웨어 버전 차이 | HAPI 사양 1.5보다 신/구 버전 | `/HAPI/V1.0/sysinfo/functionlist` |
| 기본 IP·기본 계정 차이 | 출하 기본값 | 벤더 라벨 / 매뉴얼 |

**따라서 실기 확인을 거치기 전까지 5 MP 사양서의 모든 수치를 그대로 신뢰하지 말 것.**

## 1. 박스 인벤토리

사양서 §광학 줌 단서에 따라 본체 단독으로는 줌이 동작하지 않습니다. 박스에 다음 항목이 모두 있는지 먼저 확인합니다.

| 구성품 | 필수 여부 | 비고 |
|---|---|---|
| 카메라 메인보드 | 필수 | DC 12 V 전원 입력 + RJ45 |
| 줌 렌즈 모듈 | 필수 | 없으면 광학 줌 불가 |
| 줌 제어 보드 | 필수 | 없으면 광학 줌 불가 |
| 보광등 보드(IR/백색광) | 선택 | 야간 촬영 시 필요 |
| DC 12 V 어댑터 | 필수 | 사양서 130 mA 기준이지만 여유 있게 **≥ 500 mA** 권장 |
| 이더넷 케이블 | 필수 | Cat 5e 이상 |
| 벤더 매뉴얼/QR 라벨 | 권장 | 기본 IP·기본 계정이 여기에 명시 |

### 벤더에 반드시 확인할 정보 3가지

1. **출하 기본 IP** — `192.168.1.10`, `192.168.1.108`, `192.168.1.202` 등 벤더마다 상이
2. **기본 로그인 계정/비밀번호** — 사양서 예제는 `admin/123456`이나 8 MP 변형은 다를 수 있음
3. **DHCP 활성화 여부** — 출하 기본값으로 DHCP를 켜놓는 모델도 있음

## 2. Ubuntu 24.04 환경 준비

필요한 도구를 한 번에 설치합니다.

```bash
sudo apt update
sudo apt install -y \
    arp-scan nmap iproute2 \
    curl jq python3-pip \
    ffmpeg vlc \
    gstreamer1.0-tools gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad gstreamer1.0-libav \
    wireshark tshark
```

| 도구 | 용도 |
|---|---|
| `arp-scan`, `nmap` | IP 검색 |
| `tshark`, `wireshark` | 카메라가 보내는 브로드캐스트/멀티캐스트 패킷 분석 |
| `ffmpeg`, `vlc`, `gst-launch-1.0` | RTSP 스트림 확인 |
| `curl`, `jq` | HAPI 호출 및 JSON 파싱 |

ONVIF Discovery까지 시도하려면 추가로:

```bash
pip install --user --break-system-packages onvif-zeep wsdiscovery
```

> Ubuntu 24.04는 PEP 668로 시스템 pip 설치를 막으므로 `--break-system-packages` 또는 가상환경 사용. 권장은 `python3 -m venv ~/.venv/cam && source ~/.venv/cam/bin/activate` 후 설치.

## 3. 물리 연결

```
[DC 12 V 어댑터] ──→ 카메라 전원 단자(+/− 극성 주의)
[카메라 RJ45]   ──→ (A) PC 이더넷 포트 직결
                ──→ (B) 같은 LAN의 스위치/라우터
```

| 옵션 | 장점 | 단점 |
|---|---|---|
| **A. 직결** | 외부 네트워크 영향 없음, 패킷 분석 용이 | PC의 두 번째 NIC 또는 USB-Ethernet 어댑터 필요 |
| **B. 라우터 경유** | 추가 어댑터 불필요, 인터넷 동시 사용 | 카메라 IP가 라우터 DHCP에 따라 변동 |

**권장**: 첫 테스트는 **A(직결)** 로 격리. 안정화 후 B로 이전.

### 결선 시 안전 체크

- DC 12 V 어댑터의 극성(+/−)을 카메라 라벨과 일치시킬 것 — 역접속 시 보드 손상
- 어댑터 출력 전류는 사양서 130 mA 기준이지만, 줌 모터 구동·IR LED 동작 시 순간 피크가 더 높으므로 **500 mA 이상** 권장
- 통전 전 모든 커넥터 결합 상태를 한 번 더 확인

## 4. PC 네트워크 설정 (직결 시)

카메라 기본 IP가 `192.168.1.X` 대역이라 가정하고 PC를 같은 서브넷에 임시로 둡니다.

```bash
# 인터페이스 이름 확인
ip -br link
# 예 출력: enp3s0 또는 enx00e04c534xxx(USB-Ethernet)

# 임시 IP 부여 (재부팅 시 사라짐) — 인터페이스 이름은 위 결과로 대체
sudo ip addr add 192.168.1.100/24 dev enp3s0
sudo ip link set enp3s0 up

# 확인
ip addr show enp3s0
```

영구 설정은 `nm-connection-editor` 또는 netplan(`/etc/netplan/*.yaml`)에서 진행. 첫 테스트는 위 임시 명령으로 충분합니다.

## 5. 카메라 IP 발견

벤더 매뉴얼에 적힌 기본 IP가 있으면 그것부터 시도합니다. 모를 경우 다음 순으로 진행:

```bash
# 방법 1: ARP 스캔 (가장 빠름)
sudo arp-scan --interface=enp3s0 192.168.1.0/24

# 방법 2: nmap 포트 스캔 (HTTP/RTSP/ONVIF 포트 확인)
sudo nmap -sn 192.168.1.0/24
sudo nmap -p 80,554,8000,8899,3702 192.168.1.0/24

# 방법 3: 카메라가 보내는 검색 브로드캐스트 캡처
sudo tshark -i enp3s0 -f "broadcast or multicast" -c 50

# 방법 4: ONVIF Discovery (가장 확실)
python3 - <<'PY'
from wsdiscovery.discovery import ThreadedWSDiscovery as WSDiscovery
d = WSDiscovery()
d.start()
services = d.searchServices()
for s in services:
    print("EPR:", s.getEPR())
    print("XAddrs:", s.getXAddrs())
    print("Types:", s.getTypes())
    print("---")
d.stop()
PY
```

사양서가 ONVIF 지원을 명시하므로 **방법 4(ONVIF Discovery)** 의 성공 가능성이 가장 높습니다.

## 6. 기본 동작 검증

### 6.1 핑

```bash
ping -c 4 <카메라 IP>
```

### 6.2 웹 UI 응답 확인

```bash
xdg-open "http://<카메라 IP>/"
```

대부분 IPC는 웹 UI를 갖고 있으나 ActiveX/플러그인 의존이 흔합니다. 가장 확실한 검증은 다음 HAPI 호출입니다.

### 6.3 HAPI로 디바이스 정보 조회

```bash
# 패스워드 MD5 (기본값 가정)
PW_MD5=$(echo -n "123456" | md5sum | awk '{print $1}')
echo "$PW_MD5"   # e10adc3949ba59abbe56e057f20f883e

CAM=<카메라 IP>

# 1) device_info — 모델/펌웨어/MAC 확인 (8 MP 변형 식별 핵심)
curl -s "http://$CAM/HAPI/V1.0/sysinfo/device_info?username=admin&password=$PW_MD5" | jq

# 2) 능력집 — 광학 줌 지원 여부 확인 (핵심)
curl -s "http://$CAM/HAPI/V1.0/sysinfo/capability?username=admin&password=$PW_MD5" \
  | jq '.Response.Data[] | select(.caps | test("zoom|ele_zoom|ptz|af_setting"))'

# 3) RTSP URL
curl -s "http://$CAM/HAPI/V1.0/sysinfo/rtspurl?username=admin&password=$PW_MD5" | jq

# 4) 지원 API 전체 목록
curl -s "http://$CAM/HAPI/V1.0/sysinfo/functionlist?username=admin&password=$PW_MD5" | jq
```

위 4개 호출이 모두 `ResponseCode: 0`을 반환하면 **HAPI 채널이 살아있다**고 확정할 수 있습니다.

### 6.4 RTSP 라이브 스트림 확인

```bash
# ffplay (FFmpeg에 포함, 가장 가벼움)
ffplay -fflags nobuffer -flags low_delay -rtsp_transport tcp \
  "rtsp://admin:123456@$CAM:554/stream0"

# 또는 VLC
vlc "rtsp://admin:123456@$CAM:554/stream0"

# 서브 스트림(저해상도)
ffplay -rtsp_transport tcp "rtsp://admin:123456@$CAM:554/stream1"
```

`-rtsp_transport tcp`는 방화벽·NAT·UDP 패킷 누락 환경을 회피하기 위해 권장합니다.

### 6.5 광학 줌 동작 테스트 — 핵심 검증

```bash
# uid 발급 (이후 ?uid=$SID 만으로 인증 가능)
SID=$(curl -s "http://$CAM/HAPI/V1.0/uid/getuid?username=admin&password=$PW_MD5" \
      | jq -r '.Response.SessionID')
echo "SID=$SID"

# 500 ms 확대
curl "http://$CAM/HAPI/V1.0/ptz_ctrl/zoom?direction=in&autostop=500&uid=$SID"

# 500 ms 축소
curl "http://$CAM/HAPI/V1.0/ptz_ctrl/zoom?direction=out&autostop=500&uid=$SID"

# 정지(예방)
curl "http://$CAM/HAPI/V1.0/ptz_ctrl/stop?uid=$SID"
```

#### 판정 기준

| 결과 | 의미 |
|---|---|
| `ResponseCode: 0` + RTSP 영상에서 화각 변화 관찰 | 광학 줌 정상 |
| `ResponseCode: 0` 이지만 화각 변화 없음 | 줌 렌즈/보드 미장착 또는 결합 불량 (사양서 단서 그대로) |
| `ResponseCode != 0` | 인증 실패 또는 capability 부재 — 6.3 결과 재확인 |

### 6.6 스냅샷 캡처 (시각적 증거 확보)

```bash
curl "http://$CAM/HAPI/V1.0/snapshot.cgi?uid=$SID" -o snap_before.jpg
curl "http://$CAM/HAPI/V1.0/ptz_ctrl/zoom?direction=in&autostop=800&uid=$SID"
sleep 1.2
curl "http://$CAM/HAPI/V1.0/snapshot.cgi?uid=$SID" -o snap_after.jpg

xdg-open snap_before.jpg
xdg-open snap_after.jpg
```

## 7. 문제 상황별 디버깅 매트릭스

| 증상 | 1순위 의심 | 확인 방법 |
|---|---|---|
| 카메라가 ARP 스캔에 안 잡힘 | 전원/케이블 불량, 카메라가 다른 서브넷 | LED 점등 확인, `tshark`로 패킷 캡처 |
| ping 되지만 HTTP 80 실패 | 웹 서버가 다른 포트(8080, 8000) | `sudo nmap -p 1-10000 <카메라 IP>` 풀스캔 |
| HAPI 401 / 인증 실패 | 기본 계정·비밀번호 불일치 | 벤더 라벨 확인, `admin/admin`, `admin/12345`도 시도 |
| RTSP 연결 거부 | 경로/포트/인증 차이 | `rtsp://admin:pw@…:554/live/0`, `/cam/realmonitor`, `/h264/ch1/main/av_stream` 등 다른 벤더 경로 시도 |
| 줌 명령 OK인데 화각 변화 없음 | 줌 렌즈/보드 미장착 | 6.3의 능력집에서 `ele_zoom`/`ptz_zoom`/`af_setting` 존재 확인 |
| 화질이 8 MP가 아닌 5 MP로 보임 | 메인 스트림 해상도가 기본값에 묶임 | `/HAPI/V1.0/system/video/get`으로 현재 설정 확인, 필요 시 `set` |
| ONVIF Discovery에는 응답하나 HAPI 미응답 | 펌웨어가 HAPI 미탑재(타 벤더 OEM) | ONVIF 표준 PTZ로 줌 제어 대체 검토 |

## 8. 자동화 스크립트 — `bringup_test.sh`

위 6.3 ~ 6.5 단계를 한 번에 검증하는 스크립트 예시:

```bash
#!/usr/bin/env bash
# bringup_test.sh — WGWK-AS500J 계열 카메라 브링업 검증
# 사용: ./bringup_test.sh <카메라 IP> [<username> <password>]
set -euo pipefail

CAM=${1:?사용법: $0 <카메라 IP> [<user> <pass>]}
USER=${2:-admin}
PASS=${3:-123456}
PW_MD5=$(echo -n "$PASS" | md5sum | awk '{print $1}')
BASE="http://$CAM/HAPI/V1.0"

echo "[1/5] ping"
ping -c 2 -W 2 "$CAM" >/dev/null && echo "  OK" || { echo "  FAIL"; exit 1; }

echo "[2/5] device_info"
curl -fsS "$BASE/sysinfo/device_info?username=$USER&password=$PW_MD5" | jq '.Response.Data'

echo "[3/5] capability (zoom/ptz/af 관련 키만)"
curl -fsS "$BASE/sysinfo/capability?username=$USER&password=$PW_MD5" \
  | jq '.Response.Data[] | select(.caps | test("zoom|ptz|af_setting"; "i"))'

echo "[4/5] uid 발급 및 keep_alive 확인"
SID=$(curl -fsS "$BASE/uid/getuid?username=$USER&password=$PW_MD5" \
      | jq -r '.Response.SessionID')
echo "  SID=$SID"
curl -fsS "$BASE/uid/keep_alive?uid=$SID" | jq '.Response.ResponseString'

echo "[5/5] 줌 in 500ms → out 500ms → stop"
curl -fsS "$BASE/ptz_ctrl/zoom?direction=in&autostop=500&uid=$SID" | jq '.Response.ResponseString'
sleep 1
curl -fsS "$BASE/ptz_ctrl/zoom?direction=out&autostop=500&uid=$SID" | jq '.Response.ResponseString'
sleep 1
curl -fsS "$BASE/ptz_ctrl/stop?uid=$SID" | jq '.Response.ResponseString'

echo
echo "RTSP 메인 스트림 미리보기 명령:"
echo "  ffplay -fflags nobuffer -rtsp_transport tcp \"rtsp://$USER:$PASS@$CAM:554/stream0\""
```

실행:
```bash
chmod +x bringup_test.sh
./bringup_test.sh 192.168.1.10
# 또는 계정이 다르면
./bringup_test.sh 192.168.1.10 admin mypw
```

## 9. 브링업 후 권장 후속 작업

1. **실측 결과를 사양서에 반영** — `docs/01-hardware-spec.md`에 "실기 확인 결과" 절 추가(모델/펌웨어/센서/기본 IP·계정)
2. **능력집(capability) 스냅샷 저장** — `/sysinfo/capability` 응답을 `docs/capability-snapshot.json`으로 저장하여 추후 변경 추적
3. **줌 배율 한계 측정** — `IP_NET_DVR_GetDVRConfig(..., CMD_GET_ZOOM_CFG, ...)` 또는 화각 측정으로 최대 광학 배율 확정
4. **포커스 모드 확인** — AF가 자동인지 수동 호출이 필요한지(`/ptz_ctrl/focus`) 검증
5. **HAPI vs ONVIF 결정** — HAPI 미탑재 펌웨어이면 ONVIF 기반으로 통합 경로 변경

---

> 이 가이드는 카메라 수령 전에 작성된 예방적 절차입니다. 실기 결과로 발견된 차이점은 본 문서 또는 `docs/01-hardware-spec.md`의 후속 개정에 반영하시기 바랍니다.
