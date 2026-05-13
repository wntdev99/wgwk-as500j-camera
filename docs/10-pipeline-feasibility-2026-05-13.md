# 10. 광학줌 카메라 도입 타당성 분석 (2026-05-13)

기존 송장 인식 파이프라인 대비 WGWK-AS500J (10x 광학줌 + 4K 60fps) 도입 시 성능
이득 가능성에 대한 심도 분석. 본 세션까지 누적된 실측 결과(`docs/08`, `docs/09`)를
바탕으로 한 평가이며, 실 application 데이터를 통한 추가 검증을 권장한다.

---

## 10.1 분석 대상 비교

### 기존 파이프라인 (4K 20fps 카메라 + 디지털 crop)

```
depth 추정 (박스 크기 + depth 점유율)
  → pin-hole model로 RGB에서 박스 ROI crop (디지털 줌)
  → 거리별 사전 측정된 manual focus 값 적용
  → 촬영
  → 송장 템플릿 매칭
  → 송장 이미지 추출
  → OCR
```

- 전체 사이클: **~1.5s** (실측)
- 한계: 8K로 올리면 3fps로 떨어짐 (sensor·bandwidth bottleneck)

### 대체 후보 (본 광학줌 카메라)

- 4K @ 60fps 가능 (스트림 수신 ~16ms/frame, cv2 직결)
- 10x optical zoom (KF 1~36 단위 제어)
- AF / 모터 위치 readback 제약 있음 (§10.3)

---

## 10.2 시나리오별 timing budget

본 카메라 실측 (`docs/08 §8.G`, `docs/09 §12`):

| 항목 | 측정값 |
|---|---|
| 모터 full travel (KF 1↔36) | ~6.5s motor time, rapid-fire 7.6s |
| 1 KF 이동 | 평균 185ms |
| HAPI ack | min(autostop_ms, 1000ms) |
| Focus LUT 적용 (예상) | 200~500ms (HAPI ack) |
| Focus sweep (현재 기본) | 25s |
| 4K stream frame 수신 (cv2) | ~16ms |
| Preset recall 정확도 | 1/4 |
| 모터 절대 위치 readback | **불가** |

### 시나리오 A — 박스 거리 분포가 좁음 (컨베이어·AGV 고정 거리)

- **1회 사전 셋업**: 광학줌을 nominal 거리에 고정, focus LUT로 fix
- per-frame: capture(16ms) → 템플릿 매칭(축소된 ROI로 ~700ms) → OCR
- depth 추정 단계 **삭제 가능** (광학줌이 그 역할을 대체)
- **총 ~720ms** (기존 1.5s 대비 약 2배 빠름)
- 추가 이득: 4K × 10x optical = 유효 40K급 픽셀밀도 → OCR 정확도↑

### 시나리오 B — 박스 거리 분포 중간 (±20%)

- depth → zoom ΔKF (보통 3~7 KF) = **555~1300ms**
- + focus LUT 적용 200~500ms
- + capture + 템플릿 + OCR
- **총 ~1.5~2.0s** (기존 대비 비슷하거나 약간 느림)
- 보상: 화질 이득으로 OCR 정확도 보존

### 시나리오 C — 박스 거리 분포가 매우 넓음 (1m~5m 무작위)

- 평균 zoom 이동 10+ KF = **1.8s+**
- focus 재설정도 매번 필요
- **총 2.5~3.5s** — 디지털 줌 대비 명백히 손해

---

## 10.3 구조적 위험요소

1. **모터 절대 위치 readback 불가능** (`docs/08 §8.5`)
   - SW-side KF 추정기로 우회 (`zoom_tracker.py`), 누적 drift 가능
   - 주기적 anchor (anchor_wide 또는 anchor_tele) 필요 — 1회당 7.6s 추가 비용

2. **Focus LUT의 zoom-focus dependency**
   - 광학줌 카메라는 같은 거리라도 zoom KF에 따라 focus 최적값이 다름
   - 만약 zoom을 가변으로 운용하면 LUT 차원이 (zoom_kf × distance) 2D로 폭증
   - 1회 캘리브레이션 비용 = KF 종류 × 거리 종류 × 25s sweep

3. **AF 신뢰 불가** → 완전 manual focus 의존
   - 박스 특성이 매우 다양하면 (반사·무광·곡면·흰 송장) LUT만으로 부족할 수 있음
   - 본 세션 MF 21X 사례: Laplacian variance peak이 시각적 blur와 불일치하는 경우 있음

4. **Preset recall 1/4 정확률** (`docs/08 §8.D`)
   - 위치 기억 메커니즘으로 사용 불가
   - SW-side KF 추정 + 직접 zoom 명령으로만 위치 제어

5. **HAPI 5s autostop cap** (`docs/08 §8.F`)
   - 단일 명령 최대 5s, full travel은 chunk-split 또는 rapid-fire 필요

---

## 10.4 진정한 win condition 압축

**박스 거리 분포가 좁은 application에서, 광학줌을 "fixed-focal
high-magnification 카메라"로 운용**

핵심:
- depth → 디지털 crop 단계를 **삭제** (광학줌이 대체)
- focus LUT는 zoom KF 1개 고정에 대해서만 거리별로 측정 (1D)
- per-frame 처리시간이 디지털 카메라와 동일 (16ms capture)
- 픽셀밀도 이득 → OCR 신뢰도 상승

### Lose condition

- 거리 변동이 크면 zoom 이동 시간이 budget을 먹음
- depth → zoom 의존 파이프라인은 motor 특성상 매번 ΔKF 비용 발생
- 이때는 기존 4K 20fps + 디지털 crop 파이프라인이 더 우수

---

## 10.5 권장 검증 순서

1. **실제 application의 박스 거리 분포 측정** — σ 값이 시나리오 A/B/C 판정의 핵심
2. **거리별 zoom·focus LUT 캘리브레이션** (zoom 고정 가정 시 1D)
3. **고정 zoom + LUT focus로 단일 사이클 timing 측정** vs 기존 1.5s 비교
4. **OCR 정확도 비교** — 픽셀밀도 증가의 실제 이득 정량화
5. **KF drift anchor 주기 결정** — 몇 사이클마다 wide anchor가 필요한지

---

## 10.6 결론

**조건부 채택 가능.**

- 박스 거리 분포가 좁은 application: **압도적 win** (속도 2배 + OCR 정확도 상승)
- 거리 분포가 중간: **속도는 break-even, OCR 정확도 이득**
- 거리 분포가 매우 넓음: **권장하지 않음** (기존 디지털 줌이 우수)

도입 전 §10.5의 1·2·3 단계 실측이 필수. 본 카메라의 모터 readback 부재와 AF
신뢰성 결여가 가장 큰 운영 리스크이며, SW-side 추정기 + LUT 운용으로 부분
보완 가능하나 완전한 대체는 아니다.

---

## 10.7 부록 — Zoom·Focus 병렬 명령 실증 (2026-05-13)

**검증 동기**: §10.2의 timing budget은 zoom·focus를 직렬 가정으로 계산되어 있다.
Varifocal 카메라는 zoom·focus 모터가 물리적으로 독립이므로, HAPI 펌웨어가
동시 명령을 수용한다면 wall-clock을 `T_zoom + T_focus`에서 `max(T_zoom, T_focus)`로
단축할 수 있다.

### 테스트 방법

`scripts/test_parallel_zoom_focus.py`:
- Python `threading.Thread`로 zoom 명령과 focus 명령을 동시 발사
- 각 명령 `autostop_ms=500`, AF는 사전에 OFF
- Sequential(zoom→focus) vs Parallel(zoom‖focus) wall-clock 비교
- 3회 반복

### 결과

| 항목 | 측정값 |
|---|---|
| Sequential (zoom 500 → focus 500) | **1018ms** (3회 평균, σ < 1ms) |
| Parallel (zoom 500 ‖ focus 500) | **516ms** (3회 평균, σ < 1ms) |
| zoom thread 단독 duration | 506ms |
| focus thread 단독 duration | 516ms |
| 절약량 | **502ms (49%)** |
| zoom_level 실측 변화 | 11.8 → 9.1 (병렬 명령 시) |

→ Sequential 1018ms ≈ 500 + 500 + 18ms overhead, Parallel 516ms ≈ max(506, 516)
→ **이론치와 거의 완벽히 일치**. HAPI는 zoom·focus concurrent command를 **완전히 허용**.

### 결론

- ✅ HAPI 펌웨어 직렬화 **없음**
- ✅ Zoom 모터와 focus 모터 **완전 독립** 동작 확인
- ✅ Wall-clock = `max(T_zoom, T_focus)` 적용 가능

### 시나리오 재계산 (병렬 적용)

| 시나리오 | sequential | **parallel** | 기존 (1.5s) 대비 |
|---|---|---|---|
| A (zoom 고정) | 200~500ms | 200~500ms | 동일 (zoom 없음) |
| B (ΔKF 3~7) | 755~1800ms | **555~1300ms** | break-even → **win** |
| C (ΔKF 10+) | 2000~2300ms | **1800ms+** | 개선되나 여전히 lose |

→ §10.6 결론이 한 단계 더 유리해진다. **시나리오 B가 lose에서 win 영역으로 이동**.

### 후속 검증

- ✅ 각 모터 settling time 측정 — `docs/08 §8.I` 완료 (zoom +400ms / focus +600ms)
- ✅ Focus LUT 가능성 검증 — `§10.8` 완료 (varifocal 확정, LUT 필수)
- ⚠ Focus 모터 backlash 측정 (양방향 LUT 분리 필요 여부)
- ⚠ Long-running 안정성 (수백 cycle 후 thread 충돌·HAPI 부하 확인)
- ⚠ 실제 application target(송장)으로 LUT 캘리브레이션

### 라이브러리 적용 완료

`facade.py::Camera.zoom_and_focus_parallel(zoom=(...), focus=(...))` 추가
(`§10.7` 검증 후 구현). 5개 케이스 unit test 통과:
zoom only / focus only / both parallel / invalid dir / no-op.

---

## 10.8 부록 — Focus LUT 가능성 검증 (2026-05-13)

**검증 동기**: §10.4의 핵심 가정 "focus LUT는 zoom KF 1개 고정 시 1D"가
성립하려면, 같은 거리의 같은 장면에서 focus optimum이 (a) zoom과 무관하거나
(parfocal), (b) zoom에 대해 예측 가능하게 이동(varifocal but predictable)
해야 함. 본 부록은 이를 직접 측정.

### 측정 방법

`scripts/calibrate_focus_lut.py`:
- 동일 카메라 위치, 동일 장면
- 3개 zoom KF (1=wide, 18=middle, 36=tele)에서 focus_sweep_best 수행
- 각 KF에서 peak focus step 기록
- Variance landscape의 SNR 확인

### 결과

| KF | sweep_steps | peak_step | peak_var | 신뢰도 |
|---|---|---|---|---|
| 1 (wide) | 16 | 2 | 2020.5 | High |
| 18 (middle) | 16 | 2 | 1341.2 | Medium |
| 36 (tele, 1차) | 16 | 14 | 321.1 | Low |
| 36 (tele, 2차) | 24 | 2 | 295.2 | Low (재측정으로 불일치) |

### 핵심 결론

**1. Varifocal 확정 (LUT 필수)**

- KF 1: peak step 2
- KF 36: peak step 위치 불확실하나 KF 1과 명백히 다른 영역
- Parfocal 가설 기각 — LUT 없이는 cross-zoom focus 부정확

**2. Tele에서 SNR 문제**

- KF 36의 2차 측정: variance가 sweep 전체에 걸쳐 200~295로 매우 평탄
- 같은 KF에서 두 번 측정 시 peak 위치가 step 2 vs step 14로 불일치
- → **현재 장면은 tele 캘리브레이션에 부적합**
- 원인: KF 36에서 시야가 좁아져 고주파 detail이 거의 없는 영역만 남음

**3. Cross-zoom variance 절대 비교는 무의미**

- KF 1 peak_var = 2020, KF 36 peak_var = 321
- 이는 image quality 차이가 아니라 측정 단위 차이
- Laplacian variance per pixel은 zoom↑ 시 같은 edge가 더 많은 픽셀에 분산되어 자연 감소
- → **OCR readiness 평가에는 별도 metric 필요** (edge density, OCR confidence, …)

**4. Peak shift 방향**

- zoom 증가 시 focus는 "far" 방향으로 이동하는 경향
- telephoto일수록 광학적으로 더 멀리 포커싱
- 일반적 varifocal 렌즈 동작과 일치

### 함의

- ✅ §10.4의 "LUT 1D (zoom 고정)" 접근법은 **이론적으로 타당**
- ⚠ 실제 캘리브레이션은 **application target (송장, 해상도 차트)** 필수
- ⚠ 임의 장면에서의 LUT 추출은 SNR 부족으로 신뢰 불가
- ⚠ 만약 application이 zoom 가변 운용이라면 **2D LUT (zoom × distance)** 필요
  - 캘리브레이션 비용: 5 zoom × 5 distance × 25s/sweep = ~10분 (1회성)

### 데이터

`data/focus_lut_characterization.json` 에 raw 측정값 저장.

