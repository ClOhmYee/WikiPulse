"""pageview_complete 파싱·필터·시간 디코드·합산 검증 (WP-57). 네트워크 없이 돈다."""

from __future__ import annotations

import pytest

from batch.pageview import (
    PageviewRecord,
    SchemaMismatch,
    UnsupportedWiki,
    aggregate,
    decode_hourly,
    is_content_title,
    parse_row,
    project_for,
)


def row(project, title, page_id, access, daily, hourly):
    return f"{project} {title} {page_id} {access} {daily} {hourly}"


# ---------------------------------------------------------------- 시간 디코드

def test_시간_희소_인코딩_디코드():
    assert decode_hourly("C2G1") == {2: 2, 6: 1}
    assert decode_hourly("A5") == {0: 5}
    assert decode_hourly("X10") == {23: 10}      # X = 23시, 다자릿수
    assert decode_hourly("") == {}


def test_깨진_시간_인코딩은_SchemaMismatch():
    with pytest.raises(SchemaMismatch):
        decode_hourly("C2Z9")                     # Z 는 유효 시간 문자(A-X) 아님 → 잔여


# ---------------------------------------------------------------- 제목 필터

def test_dash_와_namespace_prefix_제외():
    assert is_content_title("Strait_of_Hormuz") is True
    assert is_content_title("-") is False
    assert is_content_title("Talk:Iran") is False
    assert is_content_title("Wikipedia:Sandbox") is False


def test_정상_제목의_콜론은_남긴다():
    # 🔴 단순 `:` 필터면 잘못 버려지는 문서
    assert is_content_title("Bang:_The_Story") is True
    assert is_content_title("Category:Ships") is False   # 알려진 prefix 는 제외


# ---------------------------------------------------------------- 행 파싱

def test_대상_project만_남긴다():
    assert parse_row(row("de.wikipedia", "Iran", "1", "desktop", "5", "A5"), "en.wikipedia") is None
    title, hours = parse_row(row("en.wikipedia", "Iran", "1", "desktop", "5", "A5"), "en.wikipedia")
    assert title == "Iran" and hours == {0: 5}


def test_컬럼수_다르면_SchemaMismatch():
    with pytest.raises(SchemaMismatch):
        parse_row("en.wikipedia Iran 1 desktop 5", "en.wikipedia")   # 5컬럼


def test_시간합이_daily_total과_다르면_SchemaMismatch():
    with pytest.raises(SchemaMismatch):
        parse_row(row("en.wikipedia", "Iran", "1", "desktop", "9", "A5"), "en.wikipedia")


# ---------------------------------------------------------------- project 매핑

def test_wiki_project_역매핑():
    assert project_for("enwiki") == "en.wikipedia"
    with pytest.raises(UnsupportedWiki):
        project_for("frwiki")


# ---------------------------------------------------------------- 합산

def test_access_method와_page_id를_가로질러_합산():
    lines = [
        row("en.wikipedia", "Iran", "111", "desktop", "5", "A5"),
        row("en.wikipedia", "Iran", "222", "mobile-web", "3", "A3"),   # 다른 page_id·access, 같은 0시
        row("en.wikipedia", "Iran", "111", "desktop", "2", "C2"),      # 2시
        row("de.wikipedia", "Iran", "9", "desktop", "9", "A9"),        # 다른 project → 무시
        row("en.wikipedia", "-", "9", "desktop", "9", "A9"),           # 제목없음 → 무시
    ]
    recs = {(r.title, r.ts_hour): r for r in
            aggregate(lines, "en.wikipedia", "enwiki", "user", "2025-06-12")}
    assert recs[("Iran", "2025-06-12T00:00:00")].views == 8     # 5 + 3 합산
    assert recs[("Iran", "2025-06-12T02:00:00")].views == 2
    assert recs[("Iran", "2025-06-12T00:00:00")].agent == "user"
    assert recs[("Iran", "2025-06-12T00:00:00")].wiki == "enwiki"


def test_빈줄은_건너뛴다():
    lines = ["", row("en.wikipedia", "Iran", "1", "desktop", "5", "A5"), "  "]
    recs = list(aggregate(lines, "en.wikipedia", "enwiki", "user", "2025-06-12"))
    assert len(recs) == 1 and recs[0] == PageviewRecord(
        "enwiki", "Iran", "2025-06-12T00:00:00", "user", 5)


# ---------------------------------------------------------------- CLI 배선

def test_dump_url_날짜_분해():
    from batch.pageview_ingest import dump_url
    assert dump_url("2025-06-12", "user") == (
        "https://dumps.wikimedia.org/other/pageview_complete/"
        "2025/2025-06/pageviews-20250612-user.bz2")


def test_ingest_agent가_받아서_합산_기록(tmp_path, monkeypatch):
    import bz2
    from batch import pageview_ingest
    from batch.ingest import Counts

    dump = tmp_path / "user.bz2"
    with bz2.open(dump, "wt", encoding="utf-8") as h:
        h.write(row("en.wikipedia", "Iran", "1", "desktop", "5", "A5") + "\n")
        h.write(row("en.wikipedia", "Iran", "2", "mobile-web", "3", "A3") + "\n")

    monkeypatch.setattr(pageview_ingest, "download", lambda url, cache: dump)
    written = []

    class FakeWriter:
        def write(self, event):
            written.append(event)

    counts = Counts()
    status = pageview_ingest.ingest_agent(
        "2025-06-12", "enwiki", "en.wikipedia", "user",
        tmp_path, FakeWriter(), counts)
    assert status == "ok"
    assert len(written) == 1                       # 같은 (title,0시) 합산
    assert written[0]["views"] == 8 and written[0]["agent"] == "user"


def test_ingest_agent_404는_결손(tmp_path, monkeypatch):
    import urllib.error
    from batch import pageview_ingest
    from batch.ingest import Counts

    def raise_404(url, cache):
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)

    monkeypatch.setattr(pageview_ingest, "download", raise_404)
    status = pageview_ingest.ingest_agent(
        "2025-06-12", "enwiki", "en.wikipedia", "spider",
        tmp_path, None, Counts())
    assert status == "missing"


# ---------------------------------------------------------------- 월 루프

def test_dates_in_month_윤년():
    from batch.pageview_ingest import dates_in_month
    feb = dates_in_month("2024-02")               # 윤년 29일
    assert feb[0] == "2024-02-01" and feb[-1] == "2024-02-29" and len(feb) == 29
    assert len(dates_in_month("2025-06")) == 30


def test_main_월루프_전날짜_순회_요약(monkeypatch):
    from batch import pageview_ingest

    seen = []

    def fake_ingest_date(date, *a, **k):
        seen.append(date)
        return "missing" if date.endswith("-15") else "ok"

    monkeypatch.setattr(pageview_ingest, "ingest_date", fake_ingest_date)
    rc = pageview_ingest.main(["--wiki", "enwiki", "--month", "2025-06"])
    assert rc == 0 and len(seen) == 30            # 30일 전부 순회
    assert seen[0] == "2025-06-01" and "2025-06-15" in seen


def test_main_전부결손이면_3(monkeypatch):
    from batch import pageview_ingest
    monkeypatch.setattr(pageview_ingest, "ingest_date", lambda *a, **k: "missing")
    assert pageview_ingest.main(["--date", "2025-06-12"]) == 3
