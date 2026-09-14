"""28일 기준선 EWMA 가중치 (WP-59).

baseline 은 문서 × 요일·시간대(0..167) 슬롯마다 지난 28일의 관측치(같은 요일·시간의
편집·조회수)를 모아 "평소"를 잡는다. 한 슬롯에는 대략 4개(4주)의 관측치가 있다.
그걸 **최근에 더 무게** 두어 평균·표준편차를 낸다 — 4주 전과 어제를 같게 보면 최근
추세 변화가 묻힌다.

이 모듈이 정하는 것 = **가중 방식과 감쇠(반감기)**다. build_baseline(WP-60)이
이 함수를 불러 edit_ewma·edit_stddev·view_ewma 를 낸다. 판정 임계(detector.py, z≥3 등,
WP-38 확정)는 여기서 건드리지 않는다.

🔴 반감기 확정값은 실데이터로 정한다
    반감기 후보를 과거 구간(Historical Window 산출물, WP-58)에 돌려 비교한 뒤
    명세 §11 에 날짜와 함께 기록한다. 비교 도구는 ewma_compare.py. 아래 DEFAULT 는
    **잠정값**이다 — 실덤프(-56·-57)·HDFS(-28) 적재 전이라 아직 실측으로 확정하지 않았다.

감쇠 정의
    나이(age) = 관측일이 윈도우 끝보다 며칠 전인가. weight = 0.5 ** (age_days / 반감기).
    반감기 H일이면 H일 전 관측치의 무게가 지금의 절반이다. 반감기가 크면 단순평균에
    가까워지고(전부 비슷한 무게), 작으면 최근값이 지배한다.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass

#: 잠정 기본 반감기(일). 28일 창·슬롯당 ~4관측에서 최근 2주에 옛 2주의 약 2배 무게를 준다
#: — 반응성과 안정성의 절충. 🔴 실측 확정 아님(ewma_compare.py + §11).
DEFAULT_HALFLIFE_DAYS = 14.0

#: 비교할 반감기 후보. 7=최근 강조, 28=창 전체 완만, 14=중간(기본 후보).
CANDIDATE_HALFLIFE_DAYS = (7.0, 14.0, 28.0)


@dataclass(frozen=True)
class Observation:
    """한 슬롯의 관측치 하나. age_days=윈도우 끝 기준 경과일(0=가장 최근)."""
    age_days: float
    value: float


def weight(age_days: float, halflife_days: float = DEFAULT_HALFLIFE_DAYS) -> float:
    """age_days 만큼 지난 관측치의 가중치. 반감기마다 절반이 된다."""
    if halflife_days <= 0:
        raise ValueError("halflife_days 는 양수여야 한다")
    return 0.5 ** (age_days / halflife_days)


def ewma_mean_std(
    observations: Iterable[Observation],
    halflife_days: float = DEFAULT_HALFLIFE_DAYS,
) -> tuple[float, float | None]:
    """가중 평균과 가중 표준편차(모집단)를 낸다.

    반환 (mean, std). 관측치가 없으면 (0.0, None). 하나뿐이면 std 는 0.0 —
    detector._z 가 stddev<=0 을 z 불가로 처리하므로 얇은 슬롯은 자연히 걸러진다
    (얇음 자체는 sample_days 로 따로 본다). build_baseline 의 stddev_pop 과 같은 모집단 분산.
    """
    obs = list(observations)
    if not obs:
        return 0.0, None

    total_w = sum(weight(o.age_days, halflife_days) for o in obs)
    if total_w <= 0:
        return 0.0, None

    mean = sum(weight(o.age_days, halflife_days) * o.value for o in obs) / total_w
    variance = sum(
        weight(o.age_days, halflife_days) * (o.value - mean) ** 2 for o in obs
    ) / total_w
    return mean, math.sqrt(variance)
