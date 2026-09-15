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


def window(edits=MIN_ABSOLUTE_EDITS, editors=2, hour=19, views=None,
           title="Hurricane Milton"):
    return PageWindow(
        wiki="enwiki", title=title,
        window_start=datetime(2024, 10, 6, hour, tzinfo=UTC),
        edit_count=edits, editor_count=editors, views=views,
    )


def thick(edit_ewma=2.0, edit_stddev=1.0, **kw):
    """z 경로가 열리는 두꺼운 기준선."""
    return Baseline(edit_ewma=edit_ewma, edit_stddev=edit_stddev, view_ewma=None,
                    sample_days=MIN_BASELINE_SAMPLE_DAYS + 7, **kw)


# ---------------------------------------------------------------- 저장 여부

def test_급증이면_spike에_저장한다():
    sink = FakeSink()
    outcome = SpikeRuntime(FakeBaselines(), sink).process(window())
    assert outcome.decision.is_spike is True
    assert outcome.persisted is True
    assert len(sink.saved) == 1


def test_미탐이면_저장하지_않는다():
    """spike 는 '판정을 통과한 문서' 다 (V1 테이블 주석)."""
    sink = FakeSink()
    outcome = SpikeRuntime(FakeBaselines(), sink).process(
        window(edits=MIN_ABSOLUTE_EDITS - 1))
    assert outcome.decision.is_spike is False
    assert outcome.persisted is False
    assert sink.saved == []


def test_편집자_하한_미달도_저장하지_않는다():
    sink = FakeSink()
    SpikeRuntime(FakeBaselines(), sink).process(window(editors=1))
    assert sink.saved == []


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


def test_z가_임계_아래면_미탐이고_저장도_안_한다():
    sink = FakeSink()
    baselines = FakeBaselines({
        ("enwiki", "Deaths in 2025", 19): thick(edit_ewma=18.0, edit_stddev=4.0),
    })
    outcome = SpikeRuntime(baselines, sink).process(
        window(edits=20, editors=5, title="Deaths in 2025"))

    assert outcome.decision.edit_z < EDIT_Z_THRESHOLD
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
        edit_count=MIN_ABSOLUTE_EDITS, editor_count=2,
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
    assert w.views == 0                           # -58 의 0 을 None 으로 바꾸지 않는다


def test_요약이_판정과_기준선_출처를_센다():
    sink = FakeSink()
    baselines = FakeBaselines({
        ("enwiki", "Hurricane Milton", 19): thick(edit_ewma=2.0, edit_stddev=1.0),
    })
    runtime = SpikeRuntime(baselines, sink)
    summary = RuntimeSummary.of(runtime.iter_process([
        window(edits=20, editors=5),                       # db · 급증
        window(edits=MIN_ABSOLUTE_EDITS, hour=5),          # absent · 급증(신규 경로)
        window(edits=1, hour=6),                           # absent · 미탐
    ]))
    assert summary.evaluated == 3
    assert summary.detected == 2
    assert summary.persisted == 2
    assert summary.baseline_db == 1
    assert summary.baseline_absent == 2
    assert len(sink.saved) == 2
