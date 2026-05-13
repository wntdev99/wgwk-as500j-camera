"""SW-side 줌 KF 추정기 (KF 단위 모델).

본 카메라(MC800S5 V3.4.5.2)의 OSD가 표시하는 KF 카운터(1~36)를 클라이언트
측에서 추정한다. 모터 absolute encoder는 어느 채널(HAPI/SCF/ONVIF/Event
subscription)로도 노출되지 않음 (`docs/08 §8.5`).

원리:
  - 실측 캘리브레이션 (2026-05-13): 500ms motor time = +3 KF
    → 기본 `ms_per_kf = 167` (500/3 ≈ 166.67)
  - 한 번의 wide↔tele 이동 = 35 KF 변화 = ~6.5초 motor time
  - HAPI 단일 명령은 ~5초로 cap되지만 motor 자체는 ~6.5초면 full travel
    (이전 25초 가정은 chunked 명령들이 motor saturated 후에도 계속 발사된
    artifact였음 — `docs/08 §8.G`)

KF↔광학배율 매핑 (선형 가정):
  - KF 1  ↔ 1x optical (wide)
  - KF 36 ↔ 10x optical (tele, SCF `multiple_max`)
  - multiplier = 1 + (kf - 1) × 9 / 35

정확도:
  - 본 캘리브레이션 (185ms/KF 평균)에서 ±10% 이내
  - 장기 누적 시 drift 발생 → anchor 권장
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ZoomTracker:
    """줌 KF 추정 상태.

    Attributes:
        max_kf: 최대 KF (망원 끝). 카메라 OSD가 표시하는 값의 상한.
            본 카메라(AS500J/MC800S5) = 36.
        min_kf: 최소 KF (광각 끝). 보통 1.
        ms_per_kf: KF당 motor 명령 시간 (ms). 실측 평균값:
            500ms zoom_in = +3 KF → 500/3 ≈ 167. 실측 누적 평균 ~185.
        max_optical_multiplier: SCF DzoomConfig.multiple_max 값. KF↔광학배율
            매핑용. AS500J = 10.0.
    """

    max_kf: int = 36
    min_kf: int = 1
    ms_per_kf: float = 185.0
    max_optical_multiplier: float = 10.0

    _estimate: float | None = field(default=None, init=False, repr=False)

    @property
    def velocity_kf_per_ms(self) -> float:
        """KF 변화 속도 (KF / ms)."""
        return 1.0 / self.ms_per_kf

    @property
    def estimate(self) -> float | None:
        """현재 추정 KF (1.0 ~ max_kf). anchor 안 됐으면 `None`."""
        return self._estimate

    @property
    def estimate_multiplier(self) -> float | None:
        """KF 추정을 광학 배율로 변환 (선형 가정)."""
        if self._estimate is None:
            return None
        return self.kf_to_multiplier(self._estimate)

    @property
    def is_anchored(self) -> bool:
        return self._estimate is not None

    def kf_to_multiplier(self, kf: float) -> float:
        """KF → 광학 배율 (선형). KF 1=1x, KF max=max_optical_multiplier."""
        if self.max_kf == self.min_kf:
            return self.max_optical_multiplier
        ratio = (kf - self.min_kf) / (self.max_kf - self.min_kf)
        return 1.0 + ratio * (self.max_optical_multiplier - 1.0)

    def multiplier_to_kf(self, multiplier: float) -> float:
        """광학 배율 → KF (선형)."""
        if self.max_optical_multiplier == 1.0:
            return float(self.min_kf)
        ratio = (multiplier - 1.0) / (self.max_optical_multiplier - 1.0)
        return self.min_kf + ratio * (self.max_kf - self.min_kf)

    def anchor_wide(self) -> None:
        """추정을 `min_kf`로 고정 (광각 끝)."""
        self._estimate = float(self.min_kf)

    def anchor_tele(self) -> None:
        """추정을 `max_kf`로 고정 (망원 끝)."""
        self._estimate = float(self.max_kf)

    def invalidate(self) -> None:
        """추정 무효화. preset_call 등 알 수 없는 이동 후 사용."""
        self._estimate = None

    def set_estimate(self, kf: float) -> None:
        """KF 값 직접 주입.

        Raises:
            ValueError: [min_kf, max_kf] 범위 밖.
        """
        if not (self.min_kf <= kf <= self.max_kf):
            raise ValueError(
                f"KF {kf} out of range [{self.min_kf}, {self.max_kf}]"
            )
        self._estimate = float(kf)

    def apply_zoom_in(self, ms: float) -> None:
        """`zoom_in(ms)` 후 호출. `ms / ms_per_kf` 만큼 KF 증가, max 클램프."""
        if self._estimate is None:
            return
        self._estimate = min(
            float(self.max_kf), self._estimate + ms / self.ms_per_kf
        )

    def apply_zoom_out(self, ms: float) -> None:
        """`zoom_out(ms)` 후 호출. `ms / ms_per_kf` 만큼 KF 감소, min 클램프."""
        if self._estimate is None:
            return
        self._estimate = max(
            float(self.min_kf), self._estimate - ms / self.ms_per_kf
        )
