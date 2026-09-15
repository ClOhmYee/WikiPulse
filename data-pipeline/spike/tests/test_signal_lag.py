"""편집·조회수 신호 시차 측정 로직 (WP-86). 네트워크 없이 합성 데이터로 돈다.

실사건 10건 결과는 `python ../ai/signal-order/measure.py` 로 따로 낸다 (AQS 를 부른다).
여기서는 계산 규칙만 고정한다 — 특히 **detector 와 같은 임계를 쓰는지**와
**조회수 절대 하한 기본값이 0(하한 없음)인지**다. 후자가 바뀌면 측정값이 조용히 달라진다.
"""

from __future__ import annotations

from datetime import date

from spike.detector import MIN_VIEW_RATIO, VIEW_Z_THRESHOLD
from spike.signal_lag import EditSignal, LagResult, ViewSignal, first_view_signal


def series(start: date, values: list[int]) -> dict[date, int]:
    return {date.fromordinal(start.toordinal() + i): v for i, v in enumerate(values)}


#: 평상시 20일. 값이 조금씩 흔들린다 — 완전히 같은 값이면 표준편차가 0 이라 z 를 못 낸다
#: (아래 test_표준편차가_0이면_z를_못_낸다 가 그 규칙을 따로 고정한다).
CALM = [400, 412, 389, 405, 396, 418, 402, 391, 409, 398,
        403, 415, 387, 407, 394, 411, 400, 396, 413, 390]


# ---------------------------------------------------------------- 조회수 신호

def test_평상시_구간에서는_신호가_안_난다():
    quiet = series(date(2025, 5, 1), [400, 410, 395, 405, 398, 402, 399, 401] * 3)
    assert first_view_signal(quiet) is None


def test_급등한_첫날을_집는다():
    values = CALM + [20_000] + [30_000] * 3
    signal = first_view_signal(series(date(2025, 5, 1), values))
    assert signal is not None
    assert signal.day == date(2025, 5, 21)          # 20일치 평상시 다음 날
    assert signal.z >= VIEW_Z_THRESHOLD
    assert signal.ratio >= MIN_VIEW_RATIO


def test_기준선에_판정_대상_자신은_안_들어간다():
    """자기를 기준선에 넣으면 급증이 평소로 희석된다(미탐). replay.baseline_at 과 같은 규칙."""
    values = CALM + [20_000]
    signal = first_view_signal(series(date(2025, 5, 1), values))
    assert signal is not None
    assert signal.baseline_mean < 1_000            # 20,000 이 섞였으면 훨씬 컸다


def test_배수만_크고_z가_작으면_안_잡는다():
    """변동이 원래 큰 문서. z 관문이 이걸 막는다."""
    noisy = series(date(2025, 5, 1), [10, 5_000, 20, 4_000, 15, 6_000] * 4 + [12_000])
    signal = first_view_signal(noisy)
    assert signal is None or signal.z >= VIEW_Z_THRESHOLD


def test_관측이_2일_미만이면_건너뛴다():
    """창에 관측이 1일뿐이면 분산을 못 낸다. 신규 문서가 여기 걸린다."""
    assert first_view_signal(series(date(2025, 5, 1), [100, 900_000])) is None


def test_표준편차가_0이면_z를_못_낸다():
    """평상시 값이 완전히 일정한 문서는 아무리 튀어도 z 경로가 안 돈다.

    detector._z 가 stddev<=0 을 z 불가로 처리하는 것과 같은 규칙이다. 실데이터에는
    거의 없는 상황이지만, 합성 테스트를 짤 때 이걸 모르면 미탐을 버그로 오인한다."""
    assert first_view_signal(series(date(2025, 5, 1), [400] * 20 + [20_000])) is None


def test_절대_하한_기본값은_detector_를_따라간다():
    """🔴 측정 도구가 detector 와 다른 답을 내면 §11 수치가 조용히 어긋난다.

    ~~기본 0 = 하한 없음~~ → detector 에 `MIN_ABSOLUTE_VIEWS` 가 생겨서
    기본값이 그걸 그대로 따라간다 (2026-09-15, WP-87).
    """
    tiny = series(date(2025, 5, 1), [1, 2, 1, 3, 1, 2, 1, 1, 2, 1, 8])
    assert first_view_signal(tiny) is None                       # 8회는 이제 막힌다
    assert first_view_signal(tiny, min_absolute_views=0) is not None   # sweep 으로만 푼다

    big = series(date(2025, 5, 1), [400] + [400, 412, 389, 405, 396, 418, 402, 391,
                                            409, 398] + [20_000])
    assert first_view_signal(big) is not None                    # 큰 값은 그대로 통과


def test_not_before_이전_급등은_무시한다():
    values = CALM[:10] + [9_000] + CALM[10:19] + [9_000]
    full = series(date(2025, 5, 1), values)
    early = first_view_signal(full)
    late = first_view_signal(full, not_before=date(2025, 5, 15))
    assert early is not None and early.day == date(2025, 5, 11)
    assert late is not None and late.day == date(2025, 5, 21)


# ---------------------------------------------------------------- 시차

def _lag(view_day: date | None, edit_window: str | None) -> int | None:
    view = None if view_day is None else ViewSignal(view_day, 100, 10.0, 9.0, 10.0)
    edit = None if edit_window is None else EditSignal(edit_window, 12, 3, None, True)
    return LagResult("T", date(2025, 6, 12), view, edit).lag_days


def test_시차는_편집일_빼기_조회수일이다():
    assert _lag(date(2025, 6, 12), "2025-06-21T04:00:00") == 9      # 편집이 늦다
    assert _lag(date(2025, 6, 12), "2025-06-12T23:00:00") == 0      # 같은 날
    assert _lag(date(2025, 6, 14), "2025-06-12T01:00:00") == -2     # 편집이 빠르다


def test_한쪽이_미탐이면_시차는_없다():
    """미탐을 0 으로 세면 '동시에 잡혔다'로 읽혀 결론이 뒤집힌다."""
    assert _lag(None, "2025-06-12T01:00:00") is None
    assert _lag(date(2025, 6, 12), None) is None
