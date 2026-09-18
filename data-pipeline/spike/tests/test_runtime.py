"""런타임 경로 — 기준선 조회 → detect() → spike (WP-94). DB 없이 돈다.

여기서 고정하는 계약:
  - DB 기준선이 **그대로** detector 에 들어간다 (메모리 재계산이 아니다)
  - 급증만 저장하고 미탐은 저장하지 않는다
  - 기존 문서 z 경로가 실제로 실행된다 (WP-84 이전엔 구조적으로 죽어 있던 경로)
  - 타임스탬프는 tz-aware UTC 만 받는다

실 PostgreSQL 왕복은 `test_spike_runtime_pg.py`.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from spike.baseline_repository import BaselineRepository
from spike.detector import (
    EDIT_Z_THRESHOLD,
    MIN_ABSOLUTE_EDITS,
    MIN_BASELINE_SAMPLE_DAYS,
    Baseline,
)
from spike.runtime import PageWindow, RuntimeSummary, SpikeRuntime, parse_window_start

UTC = timezone.utc


class FakeBaselines:
    """`BaselineRepository` 자리에 끼우는 대역. 넘긴 객체를 그대로 돌려준다."""

    def __init__(self, slots: dict[tuple[str, str, int], Baseline] | None = None):
        self.slots = slots or {}
        self.asked: list[tuple[str, str, int]] = []
        self.invalidated = 0

    def get(self, wiki, title, hour_of_day):
        self.asked.append((wiki, title, hour_of_day))
        return self.slots.get((wiki, title, hour_of_day))

    def invalidate(self):
        self.invalidated += 1


class FakeConn:
    """`SELECT` 한 번에 정해진 행을 주고 왕복 횟수를 센다 (실 BaselineRepository 용)."""

    def __init__(self, store):
        self.store = store
        self.calls: list = []

    def cursor(self):
        return FakeCursor(self.store, self.calls)


class FakeCursor:
    def __init__(self, store, calls):
        self._store, self._calls, self._rows = store, calls, []

    def execute(self, sql, params):
        self._calls.append(params)
        self._rows = list(self._store.get(tuple(params), []))

    def fetchall(self):
        return self._rows

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeSink:
    def __init__(self):
        self.saved: list[dict] = []

    def save(self, **kwargs):
        self.saved.append(kwargs)
        return 1


#: 확정이 나는 기본 조회수. 2단계 계약에서 **조회수가 없으면 아무것도 확정되지 않으므로**
#: (WP-126) 기본값을 확정 쪽에 둔다. 미도착 경로를 보려면 `views=None` 을 준다.
CONFIRMING_VIEWS = 5_000


def window(edits=1, editors=2, hour=19, views=CONFIRMING_VIEWS,
           title="Hurricane Milton"):
    return PageWindow(
        wiki="enwiki", title=title,
        window_start=datetime(2024, 10, 6, hour, tzinfo=UTC),
        edit_count=edits, editor_count=editors, views=views,
    )


def thick(edit_ewma=2.0, edit_stddev=1.0, view_ewma=100.0, view_stddev=20.0, **kw):
    """조회수 기준선이 선 두꺼운 기준선.

    ~~`view_ewma=None`~~ → 2단계 계약에서 조회수 기준선이 없으면 절대 하한만 보게 되어
    (`views >= 100`) 배수·z 경로를 아예 안 탄다. 기본값을 채워 두 경로 다 테스트된다.
    """
    return Baseline(edit_ewma=edit_ewma, edit_stddev=edit_stddev, view_ewma=view_ewma,
                    view_stddev=view_stddev,
                    sample_days=MIN_BASELINE_SAMPLE_DAYS + 7, **kw)


# ---------------------------------------------------------------- 저장 여부

def test_급증이면_spike에_저장한다():
    sink = FakeSink()
    outcome = SpikeRuntime(FakeBaselines(), sink).process(window())
    assert outcome.decision.is_spike is True
    assert outcome.persisted is True
    assert len(sink.saved) == 1


def test_미탐이면_저장하지_않는다():
    """spike 는 '2단계까지 통과한 문서' 다 (V1 테이블 주석 · 명세 §3.2 3번).

    ~~편집 10건 미달이면 미탐~~ → 편집은 관문이 아니다 (WP-126).
    미탐은 **조회수가 도착했는데 급등이 아닌 것**이다.
    """
    sink = FakeSink()
    outcome = SpikeRuntime(FakeBaselines(), sink).process(window(views=50))
    assert outcome.decision.is_spike is False
    assert outcome.persisted is False
    assert sink.saved == []


def test_조회수_미도착은_후보_대기라_저장하지_않는다():
    """🔴 미탐과 **다른 상태**다. 저장은 안 하지만 폐기도 아니다 — 재판정 대상이다."""
    sink = FakeSink()
    outcome = SpikeRuntime(FakeBaselines(), sink).process(window(views=None))
    assert outcome.decision.is_pending
    assert outcome.decision.is_spike is False
    assert sink.saved == []


def test_편집자가_1명이어도_조회수가_튀면_저장한다():
    """~~편집자 하한 미달은 저장 안 함~~ → 편집자 하한이 관문에서 빠졌다
    (WP-126). 1인 편집이어도 조회수가 튀면 진짜 이슈로 본다."""
    sink = FakeSink()
    SpikeRuntime(FakeBaselines(), sink).process(window(editors=1))
    assert len(sink.saved) == 1


def test_sink가_없으면_판정만_한다():
    outcome = SpikeRuntime(FakeBaselines()).process(window())
    assert outcome.decision.is_spike is True
    assert outcome.persisted is False


# ------------------------------------------------- DB 기준선이 detector 에 들어간다

def test_DB_기준선_객체가_판정에_그대로_쓰인다():
    """🔴 이 스토리의 핵심. 메모리에서 다시 만든 값이면 이 동일성이 깨진다."""
    baseline = thick(edit_ewma=2.0, edit_stddev=1.0)
    baselines = FakeBaselines({("enwiki", "Hurricane Milton", 19): baseline})

    outcome = SpikeRuntime(baselines).process(window(edits=20, editors=5))

    assert outcome.baseline is baseline            # 조회한 그 객체
    assert baselines.asked == [("enwiki", "Hurricane Milton", 19)]
    assert outcome.decision.is_new_page is False   # 기준선이 있으니 기존 문서 경로
    assert outcome.decision.edit_z == pytest.approx((20 - 2.0) / 1.0)


def test_기준선_슬롯은_window_start의_UTC시로_묻는다():
    baselines = FakeBaselines()
    SpikeRuntime(baselines).process(window(hour=3))
    assert baselines.asked == [("enwiki", "Hurricane Milton", 3)]


def test_밑줄_제목도_공백형으로_조회한다():
    baselines = FakeBaselines()
    SpikeRuntime(baselines).process(window(title="Hurricane_Milton"))
    assert baselines.asked == [("enwiki", "Hurricane Milton", 19)]


# ---------------------------------------------------------------- 기존 문서 z 경로

def test_기존_문서_z경로가_실제로_돈다():
    """WP-84 이전엔 sample_days 가 구조적으로 미달이라 한 번도 안 돌던 경로다."""
    sink = FakeSink()
    baselines = FakeBaselines({
        ("enwiki", "Strait of Hormuz", 19): thick(edit_ewma=2.0, edit_stddev=1.0),
    })
    outcome = SpikeRuntime(baselines, sink).process(
        window(edits=20, editors=5, title="Strait of Hormuz"))

    assert outcome.baseline_source == "db"
    assert outcome.decision.is_new_page is False
    assert outcome.decision.edit_z >= EDIT_Z_THRESHOLD
    assert outcome.decision.is_spike is True
    # 기존 문서 경로는 z 를 냈으므로 NULL 이 아니다 — 신규 문서 경로와 갈리는 지점.
    assert sink.saved[0]["decision"].edit_z is not None


def test_조회수_z가_임계_아래면_미탐이고_저장도_안_한다():
    """~~편집 z~~ → **조회수 z** 가 관문이다 (WP-126).

    상시 편집 문서(`Deaths in 2025`)는 편집이 늘 튀지만, 조회수가 평소면 확정되지 않는다.
    편집자 하한(WP-85)이 하던 일을 이 관문이 대신한다.
    """
    sink = FakeSink()
    baselines = FakeBaselines({
        ("enwiki", "Deaths in 2025", 19): thick(edit_ewma=18.0, edit_stddev=4.0,
                                                view_ewma=1_000.0, view_stddev=100.0),
    })
    outcome = SpikeRuntime(baselines, sink).process(
        window(edits=20, editors=5, views=1_100, title="Deaths in 2025"))

    assert outcome.decision.view_ratio < 2.0
    assert outcome.decision.is_spike is False
    assert sink.saved == []


def test_신규_문서_경로는_edit_z가_None이다():
    sink = FakeSink()
    SpikeRuntime(FakeBaselines(), sink).process(window())
    assert sink.saved[0]["decision"].edit_z is None
    assert sink.saved[0]["decision"].is_new_page is True


# ---------------------------------------------------------------- 없음 vs 얇음

def test_기준선_없음과_얇음을_구분한다():
    """detect() 는 둘 다 신규 문서 경로로 보내지만 원인이 다르다."""
    absent = SpikeRuntime(FakeBaselines()).process(window())
    assert absent.baseline_source == "absent"

    thin_baseline = Baseline(edit_ewma=1.0, edit_stddev=0.5, view_ewma=None,
                             sample_days=MIN_BASELINE_SAMPLE_DAYS - 1)
    thin = SpikeRuntime(
        FakeBaselines({("enwiki", "Hurricane Milton", 19): thin_baseline})
    ).process(window())
    assert thin.baseline_source == "thin"
    assert thin.decision.is_new_page is True      # 판정 경로는 같다


# ---------------------------------------------------------------- 시각 계약

def test_detected_at은_윈도우_끝이다():
    """now() 를 쓰면 2024년 급증이 전부 '오늘 감지' 로 남아 시간축이 무너진다."""
    sink = FakeSink()
    w = window()
    SpikeRuntime(FakeBaselines(), sink).process(w)
    assert sink.saved[0]["window_start"] == datetime(2024, 10, 6, 19, tzinfo=UTC)
    assert sink.saved[0]["detected_at"] == datetime(2024, 10, 6, 20, tzinfo=UTC)
    assert sink.saved[0]["detected_at"] - sink.saved[0]["window_start"] == timedelta(hours=1)


def test_naive_datetime은_막는다():
    """세션 시간대로 해석돼 9시간 밀리는 걸 경계에서 막는다."""
    with pytest.raises(ValueError, match="naive"):
        PageWindow(wiki="enwiki", title="X", window_start=datetime(2024, 10, 6, 19),
                   edit_count=10, editor_count=2)


def test_58_문자열은_UTC로_읽는다():
    assert parse_window_start("2024-10-06T19:00:00") == datetime(2024, 10, 6, 19, tzinfo=UTC)
    assert parse_window_start("2024-10-06T19:00:00Z") == datetime(2024, 10, 6, 19, tzinfo=UTC)


# ---------------------------------------------------------------- -58 행 변환 · 요약

def test_배치마다_기준선_캐시를_비운다():
    """🔴 LIVE 장수명 프로세스가 재적재된 기준선을 영원히 못 읽는 걸 막는다.

    한 배치 **안에서는** 문서당 한 번만 읽고(왕복 절약), 배치가 새로 시작하면 다시 읽는다.
    """
    slot = (2.0, 1.0, None, None, MIN_BASELINE_SAMPLE_DAYS + 7)   # ewma, sd, vw, vsd, days
    conn = FakeConn({("enwiki", "Hurricane Milton"): [(h, *slot) for h in range(24)]})
    runtime = SpikeRuntime(BaselineRepository(conn))

    batch = [window(hour=h, edits=20, editors=5) for h in (19, 20, 21)]
    runtime.process_all(batch)
    assert len(conn.calls) == 1          # 배치 안에서는 문서당 한 번

    runtime.process_all(batch)           # 다음 배치
    assert len(conn.calls) == 2          # 다시 읽는다 — stale 하지 않다


def test_process는_캐시를_유지한다():
    """건별 호출은 호출자가 명시적으로 고른 경로다 — 배치 경계가 아니다."""
    baselines = FakeBaselines()
    runtime = SpikeRuntime(baselines)
    runtime.process(window())
    runtime.process(window())
    assert baselines.invalidated == 0

    runtime.process_all([window()])
    assert baselines.invalidated == 1


# ---------------------------------------------------------------- window_end

def test_소스가_준_window_end를_쓴다():
    """스트리밍은 `window.end` 를 이미 낸다 — 상수로 다시 계산하지 않는다."""
    sink = FakeSink()
    w = PageWindow(
        wiki="enwiki", title="Hurricane Milton",
        window_start=datetime(2024, 10, 6, 19, tzinfo=UTC),
        window_end=datetime(2024, 10, 7, 1, tzinfo=UTC),        # 6시간 창
        edit_count=1, editor_count=2, views=CONFIRMING_VIEWS,
    )
    # WINDOW_HOURS(1) 로 다시 계산했다면 20:00 이 됐을 자리다.
    assert w.window_end == datetime(2024, 10, 7, 1, tzinfo=UTC)
    SpikeRuntime(FakeBaselines(), sink).process(w)
    assert sink.saved[0]["detected_at"] == datetime(2024, 10, 7, 1, tzinfo=UTC)


def test_window_end가_없으면_WINDOW_HOURS로_채운다():
    """-58 행에는 window_end 가 없다 — 정각 tumbling 이라 길이가 상수다."""
    assert window().window_end == datetime(2024, 10, 6, 20, tzinfo=UTC)


def test_행에_window_end가_있으면_읽는다():
    w = PageWindow.from_row({
        "wiki": "enwiki", "title": "Hurricane Milton",
        "window_start": "2024-10-06T19:00:00", "window_end": "2024-10-06T19:30:00",
        "edit_count": 10, "editor_count": 2,
    })
    assert w.window_end == datetime(2024, 10, 6, 19, 30, tzinfo=UTC)


def test_거꾸로_된_window_end는_막는다():
    with pytest.raises(ValueError, match="window_end"):
        PageWindow(wiki="enwiki", title="X",
                   window_start=datetime(2024, 10, 6, 19, tzinfo=UTC),
                   window_end=datetime(2024, 10, 6, 18, tzinfo=UTC),
                   edit_count=10, editor_count=2)


def test_Historical_Window_행에서_만든다():
    w = PageWindow.from_row({
        "wiki": "enwiki", "title": "Hurricane_Milton",
        "window_start": "2024-10-07T21:00:00", "hour_of_day": 21,
        "edit_count": 44, "editor_count": 16, "views": 0,
    })
    assert w.title == "Hurricane Milton"          # canonical
    assert w.hour_of_day == 21
    assert w.window_start == datetime(2024, 10, 7, 21, tzinfo=UTC)
    # 🔴 ~~-58 의 0 을 None 으로 바꾸지 않는다~~ → **바꾼다** (2026-09-18, WP-126).
    # -58 은 조회수 미적재를 0 으로 낸다. 2단계 계약에서 그 0 을 액면대로 받으면 판정이
    # 폐기가 되고, 폐기는 다시 안 본다 — 조회수가 나중에 도착해도 재판정 대상에서 빠진다.
    # 미도착으로 읽으면 후보 대기로 남는다. 확정 결과는 안 바뀐다(진짜 0 도 100 미만이라
    # 어차피 확정 불가). 근거는 PageWindow.from_row 독스트링.
    assert w.views is None


def test_요약이_판정과_기준선_출처를_센다():
    sink = FakeSink()
    baselines = FakeBaselines({
        ("enwiki", "Hurricane Milton", 19): thick(edit_ewma=2.0, edit_stddev=1.0),
    })
    runtime = SpikeRuntime(baselines, sink)
    summary = RuntimeSummary.of(runtime.iter_process([
        window(edits=20, editors=5),                          # db · 확정
        window(edits=1, hour=5),                              # absent · 확정(절대 하한)
        window(edits=1, hour=6, views=50),                    # absent · 미탐(조회수 부족)
        window(edits=1, hour=7, views=None),                  # absent · 후보 대기
    ]))
    assert summary.evaluated == 4
    assert summary.detected == 2
    # 🔴 후보 대기를 따로 센다 — 미탐과 섞으면 재판정 대상을 못 고른다 (WP-126)
    assert summary.pending_views == 1
    assert summary.persisted == 2
    assert summary.baseline_db == 1
    assert summary.baseline_absent == 3
    assert len(sink.saved) == 2
