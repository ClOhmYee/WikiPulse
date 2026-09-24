"""실제 PostgreSQL에서 대표 문서 묶음·리포트 시점 SQL을 롤백 격리로 검증한다."""
from pathlib import Path
import re

from conftest import q, x


SOURCE = (Path(__file__).parents[2] / "backend/src/main/java/io/wikipulse/backend/issue/IssueQueryRepository.java").read_text(encoding="utf-8-sig")


def query_for(method):
    method_at = SOURCE.index(method + "(")
    annotation_at = SOURCE.rfind('@Query(value = """', 0, method_at)
    assert annotation_at >= 0
    start = annotation_at + len('@Query(value = """')
    end = SOURCE.index('"""', start)
    return re.sub(r":([A-Za-z]\w*)", r"%(\1)s", SOURCE[start:end].replace("%", "%%"))


def run(conn, method, params):
    with conn.cursor() as cur:
        cur.execute(query_for(method), params)
        return cur.fetchall()


def cluster(conn, key, label, ts, source="replay", status="CONFIRMED", complete=True):
    if complete:
        x(conn, "INSERT INTO cluster_snapshot(snapshot_ts,source,score_version) VALUES (%s,%s,'v1') ON CONFLICT DO NOTHING", ts, source)
    return q(conn, "INSERT INTO issue_cluster(snapshot_ts,source,issue_key,label,pulse_score,status) VALUES (%s,%s,%s,%s,10,%s) RETURNING id", ts, source, key, label, status)[0][0]


def report(conn, cid, full=False):
    x(conn, "INSERT INTO issue_report(cluster_id,summary,model,report_sections) VALUES (%s,'요약','test',%s)", cid, '[{"id":"overview","title":"개요","body":"본문","evidenceIds":[]}]' if full else None)


def group_params(**changes):
    return dict(pattern=None, status=None, source=None, offset=0, limit=20) | changes


def test_same_wiki_document_across_sources_has_one_card_and_shared_report_dates(conn):
    replay = cluster(conn, "replay:enwiki:The Odyssey (2026 film)", "The Odyssey (2026 film)",
                     "2040-07-17T01:00:00Z")
    report(conn, replay, full=True)
    live = cluster(conn, "live:enwiki:The Odyssey (2026 film)", "The Odyssey (2026 film)",
                   "2040-07-19T01:00:00Z", source="live")
    different_page = cluster(conn, "live:enwiki:The Odyssey (1997 miniseries)",
                             "The Odyssey (2026 film)", "2040-07-20T01:00:00Z", source="live")

    rows = run(conn, "findHistoryGroups", group_params())
    by_id = {row[0]: row for row in rows}
    assert set(by_id) == {live, different_page}
    assert by_id[live][7] == 2  # occurrenceCount, both sources
    assert by_id[live][8] == replay  # full report from replay
    assert run(conn, "countHistoryGroups", group_params())[0][0] == 2
    assert [row[0] for row in run(conn, "findHistoryGroups", group_params(source="live"))] == [different_page, live]
    assert run(conn, "findHistoryGroups", group_params(source="live"))[1][8] is None

    params = dict(anchorId=live, issueKey="enwiki:The Odyssey (2026 film)",
                  source="live", offset=0, limit=100)
    assert [row[0] for row in run(conn, "findHistoryReports", params)] == [replay]
    assert run(conn, "countHistoryReports", params)[0][0] == 1


def test_groups_are_stable_across_dates_but_not_malformed_or_null_keys(conn):
    old = cluster(conn, "replay:enwiki:Odyssey", "Odyssey", "2040-07-17T01:00:00Z")
    latest = cluster(conn, "replay:enwiki:Odyssey", "Odyssey", "2040-07-18T01:00:00Z")
    report(conn, old, full=True)
    live = cluster(conn, "replay:enwiki:Odyssey", "Odyssey", "2040-07-19T01:00:00Z", source="live")
    same_label = cluster(conn, "other", "Odyssey", "2040-07-20T01:00:00Z")
    null_a = cluster(conn, None, "legacy", "2040-07-21T01:00:00Z")
    null_b = cluster(conn, None, "legacy", "2040-07-22T01:00:00Z")
    cluster(conn, "discarded", "Odyssey", "2040-07-23T01:00:00Z", status="DISCARDED")
    cluster(conn, "incomplete", "Odyssey", "2040-07-24T01:00:00Z", complete=False)

    rows = run(conn, "findHistoryGroups", group_params())
    by_id = {row[0]: row for row in rows}
    assert set(by_id) == {latest, live, same_label, null_a, null_b}
    assert by_id[latest][7] == 2  # occurrenceCount
    assert by_id[latest][8] == old  # defaultReportId
    assert by_id[live][7] == 1
    assert run(conn, "countHistoryGroups", group_params())[0][0] == 5
    assert [row[0] for row in run(conn, "findHistoryGroups", group_params(source="live"))] == [live]
    assert [row[0] for row in run(conn, "findHistoryGroups", group_params(offset=1, limit=2))] == [null_a, same_label]


def test_literal_search_and_latest_status_filter(conn):
    target = cluster(conn, "k", "100%_\\ Odyssey", "2040-07-17T01:00:00Z")
    cluster(conn, "other", "1000X Odyssey", "2040-07-18T01:00:00Z", status="DETECTED")
    for needle in ("%", "_", "\\"):
        escaped = needle.replace("!", "!!").replace("%", "!%").replace("_", "!_")
        rows = run(conn, "findHistoryGroups", group_params(pattern=f"%{escaped}%"))
        assert [row[0] for row in rows] == [target]
    assert [row[0] for row in run(conn, "findHistoryGroups", group_params(status="CONFIRMED"))] == [target]


def test_report_history_uses_only_report_rows_across_sources(conn):
    first = cluster(conn, "replay:enwiki:A", "A", "2040-07-17T01:00:00Z")
    middle = cluster(conn, "replay:enwiki:A", "A", "2040-07-17T02:00:00Z")
    last = cluster(conn, "replay:enwiki:A", "A", "2040-07-18T01:00:00Z")
    report(conn, first)
    report(conn, last, full=True)
    other = cluster(conn, "live:enwiki:A", "A", "2040-07-19T01:00:00Z", source="live")
    report(conn, other)
    params = dict(anchorId=middle, issueKey="enwiki:A", source="replay", offset=0, limit=100)
    assert [row[0] for row in run(conn, "findHistoryReports", params)] == [other, last, first]
    assert [row[4] for row in run(conn, "findHistoryReports", params)] == ["live", "replay", "replay"]
    assert run(conn, "countHistoryReports", params)[0][0] == 3
    assert [row[0] for row in run(conn, "findHistoryReports", params | dict(offset=1, limit=1))] == [last]
    assert [row[0] for row in run(conn, "findHistoryReports", params | dict(anchorId=first, issueKey=None))] == [first]


def test_full_report_is_default_and_missing_label_uses_representative_page(conn):
    full = cluster(conn, "replay:enwiki:Real root", "Old label", "2040-07-17T01:00:00Z")
    report(conn, full, full=True)
    latest = cluster(conn, "replay:enwiki:Real root", None, "2040-07-18T01:00:00Z")
    report(conn, latest)
    page = q(conn, "INSERT INTO wiki_page(wiki,title) VALUES ('enwiki','Real root') RETURNING id")[0][0]
    x(conn, "INSERT INTO cluster_member(cluster_id,page_id,is_seed) VALUES (%s,%s,true)", latest, page)
    rows = run(conn, "findHistoryGroups", group_params(pattern="%Real root%"))
    assert len(rows) == 1
    assert run(conn, "countHistoryGroups", group_params(pattern="%Real root%"))[0][0] == 1
    assert rows[0][0] == latest
    assert rows[0][1] == "Real root"
    assert rows[0][8] == full
