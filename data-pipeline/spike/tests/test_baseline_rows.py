"""기준선 행 산출·적재 검증 (WP-60). Spark·DB 없이 돈다."""

from __future__ import annotations

from datetime import date

import pytest

from spike.baseline_rows import BASELINE_WINDOW_DAYS, build_rows
from spike.baseline_sink import (
    RESOLVE_PAGE_SQL,
    UPSERT_BASELINE_SQL,
    resolve_page_ids,
    upsert_rows,
)
from spike.detector import MIN_BASELINE_SAMPLE_DAYS, Baseline, Window, detect


def win(day, slot_hour, edits, views=None, wiki="enwiki", title="Iran"):
    """-58 산출물 한 행. 시각을 주면 slot_index(= 시각 // 6)를 맞춰 둔다."""
    return {"wiki": wiki, "title": title, "slot_index": slot_hour // 6,
            "window_start": f"{day}T{slot_hour % 24:02d}:00:00",
            "edit_count": edits, "views": views}


# ---------------------------------------------------------------- EWMA 산출

def test_최근_관측이_더_무겁다():
    # 같은 슬롯, 2025-06-09(최근) 10편집 / 2025-05-26(14일 전) 0편집
    rows = build_rows([win("2025-06-09", 0, 10), win("2025-05-26", 0, 0)],
                      as_of=date(2025, 6, 9), halflife_days=14.0)
    assert len(rows) == 1
    # 가중 (10*1 + 0*0.5) / 1.5 = 6.667 — 단순평균 5 보다 크다
    assert rows[0].edit_ewma == pytest.approx(6.6667, abs=1e-3)


def test_조회수도_같은_가중():
    rows = build_rows([win("2025-06-09", 0, 1, views=100),
                       win("2025-05-26", 0, 1, views=0)],
                      as_of=date(2025, 6, 9), halflife_days=14.0)
    assert rows[0].view_ewma == pytest.approx(66.6667, abs=1e-3)


def test_조회수_전부_결측이면_view_ewma_None():
    rows = build_rows([win("2025-06-09", 0, 3, views=None)], as_of=date(2025, 6, 9))
    assert rows[0].view_ewma is None
    assert rows[0].edit_ewma == 3.0


# ---------------------------------------------------------------- 28일 경계

def test_창_밖_관측은_버린다():
    # as_of 기준 29일 전은 창 밖(경계는 (as_of-28, as_of])
    rows = build_rows([win("2025-06-30", 0, 10), win("2025-06-01", 0, 999)],
                      as_of=date(2025, 6, 30), halflife_days=1e9)
    assert len(rows) == 1
    assert rows[0].edit_ewma == 10.0          # 999 는 안 섞였다
    assert rows[0].sample_days == 1


def test_창_경계_정확히_28일전은_포함():
    as_of = date(2025, 6, 30)
    edge = date.fromordinal(as_of.toordinal() - (BASELINE_WINDOW_DAYS - 1))
    rows = build_rows([win(edge.isoformat(), 0, 5)], as_of=as_of, halflife_days=1e9)
    assert len(rows) == 1 and rows[0].edit_ewma == 5.0


def test_창_안에_관측이_없으면_행을_안_낸다():
    # 기준선 없음과 기준선 0 은 다른 뜻이다 — detector 가 None 을 신규 문서로 본다
    rows = build_rows([win("2025-01-01", 0, 10)], as_of=date(2025, 6, 30))
    assert rows == []


# ---------------------------------------------------------------- sample_days

def test_sample_days는_고유_날짜수():
    # 같은 날 두 행(다른 슬롯 아님, 같은 슬롯)이면 하루로 센다
    rows = build_rows([win("2025-06-09", 0, 1), win("2025-06-09", 0, 2),
                       win("2025-06-02", 0, 3)],
                      as_of=date(2025, 6, 9))
    assert rows[0].sample_days == 2


def test_얇은_baseline은_detector가_신규문서로_보낸다():
    rows = build_rows([win("2025-06-09", 0, 5)], as_of=date(2025, 6, 9))
    baseline = Baseline(rows[0].edit_ewma, rows[0].edit_stddev,
                        rows[0].view_ewma, rows[0].sample_days)
    assert rows[0].sample_days < MIN_BASELINE_SAMPLE_DAYS
    assert baseline.is_thin is True
    # 얇으면 z 를 안 쓰고 절대 편집수 경로 — 편집 3건은 미달
    assert detect(Window(edit_count=3, editor_count=1, views=None), baseline).is_spike is False


def test_두꺼운_baseline은_z경로로_간다():
    # 7일치 평상시 1편집 -> 급증 20편집이면 잡혀야 한다
    days = [f"2025-06-{d:02d}" for d in range(3, 10)]
    rows = build_rows([win(d, 0, 1) for d in days], as_of=date(2025, 6, 9),
                      halflife_days=1e9)
    row = rows[0]
    assert row.sample_days == 7 and row.edit_stddev == pytest.approx(0.0)
    baseline = Baseline(row.edit_ewma, row.edit_stddev, row.view_ewma, row.sample_days)
    assert baseline.is_thin is False
    # stddev 0 이면 z 계산 불가 -> detector 가 편집 미달로 처리(조용히 통과시키지 않는다)
    assert detect(Window(edit_count=20, editor_count=3, views=None), baseline).is_spike is False


def test_변동있는_baseline에서_급증이_잡힌다():
    """산출한 행을 detector 에 그대로 먹였을 때 실제 급증이 통과하는지.

    평상시 1~3 편집(7일) -> 40 편집이면 z 가 임계를 넘고 절대 하한도 넘는다.
    """
    counts = [1, 3, 2, 1, 3, 2, 1]
    days = [f"2025-06-{d:02d}" for d in range(3, 10)]
    rows = build_rows([win(d, 0, c) for d, c in zip(days, counts)],
                      as_of=date(2025, 6, 9), halflife_days=1e9)
    row = rows[0]
    assert row.sample_days == 7 and row.edit_stddev > 0

    baseline = Baseline(row.edit_ewma, row.edit_stddev, row.view_ewma, row.sample_days)
    decision = detect(Window(edit_count=40, editor_count=5, views=None), baseline)
    assert decision.is_spike is True
    assert decision.is_new_page is False
    assert decision.edit_z > 3.0                      # EDIT_Z_THRESHOLD
    # 조회수가 아직 없으면 확정이 아니라 '감지됨' 상태 (detector 계약)
    assert "조회수" in decision.reason


# ---------------------------------------------------------------- 적재 SQL

class FakeCursor:
    """psycopg 커서 흉내. 실행된 SQL·파라미터를 기록한다."""

    def __init__(self):
        self.calls: list[tuple[str, object]] = []
        self.many: list[tuple[str, list]] = []
        self._next_id = 100

    def execute(self, sql, params=None):
        self.calls.append((sql, params))

    def executemany(self, sql, seq):
        self.many.append((sql, list(seq)))

    def fetchone(self):
        self._next_id += 1
        return (self._next_id,)


def test_page_id_해석은_고유키당_한_번():
    cur = FakeCursor()
    keys = [("enwiki", "Iran")] * 24 + [("enwiki", "Milton")]
    resolved = resolve_page_ids(cur, keys)
    assert len(cur.calls) == 2                      # 24번이 아니라 고유 2번
    assert set(resolved) == {("enwiki", "Iran"), ("enwiki", "Milton")}
    assert "ON CONFLICT (wiki, title) DO UPDATE" in RESOLVE_PAGE_SQL
    assert "RETURNING id" in RESOLVE_PAGE_SQL       # DO NOTHING 이면 id 를 못 받는다


def test_upsert는_PK충돌시_갱신():
    assert "ON CONFLICT (page_id, slot_index) DO UPDATE" in UPSERT_BASELINE_SQL
    assert "updated_at  = now()" in UPSERT_BASELINE_SQL

    rows = build_rows([win("2025-06-09", 0, 4, views=10)], as_of=date(2025, 6, 9))
    cur = FakeCursor()
    written = upsert_rows(cur, rows, {("enwiki", "Iran"): 7})
    assert written == 1
    sql, params = cur.many[0]
    # page_id 가 앞에 붙고, view_stddev 가 view_ewma 뒤에 온다 (WP-90).
    # 관측이 하나뿐이라 두 표준편차가 다 0.0 이다 — None(표본 없음)과 다른 뜻이다.
    assert params == [(7, 0, 4.0, 0.0, 10.0, 0.0, 1)]


def test_같은_입력을_두_번_돌려도_같은_파라미터():
    """멱등성의 산출 쪽. 실제 행 수 불변은 실 PostgreSQL 로 확인해야 한다(README)."""
    windows = [win("2025-06-09", 0, 4), win("2025-06-02", 0, 2)]
    first = build_rows(windows, as_of=date(2025, 6, 9))
    second = build_rows(windows, as_of=date(2025, 6, 9))
    assert first == second
