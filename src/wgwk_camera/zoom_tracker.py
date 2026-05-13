"""SW-side 줌 배율 추정기.

본 카메라(MC800S5 V3.4.5.2)는 모터 absolute encoder를 어느 채널(HAPI/SCF/ONVIF/
Event subscription)로도 노출하지 않는다 (`docs/08-endpoint-probe-2026-05-12.md`
§8.5). 이 모듈은 클라이언트 측에서 시간 적분으로 줌 배율을 추정한다.

원리:
  - 모터 속도 일정 가정 (linear): velocity = (max - min) / full_travel_ms
  - `zoom_in(ms)`, `zoom_out(ms)` 명령 시 estimate를 velocity × ms 만큼 갱신
  - 최소·최대 배율에서 clamp
  - hard-limit 도달(`anchor_wide`/`anchor_tele`)로 추정 기준점 재설정

정확도:
  - ±10~30% (모터 속도가 range 내 비등속이면 오차 누적)
  - 장기 운영 시 N분마다 anchor 권장
  - 추정값이 실제 모터 위치와 다를 수 있음을 항상 가정해야 한다
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ZoomTracker:
    """줌 배율 추정 상태.

    Attributes:
        max_multiplier: 최대 줌 배율 (10x 광학). SCF DzoomConfig.multiple_max에서 확인.
        min_multiplier: 최소 줌 배율 (광각, 1.0x).
        full_travel_ms: wide↔tele 전체 이동 시간 (ms). 기본 25000ms는 본 카메라
            (MC800S5 V3.4.5.2) 시각 검증 — 청크 방식 5s × 5회로 wide hard-limit
            완전 도달 확인 (`docs/08 §8.F`). 청크 분할 발사가 필수임을 주의:
            HAPI 펌웨어가 단일 zoom 명령의 autostop_ms를 ~5초로 내부 cap한다.
            `Camera._zoom_chunks()` 가 자동 처리.
    """

    max_multiplier: float = 10.0
    min_multiplier: float = 1.0
    full_travel_ms: int = 25000

    _estimate: float | None = field(default=None, init=False, repr=False)

    @property
    def velocity(self) -> float:
        """배율 변화 속도 (multiplier per ms)."""
        return (self.max_multiplier - self.min_multiplier) / self.full_travel_ms

    @property
    def estimate(self) -> float | None:
        """현재 추정 배율. anchor가 한 번도 안 됐으면 `None`."""
        return self._estimate

    @property
    def is_anchored(self) -> bool:
        return self._estimate is not None

    def anchor_wide(self) -> None:
        """추정을 최소 배율(광각 끝)로 고정. `anchor_wide()` 메서드 보조용."""
        self._estimate = self.min_multiplier

    def anchor_tele(self) -> None:
        """추정을 최대 배율(망원 끝)로 고정."""
        self._estimate = self.max_multiplier

    def invalidate(self) -> None:
        """추정 무효화 — `None` 반환. preset_call 등 알 수 없는 이동 후 사용."""
        self._estimate = None

    def set_estimate(self, value: float) -> None:
        """외부 정보를 직접 주입 (사용자가 실제 배율을 안다고 가정).

        Raises:
            ValueError: [min_multiplier, max_multiplier] 범위 밖.
        """
        if not (self.min_multiplier <= value <= self.max_multiplier):
            raise ValueError(
                f"zoom value {value} out of range "
                f"[{self.min_multiplier}, {self.max_multiplier}]"
            )
        self._estimate = float(value)

    def apply_zoom_in(self, ms: float) -> None:
        """`zoom_in(ms)` 명령 발사 후 호출. 추정 미앵커면 no-op."""
        if self._estimate is None:
            return
        self._estimate = min(
            self.max_multiplier, self._estimate + self.velocity * ms
        )

    def apply_zoom_out(self, ms: float) -> None:
        """`zoom_out(ms)` 명령 발사 후 호출. 추정 미앵커면 no-op."""
        if self._estimate is None:
            return
        self._estimate = max(
            self.min_multiplier, self._estimate - self.velocity * ms
        )
