# 11. 광학줌 도입 검토 진행 상태 (2026-05-13)

본 문서는 기존 송장 인식 파이프라인(4K 20fps 디지털 crop)을 WGWK-AS500J 광학줌
카메라로 대체할 때의 타당성 검토 진행 현황을 정리한다. 인식 파이프라인 최종
설계는 추후 결정 예정이며, 본 문서는 결정 시점에 필요한 사전 검증 결과와
보류된 작업을 인계하기 위한 기록이다.

---

## 11.1 검토 배경

**기존 파이프라인**:
```
depth 추정 → pin-hole 모델로 RGB crop (디지털줌) →
사전 측정 manual focus → 촬영 → 템플릿 매칭 → OCR
```
- 사이클 ~1.5s @ 4K 20fps
- 한계: 8K로 올리면 3fps로 떨어짐

**대체 후보**: WGWK-AS500J (10x 광학줌, 4K @ 60fps)
- 디지털 crop을 광학 줌으로 대체하여 픽셀밀도 이득 + 60fps 유지를 노림

---

## 11.2 완료된 검증 (요약)

상세 결과는 `docs/08`, `docs/10` 참조.

### 라이브러리/카메라 동작 특성 확정

| 항목 | 결과 | 참조 |
|---|---|---|
| 모터 절대 위치 readback | **불가** (어느 채널로도 노출 안 됨) | `08 §8.5` |
| HAPI 단일 zoom 명령 cap | 5s autostop, ack = `min(autostop, 1000ms)` | `08 §8.F` |
| 모터 full travel | ~6.5s (rapid-fire 7.6s) | `08 §8.G` |
| KF 단위 추정기 | 185ms/KF 평균 정확도 ±10% | `08 §8.G`, `09 §12` |
| Preset recall 정확도 | 1/4 (사용 불가) | `08 §8.D` |
| AF 자동 동작 신뢰성 | zoom 중 작동 안 함 — manual focus 의존 | (반복 실측) |

### 본 세션 핵심 검증 (2026-05-13)

| 항목 | 결과 | 참조 |
|---|---|---|
| HAPI **zoom·focus 병렬 명령** | 완전 허용, 펌웨어 직렬화 없음 | `08 §8.H`, `10 §10.7` |
| 병렬 wall-clock | **516ms** (sequential 1018ms 대비 49% 감소) | `08 §8.H` |
| 모터 settling time | zoom: ack+400ms / focus: ack+600ms | `08 §8.I` |
| End-to-end (병렬+settle) | ~1116ms (sequential+settle 1618ms 대비 31% 감소) | `08 §8.I` |
| Focus LUT 가능성 | **varifocal 확정** — LUT 필수, peak step이 zoom에 따라 강하게 이동 | `10 §10.8` |
| Tele 캘리브레이션 SNR | 임의 장면에선 variance landscape 평탄 → 실제 송장 필요 | `10 §10.8` |

### 라이브러리 변경 (커밋 미실시, 워킹 트리에 존재)

- `src/wgwk_camera/facade.py`
  - `import threading` 추가
  - `Camera.zoom_and_focus_parallel(zoom=(...), focus=(...))` 신규 메서드
  - 5개 unit test 통과 (`scripts/test_parallel_zoom_focus.py` 결과)
- `scripts/test_parallel_zoom_focus.py` — 병렬 명령 검증
- `scripts/test_motor_settling.py` — settling time 측정
- `scripts/calibrate_focus_lut.py` — LUT 특성화 (임의 장면)
- `scripts/preview_label_setup.py` — 송장 setup용 snapshot 헬퍼
- `data/focus_lut_characterization.json` — raw 측정 데이터

---

## 11.3 보류 사항 (Pipeline 설계 결정 후 진행)

### 보류 이유

광학줌 도입의 win/lose 영역은 **실제 application의 박스 거리 분포**에 강하게
의존 (`docs/10 §10.2`). 거리 분포 데이터 없이 LUT 캘리브레이션을 진행하는
것은 다음 위험이 있음:

1. **잘못된 zoom 범위로 캘리브레이션**: 실 운용에서 사용 안 할 KF 영역까지
   측정하면 시간 낭비
2. **잘못된 distance grid**: 1D LUT 충분 vs 2D LUT 필수 결정이 거리 분포에
   따라 달라짐
3. **AF off 시 초기 focus anchor 위치**: application에서 박스가 일관된 거리에
   있다면 anchor 전략이 단순해짐

### 보류된 작업 목록

| # | 작업 | 선결 조건 | 예상 시간 |
|---|---|---|---|
| L1 | 실제 application의 박스 **거리 분포 σ 측정** | 운용 영상/로그 확보 | 1~2시간 |
| L2 | 시나리오 A/B/C 중 어디 해당하는지 결정 | L1 완료 | 즉시 (분석) |
| L3 | 송장 setup 후 1D 또는 2D LUT **캘리브레이션** | L2 결정 + 송장 물리 setup | 3분(1D) ~ 25분(2D) |
| L4 | LUT 정확도 검증 — fine-tune 필요 여부 | L3 완료 | 30분 |
| L5 | Focus 모터 **backlash 측정** (양방향 LUT 분리 필요 여부) | 별도 | 30분 |
| L6 | End-to-end **단일 사이클 timing** 측정 vs 기존 1.5s | L3, L4 완료 | 1시간 |
| L7 | OCR 정확도 비교 (광학줌 vs 기존 디지털 crop) | L3 완료 + 실 송장 dataset | 반나절~ |
| L8 | KF drift **anchor 주기** 결정 (수십 사이클당 anchor 1회) | 운용 시뮬 | 1시간 |

### 시나리오별 의사결정 가이드 (재게재 — `docs/10 §10.2`)

| 거리 분포 | 시나리오 | 도입 권장? | 권장 LUT |
|---|---|---|---|
| σ 매우 작음 (고정 위치) | A | **압도적 win** | 1D (distance) |
| σ ≤ ±20% nominal | B | **win** (병렬 적용 시) | 2D (zoom × distance) |
| σ 매우 큼 (1~5m 무작위) | C | **lose** (디지털 crop 우수) | (도입 비권장) |

---

## 11.4 재개 시 권장 순서

작업이 재개되면 다음 순서를 따를 것:

1. **L1**: 실 application 거리 분포 데이터 확보
2. **L2**: 시나리오 판정 → 도입 여부 1차 결정
3. (도입 진행 결정 시)
   - **송장 물리 setup** (1.5~2m 거리 권장, `scripts/preview_label_setup.py`로 검증)
   - **L3** 캘리브레이션 (시나리오 A=1D, B=2D)
   - **L4** 정확도 검증
   - **L6** end-to-end timing
   - **L7** OCR 정확도
4. 운용 결정 → **L8** drift 주기 산정 후 production 적용

---

## 11.5 미해결 / Open Questions

본 검토 과정에서 미해결로 남은 항목:

1. **Snapshot endpoint vs RTSP stream의 latency 차이**
   - 현 settling 측정은 RTSP 4K 60fps (cv2 decoder buffer 포함)
   - 단일 snapshot JPEG endpoint의 latency가 더 짧다면 capture timing
     단축 가능
   - 검증 필요

2. **NETSDK 포트 8091 인증 우회**
   - 모터 absolute 위치 readback이 이 채널에 있을 가능성 (Phase 1에서
     auth wall, `docs/08 §8.C`)
   - 만약 뚫리면 SW-side KF 추정 + LUT의 drift 문제가 근본 해결됨
   - 우선순위 낮음 (현 방식으로도 운용 가능)

3. **Laplacian variance 대안 metric**
   - tele에서 SNR 부족 — edge density, OCR confidence 등 OCR-aligned
     metric이 캘리브레이션에 더 적합할 가능성
   - 실 송장 캘리브레이션 단계에서 비교 평가

4. **Long-running 안정성**
   - `zoom_and_focus_parallel` 헬퍼의 수백 cycle 반복 시 thread 충돌·
     HAPI 부하 미검증

---

## 11.6 인계 시 참고 파일

```
docs/
  08-endpoint-probe-2026-05-12.md    §8.H, §8.I 가 최근 추가분
  09-library-api.md                   라이브러리 사용법
  10-pipeline-feasibility-2026-05-13.md  타당성 분석 본체
  11-pipeline-status-2026-05-13.md    (본 문서)

src/wgwk_camera/facade.py             zoom_and_focus_parallel 추가
src/wgwk_camera/zoom_tracker.py       KF 단위 추정기

scripts/
  test_parallel_zoom_focus.py         §8.H 재현
  test_motor_settling.py              §8.I 재현
  calibrate_focus_lut.py              §10.8 재현 (특성화)
  preview_label_setup.py              송장 setup 검증

data/
  focus_lut_characterization.json     §10.8 raw 데이터
```

본 시점까지의 워킹 트리는 git commit되어 있지 않음 (`scripts/`, `docs/10`,
`docs/11`, `data/`, `facade.py` 수정분). 재개 시 commit 정리 또는 stash
필요.
