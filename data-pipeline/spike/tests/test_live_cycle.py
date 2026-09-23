"""LIVE 시간 주기 계약 (WP-135). DB·네트워크는 대역이다.

여기서 고정하는 것은 **무엇을 받을지 고르는 규칙**이다 — 그게 이 모듈의 존재 이유다.
전수 적재(시간당 149만 행)를 피하려고 대기 목록에서 시간·문서를 뽑는다.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from spike import live_cycle
from spike.live_cycle import AVAILABLE_AFTER_HOURS, CycleSummary, missing_views, run_once
from spike.recheck import RecheckSummary

UTC = timezone.utc
NOW = datetime(2026, 9, 18, 8, 30, tzinfo=UTC)


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows
        self.params = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        self.params = params

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return (True,)


class FakeConn:
    def __init__(self, rows=()):
        self.cursor_obj = FakeCursor(list(rows))
        self.rolled_back = 0

    def cursor(self):
        return self.cursor_obj

    def rollback(self):
        self.rolled_back += 1

    def commit(self):
        pass


def row(hour: datetime, title: str):
    return (hour, title)


# ---------------------------------------------------------------- 대상 고르기

def test_시간별로_문서를_묶는다():
    """한 시간 파일을 한 번만 받고, 그 안에서 필요한 문서만 거른다."""
    nine = datetime(2026, 9, 18, 5, tzinfo=UTC)
    ten = datetime(2026, 9, 18, 6, tzinfo=UTC)
    conn = FakeConn([row(nine, "Air India Flight 171"), row(nine, "Boeing 787"),
                     row(ten, "Air India Flight 171")])

    due = missing_views(conn, "live", now=NOW)

    assert [h for h, _ in due] == ["2026-09-18T05:00:00", "2026-09-18T06:00:00"]
    assert due[0][1] == frozenset({"Air India Flight 171", "Boeing 787"})


def test_아직_안_나온_시간은_안_받는다():
    """🔴 덤프는 윈도우 끝 기준 약 2시간 뒤에 나온다 (실측 125~153분).

    그 전에 받으면 404 라 헛다운로드다. 질의 자체에서 잘라 낸다.
    """
    conn = FakeConn([])
    missing_views(conn, "live", now=NOW)

    cutoff = conn.cursor_obj.params[1]
    assert cutoff == NOW - timedelta(hours=AVAILABLE_AFTER_HOURS)


def test_한_주기_시간_수를_제한한다():
    """밀린 구간을 따라잡되 한 주기가 무한정 길어지지 않게. 오래된 시간부터 받는다."""
    hours = [datetime(2026, 9, 18, h, tzinfo=UTC) for h in range(0, 6)]
    conn = FakeConn([row(h, "Doc") for h in hours])

    due = missing_views(conn, "live", now=NOW, max_hours=2)

    assert [h for h, _ in due] == ["2026-09-18T00:00:00", "2026-09-18T01:00:00"]


def test_출처를_질의에_넘긴다():
    conn = FakeConn([])
    missing_views(conn, "replay", now=NOW)
    assert conn.cursor_obj.params[0] == "replay"


# ---------------------------------------------------------------- 한 주기

@pytest.fixture()
def stub_cycle(monkeypatch):
    """적재·재판정을 대역으로 바꾼다. 무엇을 어떤 인자로 불렀는지만 본다."""
    calls = {"ingest": [], "recheck": 0, "prune": []}

    def fake_ingest(ts_hour, wiki, cache_dir, out_root, *, titles, shard_records,
                    dry_run, conn, min_views=None):
        calls["ingest"].append((ts_hour, titles, min_views))
        return "pending" if ts_hour.endswith("T07:00:00") else "ok"

    def fake_recheck(conn, *, source="live", dry_run=False, **kwargs):
        calls["recheck"] += 1
        return RecheckSummary(rechecked=2, confirmed=1, rejected=1)

    def fake_prune(cache_dir, **kwargs):
        calls["prune"].append(cache_dir)
        return 3

    monkeypatch.setattr(live_cycle, "ingest_hour", fake_ingest)
    monkeypatch.setattr(live_cycle, "recheck", fake_recheck)
    monkeypatch.setattr(live_cycle, "prune_cache", fake_prune)
    return calls


def test_대기_목록의_문서만_받는다(stub_cycle, tmp_path):
    """🔴 이 모듈의 존재 이유. 전수는 시간당 149만 행이라 못 받는다 (WP-127 실측)."""
    five = datetime(2026, 9, 18, 5, tzinfo=UTC)
    conn = FakeConn([row(five, "Air India Flight 171"), row(five, "Boeing 787")])

    summary = run_once(conn, cache_dir=tmp_path, out_root=tmp_path, now=NOW)

    assert stub_cycle["ingest"] == [
        ("2026-09-18T05:00:00", frozenset({"Air India Flight 171", "Boeing 787"}), None)]
    assert (summary.hours_due, summary.hours_ingested, summary.titles) == (1, 1, 2)


def test_아직_안_나온_파일은_대기로_센다(stub_cycle, tmp_path):
    """404 는 실패가 아니다 — 다음 주기가 다시 본다."""
    conn = FakeConn([row(datetime(2026, 9, 18, 7, tzinfo=UTC), "Doc")])

    summary = run_once(conn, cache_dir=tmp_path, out_root=tmp_path,
                       now=NOW + timedelta(hours=3))

    assert (summary.hours_ingested, summary.hours_pending) == (0, 1)


def test_받을_게_없어도_재판정은_돈다(stub_cycle, tmp_path):
    """조회수가 이미 들어와 있는 대기가 있을 수 있다 — 적재와 재판정은 별개 단계다."""
    summary = run_once(FakeConn([]), cache_dir=tmp_path, out_root=tmp_path, now=NOW)

    assert stub_cycle["ingest"] == [] and stub_cycle["recheck"] == 1
    assert summary.recheck.confirmed == 1


def test_dry_run은_받지_않는다(stub_cycle, tmp_path):
    conn = FakeConn([row(datetime(2026, 9, 18, 5, tzinfo=UTC), "Doc")])

    summary = run_once(conn, cache_dir=tmp_path, out_root=tmp_path, now=NOW, dry_run=True)

    assert stub_cycle["ingest"] == []       # 다운로드 없음
    assert summary.hours_due == 1           # 무엇을 받을지는 보여준다
    assert stub_cycle["prune"] == []        # WP-171: dry-run 은 아무것도 안 지운다


# ---------------------------------------------------------------- 캐시 정리 (WP-171)

def test_주기가_끝나면_캐시를_정리한다(stub_cycle, tmp_path):
    """ingest_hour() 만 직접 부르는 이 서비스가 실제로 도는 자리라, main() 이 아니라
    여기서 prune_cache 를 불러야 배포된 live-cycle 에 실제로 걸린다."""
    summary = run_once(FakeConn([]), cache_dir=tmp_path, out_root=tmp_path, now=NOW)

    assert stub_cycle["prune"] == [tmp_path]
    assert summary.cache_pruned == 3
    assert "캐시 정리 3" in summary.format()


# ---------------------------------------------------------------- 요약·락

def test_요약에_경과_시간이_들어간다(stub_cycle, tmp_path):
    """명세 §3.2 3번 "원본 도착 후 내부 처리 15분 이내" 를 재려면 주기 시간이 필요하다."""
    summary = run_once(FakeConn([]), cache_dir=tmp_path, out_root=tmp_path, now=NOW)
    assert summary.seconds >= 0
    assert "s" in summary.format()


def test_advisory_lock을_잡는다():
    """⚠️ 두 주기가 겹치면 같은 45 MB 파일을 두 번 받는다. 세션 락이라 프로세스가 죽어도 풀린다."""
    conn = FakeConn([])
    assert live_cycle.try_lock(conn) is True
    assert conn.cursor_obj.params == (live_cycle.LOCK_KEY,)


def test_빈_요약도_읽힌다():
    assert "시간 0/0" in CycleSummary().format()


# -------------------------------- 기준선용 하한 적재 (WP-212)

def test_하한을_주면_적재로_넘어간다(stub_cycle, tmp_path):
    """🔴 후보 문서만 받으면 `page_baseline` 을 만들 이력이 안 쌓인다.

    기준선은 (문서, 시간대) 별 28일치가 필요한데, "그 시간에 편집이 있던 날" 의
    조회수만 있으면 `sample_days` 가 1 근처에서 멈춘다 — `-162` 가 replay 에서
    겪은 문제와 같은 것이다.
    """
    five = datetime(2026, 9, 18, 5, tzinfo=UTC)
    conn = FakeConn([row(five, "Air India Flight 171")])

    run_once(conn, cache_dir=tmp_path, out_root=tmp_path, now=NOW, min_views=50)

    assert stub_cycle["ingest"][0][2] == 50


def test_하한은_기본으로_안_걸린다(stub_cycle, tmp_path):
    """기본값이 안 바뀌는 것을 고정한다 — 켜면 행이 는다(시간당 약 17,400)."""
    five = datetime(2026, 9, 18, 5, tzinfo=UTC)
    conn = FakeConn([row(five, "Doc")])

    run_once(conn, cache_dir=tmp_path, out_root=tmp_path, now=NOW)

    assert stub_cycle["ingest"][0][2] is None


# -------------------------------- 하루 한 번 기준선 (WP-212)

from datetime import date  # noqa: E402

from spike.live_cycle import (  # noqa: E402
    BASELINE_LAG_HOURS, baseline_as_of, maybe_refresh_baseline)
from spike.candidate_store import DEFAULT_EXPIRE_HOURS  # noqa: E402


def test_기준선_창은_살아_있는_대기의_날을_안_덮는다():
    """🔴 급등 자신이 기준선에 섞이면 EWMA 최근 가중 때문에 배수가 깎여 진짜 급등이
    폐기된다. 만료 직전 대기(윈도우 끝 + 36시간)의 날보다 as_of 가 반드시 앞선다."""
    for minute in range(0, 24 * 60, 7):
        now = datetime(2026, 9, 23, tzinfo=UTC) + timedelta(minutes=minute)
        # 아직 안 만료된 가장 오래된 대기의 윈도우 시작
        oldest_pending = now - timedelta(hours=DEFAULT_EXPIRE_HOURS + 1)
        assert baseline_as_of(now) < oldest_pending.date(), now


def test_기준선_지연은_만료보다_길다():
    assert BASELINE_LAG_HOURS > DEFAULT_EXPIRE_HOURS


@pytest.fixture()
def stub_baseline(monkeypatch):
    calls = []

    def fake_run(conn, *, wiki, as_of):
        calls.append(as_of)
        return {"observations": 10, "rows": 2, "thin": 2, "written": 2}

    monkeypatch.setattr(live_cycle.baseline_from_views, "run", fake_run)
    return calls


def test_날이_바뀔_때만_기준선을_굴린다(stub_baseline):
    conn = FakeConn()
    first = maybe_refresh_baseline(conn, now=NOW, last_as_of=None)
    again = maybe_refresh_baseline(conn, now=NOW + timedelta(hours=1), last_as_of=first)
    next_day = maybe_refresh_baseline(conn, now=NOW + timedelta(days=1), last_as_of=again)

    assert first == again == baseline_as_of(NOW)
    assert next_day == first + timedelta(days=1)
    assert stub_baseline == [first, next_day]      # 같은 날 두 번째는 안 돈다


def test_기준선이_실패해도_주기를_안_죽이고_다음에_다시_한다(monkeypatch):
    """🔴 기준선이 하루 늦는 건 fallback 이 받지만, 적재가 멈추면 이력이 끊긴다."""
    def boom(conn, **kwargs):
        raise RuntimeError("db gone")

    monkeypatch.setattr(live_cycle.baseline_from_views, "run", boom)
    conn = FakeConn()
    prev = date(2026, 9, 1)
    assert maybe_refresh_baseline(conn, now=NOW, last_as_of=prev) == prev
    assert conn.rolled_back == 1
