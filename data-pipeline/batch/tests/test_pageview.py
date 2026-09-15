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


# ------------------------------------------- canonical title (WP-79)
#
# 왜 여기서 보나 — pageview 는 baseline `view_ewma` 입력이고, 편집 경로와
# `(wiki, title)` 로 조인된다. 키가 갈라지면 예외 없이 "조회수가 없는 문서"가 되어
# 급증 2차 판정이 조용히 틀린다. 근거: 명세 §3.2 3번·§5.1.
#
# ⚠️ 덤프 계약상 **제목에 리터럴 공백은 올 수 없다.** 6컬럼을 `" "` 로 자르는 형식이라
#   공백이 든 제목은 7필드가 되어 SchemaMismatch 로 떨어진다. 그래서 "공백형 제목이
#   덤프에 섞여 들어오는" 시나리오는 인위적이라 만들지 않는다. 덤프 안에서 실제로
#   흔들릴 수 있는 건 밑줄 표기(연속·앞뒤)뿐이고, 공백형과의 대조는 아래
#   `test_pageview_와_편집경로가_같은_키를_낸다` 가 소스 간 조인으로 확인한다.

from producer.normalize import canonical_title, normalize  # noqa: E402


def test_밑줄_제목이_canonical_공백형으로_나온다():
    """핵심 회귀. 덤프는 `Hurricane_Milton`, 내부 canonical 은 `Hurricane Milton`."""
    title, hours = parse_row(
        row("en.wikipedia", "Hurricane_Milton", "780", "desktop", "5", "A5"),
        "en.wikipedia",
    )
    assert title == "Hurricane Milton"
    assert hours == {0: 5}


@pytest.mark.parametrize(
    "dump_title",
    ["Hurricane_Milton", "Hurricane__Milton", "_Hurricane_Milton_", "Hurricane___Milton"],
)
def test_밑줄_표기가_흔들려도_같은_canonical(dump_title):
    """연속·앞뒤 밑줄은 덤프 표본에서 본 적 없다. 봐도 키가 안 갈라지게 방어한다."""
    title, _ = parse_row(
        row("en.wikipedia", dump_title, "780", "desktop", "5", "A5"), "en.wikipedia"
    )
    assert title == "Hurricane Milton"


def test_canonical_은_멱등이다():
    once = canonical_title("_Hurricane__Milton_")
    assert canonical_title(once) == once == "Hurricane Milton"


def test_표기만_다른_같은_문서가_한_키로_합산된다():
    """합산 **전에** canonical 이 걸리는지 보는 테스트.

    출력 직전에만 문자열을 바꾸면 `acc` 가 이미 원형으로 그룹을 갈라 놓은 뒤라
    같은 0시가 레코드 두 개로 나온다. 여기서 views 8 이 나와야 시점이 맞는 것이다.
    """
    lines = [
        row("en.wikipedia", "Hurricane_Milton", "780", "desktop", "5", "A5"),
        row("en.wikipedia", "Hurricane__Milton", "781", "mobile-web", "3", "A3"),
    ]
    recs = list(aggregate(lines, "en.wikipedia", "enwiki", "user", "2024-10-09"))
    assert len(recs) == 1, f"키가 갈라졌다: {[r.title for r in recs]}"
    assert recs[0] == PageviewRecord(
        "enwiki", "Hurricane Milton", "2024-10-09T00:00:00", "user", 8)


def test_pageview_와_편집경로가_같은_키를_낸다():
    """소스 간 조인 키 확인. 이게 깨지면 조회수와 편집량이 서로 다른 행이 된다."""
    title, _ = parse_row(
        row("en.wikipedia", "Strait_of_Hormuz", "1", "desktop", "5", "A5"), "en.wikipedia"
    )
    live = normalize({
        "meta": {"domain": "en.wikipedia.org", "id": "x", "dt": "2026-09-08T00:24:20.990Z"},
        "type": "edit", "namespace": 0, "title": "Strait of Hormuz",
        "user": "Alice", "bot": False, "minor": False,
        "length": {"old": 1000, "new": 1100}, "revision": {"old": 10, "new": 11},
        "wiki": "enwiki",
    })
    assert title == live["title"] == "Strait of Hormuz"


def test_canonical_이_namespace_필터보다_뒤에_걸린다():
    """순서 회귀. canonical 을 앞으로 옮기면 `User_talk` 가 `User talk` 가 되어
    prefix 목록과 일치하지 않고, namespace 문서가 ns0 로 새어 들어온다."""
    for ns_title in ["User_talk:Alice", "Template_talk:Infobox", "Image_talk:X.png"]:
        assert parse_row(
            row("en.wikipedia", ns_title, "1", "desktop", "5", "A5"), "en.wikipedia"
        ) is None, f"{ns_title} 가 통과했다 — canonical 적용 시점이 앞으로 밀렸다"


def test_다른_문서는_여전히_다른_키다():
    """정규화가 서로 다른 문서를 뭉쳐버리지 않는지. 반대 방향 확인."""
    a, _ = parse_row(row("en.wikipedia", "Hurricane_Milton", "1", "d", "5", "A5"), "en.wikipedia")
    b, _ = parse_row(row("en.wikipedia", "Hurricane_Helene", "2", "d", "5", "A5"), "en.wikipedia")
    assert a != b
