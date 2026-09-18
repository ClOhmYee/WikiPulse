"""후보 대기 보관·재판정 계약 (WP-128). DB 없이 대역으로 돈다.

실 PostgreSQL 왕복은 `db/tests/test_spike_candidate_sql.py`(SQL 계약)와
`tests/test_recheck_pg.py`(Docker 필요)가 본다. 여기서는 **무엇을 언제 보관하고 지우는지**를
고정한다 — 그게 이 이슈의 계약이다.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from spike.candidate_store import DueCandidate
from spike.detector import Baseline, DecisionStatus, MIN_ABSOLUTE_VIEWS
from spike.recheck import recheck
from spike.runtime import PageWindow, SpikeRuntime

UTC = timezone.utc
WINDOW_START = datetime(2025, 6, 12, 9, tzinfo=UTC)

#: 조회수 기준선 표본이 없는 문서를 절대 하한으로 통과시키는 값 (명세 §3.2 3번).
CONFIRMING_VIEWS = 5_000


def window(*, views=None, edits=12, title="Air India Flight 171", start=WINDOW_START):
    return PageWindow(wiki="enwiki", title=title, window_start=start,
                      edit_count=edits, editor_count=3, views=views)


class FakeBaselines:
    """기준선 없음 = 신규 문서 경로. 재판정 계약은 기준선 종류와 무관하다."""

    def __init__(self, baseline: Baseline | None = None) -> None:
        self.baseline = baseline

    def get(self, wiki, title, hour_of_day):
        return self.baseline

    def invalidate(self):
        pass


class FakeSink:
    def __init__(self):
        self.saved = []

    def page_id(self, wiki, title):
        return 7

    def save(self, **kwargs):
        self.saved.append(kwargs)
        return 7


class FakeStore:
    """`CandidateStore` 대역. 무엇이 보관·삭제됐는지만 기록한다."""

    def __init__(self, due=()):
        self.saved = {}
        self.dropped = []
        self.bumped = []
        self.expired_with = None
        self._due = list(due)

    def page_id(self, wiki, title):
        return 7

    def save(self, page_id, window):
        self.saved[(page_id, window.window_start)] = window

    def drop(self, page_id, window_start):
        self.dropped.append((page_id, window_start))
        self.saved.pop((page_id, window_start), None)

    def bump(self, page_id, window_start):
        self.bumped.append((page_id, window_start))

    def due(self, limit=1000):
        return list(self._due)[:limit]

    def expire(self, *, now, hours):
        self.expired_with = (now, hours)
        return 2

    def count(self):
        return len(self.saved)


class FakeConn:
    def __init__(self):
        self.committed = 0
        self.rolled_back = 0

    def commit(self):
        self.committed += 1

    def rollback(self):
        self.rolled_back += 1


# ------------------------------------------------- 보관 (runtime 쪽 계약)

def test_후보_대기는_보관소에_담긴다():
    """🔴 이게 없으면 조회수가 도착해도 재판정할 대상이 없다 — LIVE 가 확정을 못 낸다."""
    store = FakeStore()
    runtime = SpikeRuntime(FakeBaselines(), FakeSink(), candidates=store)

    outcome = runtime.process(window(views=None))

    assert outcome.decision.status is DecisionStatus.PENDING_VIEWS
    assert list(store.saved) == [(7, WINDOW_START)]


def test_확정되면_보관소에서_지운다():
    """재판정으로 확정된 윈도우가 남아 있으면 다음 실행이 같은 것을 또 판정한다."""
    store = FakeStore()
    sink = FakeSink()
    runtime = SpikeRuntime(FakeBaselines(), sink, candidates=store)

    outcome = runtime.process(window(views=CONFIRMING_VIEWS))

    assert outcome.decision.is_spike and len(sink.saved) == 1
    assert store.dropped == [(7, WINDOW_START)] and not store.saved


def test_폐기되면_보관소에서_지운다():
    """조회수가 왔는데 급등이 아니면 다시 볼 이유가 없다. 안 지우면 영영 쌓인다."""
    store = FakeStore()
    runtime = SpikeRuntime(FakeBaselines(), FakeSink(), candidates=store)

    outcome = runtime.process(window(views=MIN_ABSOLUTE_VIEWS - 1))

    assert outcome.decision.status is DecisionStatus.REJECTED
    assert store.dropped == [(7, WINDOW_START)]


def test_1단계_탈락은_보관도_안_한다():
    """편집 0건은 후보 자체가 아니다 — 조회수를 받아 볼 이유가 없다."""
    store = FakeStore()
    runtime = SpikeRuntime(FakeBaselines(), FakeSink(), candidates=store)

    runtime.process(PageWindow(wiki="enwiki", title="Cat", window_start=WINDOW_START,
                               edit_count=0, editor_count=0, views=None))

    assert not store.saved
    assert store.dropped == [(7, WINDOW_START)]      # 혹시 남아 있던 것도 정리한다


def test_보관소가_없으면_여태처럼_센다():
    """보관소는 선택이다. 안 주면 대기를 세기만 하고 버린다(WP-128 이전 동작)."""
    runtime = SpikeRuntime(FakeBaselines(), FakeSink())
    assert runtime.process(window(views=None)).decision.is_pending


# ------------------------------------------------- 재판정 (recheck 쪽 계약)

def due(views, *, page_id=7, start=WINDOW_START):
    return DueCandidate(source="live", page_id=page_id,
                        window=window(views=views, start=start), views=views)


def run(monkeypatch, store, *, dry_run=False, now=None):
    """recheck() 를 대역 저장소·싱크로 돌린다."""
    import spike.recheck as module

    conn = FakeConn()
    monkeypatch.setattr(module, "CandidateStore", lambda conn, source="live": store)
    monkeypatch.setattr(module, "SpikeSink", lambda conn, source="live": FakeSink())
    monkeypatch.setattr(module, "BaselineRepository", lambda conn: FakeBaselines())
    summary = recheck(conn, dry_run=dry_run, now=now)
    return summary, conn


def test_조회수가_도착한_대기를_확정한다(monkeypatch):
    store = FakeStore(due=[due(CONFIRMING_VIEWS)])
    summary, conn = run(monkeypatch, store)

    assert (summary.rechecked, summary.confirmed, summary.rejected) == (1, 1, 0)
    assert store.dropped == [(7, WINDOW_START)]
    assert conn.committed == 1


def test_급등이_아니면_폐기하고_지운다(monkeypatch):
    store = FakeStore(due=[due(MIN_ABSOLUTE_VIEWS - 1)])
    summary, _ = run(monkeypatch, store)

    assert (summary.confirmed, summary.rejected) == (0, 1)
    assert store.dropped == [(7, WINDOW_START)]


def test_조회수_0도_판정이_끝난_것이다(monkeypatch):
    """⚠️ `page_view_hourly` 에 행이 있으면 그 시간 조회수를 실제로 받은 것이다.

    0 은 "아무도 안 봤다" 는 관측이라 폐기가 맞다. "원본 미도착" 은 행이 **없는** 것으로
    표현한다 (WP-127) — 그건 애초에 due() 에 안 걸린다.
    """
    store = FakeStore(due=[due(0)])
    summary, _ = run(monkeypatch, store)

    assert summary.rejected == 1 and store.dropped == [(7, WINDOW_START)]


def test_만료된_대기를_버린다(monkeypatch):
    """조회수가 영영 안 오는 문서가 있다(삭제·이동). 안 버리면 매번 다시 조회한다."""
    store = FakeStore()
    now = datetime(2026, 9, 18, 12, tzinfo=UTC)
    summary, _ = run(monkeypatch, store, now=now)

    assert summary.expired == 2
    assert store.expired_with[0] == now


def test_dry_run은_아무것도_안_쓰고_롤백한다(monkeypatch):
    store = FakeStore(due=[due(CONFIRMING_VIEWS)])
    summary, conn = run(monkeypatch, store, dry_run=True)

    assert summary.confirmed == 1           # 판정은 한다
    assert not store.dropped and store.expired_with is None
    assert conn.rolled_back == 1 and conn.committed == 0


def test_여러_건을_오래된_것부터_본다(monkeypatch):
    later = WINDOW_START + timedelta(hours=1)
    store = FakeStore(due=[due(CONFIRMING_VIEWS), due(0, start=later)])
    summary, _ = run(monkeypatch, store)

    assert (summary.rechecked, summary.confirmed, summary.rejected) == (2, 1, 1)
    assert [d[1] for d in store.dropped] == [WINDOW_START, later]
