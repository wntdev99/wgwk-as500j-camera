# scripts/

카메라 셋업·운영용 CLI 스크립트.

`wgwk_camera` 라이브러리를 사용하는 운영 도구들이며, 모두 기본 동작은 **비파괴(dry-run)** 입니다. 카메라 영구 변경은 `--apply` 플래그를 명시적으로 추가해야 발생합니다.

## `initial_setup.py` — 새 카메라 초기 셋업

새 카메라를 받았을 때 또는 운영 환경에 처음 투입할 때 사용. 도달성 확인 → 디바이스 정보 → 현재 인코딩 → 능력집 → 인코딩 프로필 적용 → OSD off → (선택) 재부팅까지 한 흐름.

```bash
# 1) 현재 상태만 확인 (가장 안전)
python3 scripts/initial_setup.py --host 192.168.8.101

# 2) 정밀 검출 프로필 변경 사항 미리 보기 (dry-run)
python3 scripts/initial_setup.py --host 192.168.8.101 --profile precision

# 3) 실제 적용
python3 scripts/initial_setup.py --host 192.168.8.101 --profile precision --apply

# 4) 적용 후 재부팅까지
python3 scripts/initial_setup.py --host 192.168.8.101 --profile precision --apply --reboot

# 5) OSD는 그대로 두고 인코딩만 변경
python3 scripts/initial_setup.py --host 192.168.8.101 --profile precision --apply --keep-osd
```

선택 가능한 `--profile`: `precision`(기본 권장), `robot_vision`, `bandwidth_save`, `fast_tracking`.
프로필 명세는 `src/wgwk_camera/profiles.py`.

## `healthcheck.py` — 운영 중 한 줄 점검

```bash
python3 scripts/healthcheck.py --host 192.168.8.101
python3 scripts/healthcheck.py --host 192.168.8.101 --snapshot /tmp/h.jpg
```

확인 항목:
1. HTTP TCP 도달성
2. HAPI 로그인
3. device_info (모델/펌웨어)
4. 비디오 인코딩 활성 스트림
5. RTSP 554 포트 개방
6. OSD 토글 상태
7. (선택) snapshot.cgi 한 장 받기

종료 코드:
- `0`: 모두 정상
- `2`: 도달 불가 (전원/네트워크/IP 확인)
- `3`: 인증 실패 (계정/비밀번호 확인)
- `4`: 일부 채널 실패 (RTSP 포트 닫힘 등)

스크립트 모두 단순 Python으로 작성되어 있어, 본 패키지를 외부 프로젝트의 `setup.py` 후속 작업으로 끼워 넣기 좋습니다.
