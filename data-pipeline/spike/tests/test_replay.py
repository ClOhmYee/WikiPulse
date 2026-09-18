"""리플레이 회귀 검증 로직 (WP-61). 실덤프 없이 합성 데이터로 돈다.

실사건(Hormuz 2025-06 · Milton 2024-10) 결과는 실덤프를 적재해 `python -m spike.replay`
로 따로 낸다 — 여기서는 재생 로직 자체(집계·기준선 시점·판정 경로)를 고정한다.
"""

from __future__ import annotations

from datetime import date

from spike.detector import MIN_ABSOLUTE_EDITS, MIN_BASELINE_SAMPLE_DAYS
from spike.replay import (
    first_candidate,
    Observation,
    aggregate,
    baseline_at,
    first_detection,
    replay_title,
)


def event(title, ts, user="u1", is_bot=False, wiki="enwiki"):
    return {"wiki": wiki, "title": title, "event_ts": ts, "user": user, "is_bot": is_bot}


def obs(title, window_start, edits, editors=2):   # 편집자 하한(MIN_DISTINCT_EDITORS)이 2다
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



def test_밑줄_덤프와_공백_덤프가_같은_답을_낸다():
    """덤프 세대가 둘이다 (WP-91).

    `normalize_dump` 가 WP-79 부터 공백형 제목을 낸다. 재생성 전 적재본은
    밑줄형이라 두 세대가 섞여 돈다. 형식이 어긋나면 "관측 없음" 으로 끝나는데 그게
    "급증이 없었다" 로 읽히기 쉬워 — 조용히 틀리는 쪽이라 aggregate 가 흡수한다.
    """
    underscore = [event("Strait_of_Hormuz", "2025-06-23T14:10:00", "a"),
                  event("Strait_of_Hormuz", "2025-06-23T14:40:00", "b")]
    spaced = [event("Strait of Hormuz", "2025-06-23T14:10:00", "a"),
              event("Strait of Hormuz", "2025-06-23T14:40:00", "b")]

    # 요청 제목도 어느 형식으로 주든 같아야 한다 — 2 × 2 조합 전부.
    results = [aggregate(evts, {req})
               for evts in (underscore, spaced)
               for req in ("Strait_of_Hormuz", "Strait of Hormuz")]
    for by_title in results:
        assert list(by_title) == ["Strait of Hormuz"]      # 결과 키는 canonical
        assert by_title["Strait of Hormuz"][0].edit_count == 2


def test_연속_구분자_제목도_한_문서로_모인다():
    """같은 문서가 표기만 다르게 들어오면 한 키로 합쳐야 한다. 안 합치면 편집 수가
    쪼개져 절대 하한(10)에 못 미치고 미탐이 난다."""
    events = [event("Hurricane__Milton", "2024-10-06T19:10:00", "a"),
              event("Hurricane Milton", "2024-10-06T19:20:00", "b"),
              event("_Hurricane_Milton_", "2024-10-06T19:30:00", "c")]
    by_title = aggregate(events, {"Hurricane Milton"})
    assert list(by_title) == ["Hurricane Milton"]
    obs = by_title["Hurricane Milton"][0]
    assert obs.edit_count == 3 and obs.editor_count == 3

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

def test_기준선_없는_문서도_조회수_없이는_확정_안_된다():
    """Hurricane Milton 경로 — 사건 당일 생긴 문서라 기준선이 없다.

    ~~40 >= MIN_ABSOLUTE_EDITS 라 급증~~ → **후보 대기**다 (2026-09-18, WP-126).
    편집 덤프에는 조회수가 없어서 2단계를 못 넘는다. 리플레이가 확정을 못 내는 건
    버그가 아니라 계약이다 — 명세 §3.2 9번이 리플레이도 시간별 조회수를 쓰라고 했다.
    """
    results = replay_title([obs("Milton", "2024-10-09T12:00:00", 40, editors=8)])
    decision = results[0].decision
    assert decision.is_new_page is True
    assert decision.is_pending                      # 확정도 폐기도 아니다
    assert decision.is_spike is False
    assert decision.edit_z is None                  # 기준선이 없어 z 를 못 낸다
    assert decision.spike_score == 0.0              # 점수는 확정된 뒤에만 의미가 있다


def test_편집이_0이면_후보도_아니다():
    """~~절대 편집수(10) 미달이면 안 잡힌다~~ → 1단계 관문은 **1건**이다
    (WP-126). 9건도 후보가 된다 — 0건만 탈락한다.
    """
    few = replay_title([obs("Cat", "2025-06-09T00:00:00", MIN_ABSOLUTE_EDITS - 1)])
    assert few[0].decision.is_pending                # 9건도 1단계는 통과

    none = replay_title([obs("Cat", "2025-06-09T00:00:00", 0, editors=0)])
    assert none[0].decision.is_pending is False
    assert none[0].decision.is_spike is False


def test_1인_연속편집도_1단계는_통과한다():
    """~~편집자가 한 명이면 거른다 (WP-85)~~ → **관문에서 빠졌다**
    (2026-09-18, WP-126, 명세 §3.2 2번).

    그 게이트는 실덤프에서 대조군 오탐을 395 -> 101 건으로 줄였었다. 새 계약은 그 일을
    **조회수 최종 관문**이 대신한다 — 혼자 문서를 정리해도 조회수는 안 튀기 때문이다.
    ⚠️ 아직 실측으로 확인 안 됐다. 조회수를 실제로 넣는 후속에서 재확인한다.
    """
    solo = replay_title([obs("Cat", "2025-06-09T00:00:00", 40, editors=1)])
    assert solo[0].decision.is_pending              # 1단계 통과, 조회수 대기
    assert solo[0].decision.is_spike is False       # 확정은 아니다

    # 편집자가 둘이어도 결과는 같다 — 편집자 수는 이제 판정에 안 들어간다
    team = replay_title([obs("Cat", "2025-06-09T00:00:00", 40, editors=2)])
    assert team[0].decision.status is solo[0].decision.status


def test_대조군은_평소_편집에서_오탐이_없다():
    """매주 같은 슬롯에 2편집씩. 급증이 없으니 아무 시점도 잡히면 안 된다."""
    days = ["2025-05-19", "2025-05-26", "2025-06-02", "2025-06-09"]
    observations = [obs("Cat", f"{d}T00:00:00", 2) for d in days]
    results = replay_title(observations, halflife_days=1e9)
    assert first_detection(results) is None


def test_조회수_없는_재생은_확정이_하나도_없다():
    """🔴 이 경로로 재현율을 재던 수치(WP-85: 10/12)는 더는 못 낸다."""
    observations = [obs("Iran", "2025-06-09T00:00:00", 2),
                    obs("Iran", "2025-06-09T01:00:00", 40),
                    obs("Iran", "2025-06-09T02:00:00", 50)]
    results = replay_title(observations)
    assert first_detection(results) is None
    assert all(r.decision.is_pending for r in results)


def test_first_candidate는_1단계_통과_시점을_준다():
    """확정을 못 내는 동안 편집 신호가 언제 섰는지는 볼 수 있어야 한다."""
    observations = [obs("Iran", "2025-06-09T00:00:00", 0, editors=0),
                    obs("Iran", "2025-06-09T01:00:00", 40),
                    obs("Iran", "2025-06-09T02:00:00", 50)]
    first = first_candidate(replay_title(observations))
    assert first is not None and first.window_start == "2025-06-09T01:00:00"


# ---------------------------------------------------------------- 알려진 한계

def test_슬롯이_매일_와서_sample_days가_쌓인다():
    """WP-84 로 해소된 구조 문제의 회귀 테스트.

    ~~hour_of_week 슬롯은 주 1회라 28일 창 관측이 최대 4개이고 sample_days 가
    MIN_BASELINE_SAMPLE_DAYS(7) 에 영원히 도달하지 못했다~~ → hour_of_day 로 바꿔
    같은 슬롯이 **매일** 온다 (2026-09-15). 이제 7일이면 문턱을 넘어 z 경로가 산다.
    """
    days = [f"2025-06-{d:02d}" for d in range(2, 10)]    # 8일 연속, 같은 00시 슬롯
    observations = [obs("Iran", f"{d}T00:00:00", 1) for d in days]
    target = obs("Iran", "2025-06-10T00:00:00", 40)
    baseline = baseline_at(observations + [target], target, halflife_days=1e9)

    assert baseline.sample_days == 8                     # 주 1회가 아니라 매일
    assert baseline.sample_days >= MIN_BASELINE_SAMPLE_DAYS
    assert baseline.is_thin is False                     # -> z 경로가 실제로 돈다
