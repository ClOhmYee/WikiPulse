"""리플레이 회귀 검증 로직 (WP-61). 실덤프 없이 합성 데이터로 돈다.

실사건(Hormuz 2025-06 · Milton 2024-10) 결과는 실덤프를 적재해 `python -m spike.replay`
로 따로 낸다 — 여기서는 재생 로직 자체(집계·기준선 시점·판정 경로)를 고정한다.
"""

from __future__ import annotations

from datetime import date

from spike.detector import MIN_ABSOLUTE_EDITS, MIN_BASELINE_SAMPLE_DAYS
from spike.replay import (
    Observation,
    aggregate,
    baseline_at,
    first_detection,
    replay_title,
)


def event(title, ts, user="u1", is_bot=False, wiki="enwiki"):
    return {"wiki": wiki, "title": title, "event_ts": ts, "user": user, "is_bot": is_bot}


def obs(title, window_start, edits, editors=1):
    return Observation("enwiki", title, window_start, edits, editors)


# ---------------------------------------------------------------- 집계

def test_관심_문서만_봇_빼고_시간별로_센다():
    events = [
        event("Iran", "2025-06-09T00:10:00", "a"),
        event("Iran", "2025-06-09T00:50:00", "b"),
        event("Iran", "2025-06-09T00:20:00", "bot1", is_bot=True),   # 봇 제외
        event("Iran", "2025-06-09T01:05:00", "a"),                    # 다음 시간
        event("Cat", "2025-06-09T00:10:00", "c"),                     # 관심 밖
    ]
    by_title = aggregate(events, {"Iran"})
    assert set(by_title) == {"Iran"}
    first = by_title["Iran"][0]
    assert first.window_start == "2025-06-09T00:00:00"
    assert first.edit_count == 2 and first.editor_count == 2          # a, b
    assert by_title["Iran"][1].window_start == "2025-06-09T01:00:00"


def test_같은_편집자_반복은_편집자_1명():
    events = [event("Iran", f"2025-06-09T00:{m:02d}:00", "a") for m in (5, 15, 25)]
    first = aggregate(events, {"Iran"})["Iran"][0]
    assert first.edit_count == 3 and first.editor_count == 1


# ---------------------------------------------------------------- 기준선 시점

def test_판정_대상은_자기_기준선에_안_들어간다():
    """대상이 기준선에 섞이면 급증이 평소로 희석돼 미탐이 난다."""
    target = obs("Iran", "2025-06-09T00:00:00", 40)
    history = [obs("Iran", "2025-06-02T00:00:00", 1),
               obs("Iran", "2025-05-26T00:00:00", 1), target]
    baseline = baseline_at(history, target, halflife_days=1e9)
    assert baseline is not None
    assert baseline.edit_ewma == 1.0        # 40 이 안 섞였다


def test_같은_슬롯만_기준선에_쓴다():
    target = obs("Iran", "2025-06-09T00:00:00", 40)          # 월 00시 = slot 0
    history = [target,
               obs("Iran", "2025-06-02T00:00:00", 1),        # slot 0
               obs("Iran", "2025-06-03T05:00:00", 99)]       # 화 05시 = 다른 슬롯
    baseline = baseline_at(history, target, halflife_days=1e9)
    assert baseline.edit_ewma == 1.0                          # 99 는 안 섞였다


def test_28일_창_밖은_기준선에_안_들어간다():
    target = obs("Iran", "2025-06-09T00:00:00", 40)
    old = obs("Iran", "2025-04-07T00:00:00", 999)             # 두 달 전, 같은 슬롯
    assert baseline_at([target, old], target, halflife_days=1e9) is None


def test_과거_관측이_없으면_기준선_없음():
    target = obs("Iran", "2025-06-09T00:00:00", 40)
    assert baseline_at([target], target, halflife_days=1e9) is None


# ---------------------------------------------------------------- 판정 경로

def test_기준선_없는_문서는_절대_편집수로_잡힌다():
    """Hurricane Milton 경로 — 사건 당일 생긴 문서라 기준선이 없다."""
    results = replay_title([obs("Milton", "2024-10-09T12:00:00", 40, editors=8)])
    decision = results[0].decision
    assert decision.is_new_page is True
    assert decision.is_spike is True                # 40 >= MIN_ABSOLUTE_EDITS
    assert decision.edit_z is None                  # 기준선이 없어 z 를 못 낸다
    assert decision.spike_score > 0


def test_절대_편집수_미달이면_안_잡힌다():
    results = replay_title([obs("Cat", "2025-06-09T00:00:00", MIN_ABSOLUTE_EDITS - 1)])
    assert results[0].decision.is_spike is False


def test_대조군은_평소_편집에서_오탐이_없다():
    """매주 같은 슬롯에 2편집씩. 급증이 없으니 아무 시점도 잡히면 안 된다."""
    days = ["2025-05-19", "2025-05-26", "2025-06-02", "2025-06-09"]
    observations = [obs("Cat", f"{d}T00:00:00", 2) for d in days]
    results = replay_title(observations, halflife_days=1e9)
    assert first_detection(results) is None


def test_first_detection은_가장_이른_급증():
    observations = [obs("Iran", "2025-06-09T00:00:00", 2),
                    obs("Iran", "2025-06-09T01:00:00", 40),
                    obs("Iran", "2025-06-09T02:00:00", 50)]
    first = first_detection(replay_title(observations))
    assert first is not None and first.window_start == "2025-06-09T01:00:00"


# ---------------------------------------------------------------- 알려진 한계

def test_슬롯당_관측은_28일에_최대_4개다():
    """🔴 회귀로 고정하는 **알려진 불일치** (WP-61 에서 발견).

    hour_of_week 슬롯은 주에 한 번만 온다. 그래서 28일 창에서 한 슬롯의 관측은
    아무리 많아야 4개이고 `sample_days <= 4` 다. 그런데 detector 의
    MIN_BASELINE_SAMPLE_DAYS 는 7 이라 **조건이 영원히 충족되지 않는다** —
    기존 문서도 항상 is_thin 으로 판정돼 z 경로 대신 절대 편집수 경로로 간다.

    ⚠️ 여기서 임계를 고치지 않는다. WP-38 확정 자산이라 별건 이슈다.
    """
    days = ["2025-05-19", "2025-05-26", "2025-06-02", "2025-06-09"]   # 월요일 4주
    observations = [obs("Iran", f"{d}T00:00:00", 1) for d in days]
    target = obs("Iran", "2025-06-16T00:00:00", 40)
    baseline = baseline_at(observations + [target], target, halflife_days=1e9)

    assert baseline.sample_days == 4                     # 4주치가 최대
    assert baseline.sample_days < MIN_BASELINE_SAMPLE_DAYS
    assert baseline.is_thin is True                      # -> 신규 문서 경로로 빠진다
