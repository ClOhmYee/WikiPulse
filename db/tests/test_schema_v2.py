"""펄스맵 스냅샷·문서 그래프 스키마 검증 — V2 (WP-75).

V1 위에 additive 로 얹은 것만 본다.
    - issue_cluster: issue_key·first_detected_at·hot·category
    - cluster_member: 시점별 고정 지표 + size_score 0~1 + completeness + window 순서
    - cluster_edge: 문서 쌍 간선, 종류별 근거 제약
    - cluster_snapshot: 완성 스냅샷 레지스트리(0개 포함)

conftest 픽스처(conn)가 V1·V2 를 순서대로 적재한다. rollback 픽스처가 테스트마다 되돌린다.
"""

from __future__ import annotations

import pytest

from conftest import q, x  # 공용 픽스처(conn·rollback)·헬퍼

pytest.importorskip("psycopg", reason="psycopg 미설치")
import psycopg  # noqa: E402


def _cluster(conn, **cols) -> int:
    """issue_cluster 한 행 만들고 id 반환. 기본값으로 최소 컬럼만 채운다."""
    base = {"snapshot_ts": "now()", "pulse_score": "1.0"}
    base.update({k: v for k, v in cols.items()})
    keys = ", ".join(base)
    vals = ", ".join(str(v) for v in base.values())
    x(conn, f"INSERT INTO issue_cluster ({keys}) VALUES ({vals})")
    return q(conn, "SELECT max(id) FROM issue_cluster")[0][0]


def _page(conn, title: str) -> int:
    x(conn, "INSERT INTO wiki_page (wiki, title) VALUES ('enwiki', %s)", title)
    return q(conn, "SELECT id FROM wiki_page WHERE title = %s", title)[0][0]


# ---------------------------------------------------------------- issue_cluster

def test_시점간_추적_메타_컬럼이_있다(conn):
    cid = _cluster(
        conn,
        issue_key="'iran-war-2026'",
        first_detected_at="'2026-08-28T00:00Z'",
        hot="true",
        category="'world'",
    )
    row = q(
        conn,
        "SELECT issue_key, first_detected_at, hot, category "
        "FROM issue_cluster WHERE id = %s",
        cid,
    )[0]
    assert row[0] == "iran-war-2026"
    assert row[2] is True
    assert row[3] == "world"


def test_카테고리는_10종만_받는다(conn):
    """뉴스형 카테고리가 오타로 조용히 새면 화면 필터가 깨진다."""
    with pytest.raises(psycopg.errors.CheckViolation):
        _cluster(conn, category="'finance'")  # 목록에 없음


def test_카테고리_기본값은_other다(conn):
    cid = _cluster(conn)
    assert q(conn, "SELECT category FROM issue_cluster WHERE id = %s", cid) == [("other",)]


def test_같은_issue_key로_시점별_행을_추적한다(conn):
    """id 는 스냅샷마다 다르지만 issue_key 로 시간축을 따라간다."""
    _cluster(conn, issue_key="'milton-2024'", snapshot_ts="'2024-10-09T12:00Z'", source="'replay'")
    _cluster(conn, issue_key="'milton-2024'", snapshot_ts="'2024-10-10T12:00Z'", source="'replay'")
    rows = q(
        conn,
        "SELECT snapshot_ts FROM issue_cluster WHERE issue_key = 'milton-2024' "
        "ORDER BY snapshot_ts",
    )
    assert len(rows) == 2


# ---------------------------------------------------------------- cluster_member 지표

def test_시점별_노드_지표를_고정해_저장한다(conn):
    """리플레이가 현재 spike 를 다시 읽지 않도록 멤버 행에 지표를 박는다."""
    cid = _cluster(conn)
    pid = _page(conn, "Strait of Hormuz")
    x(
        conn,
        "INSERT INTO cluster_member "
        "(cluster_id, page_id, weight, is_seed, edit_count, views, "
        " edit_baseline, view_baseline, spike_score, size_score, completeness, "
        " window_start, window_end) "
        "VALUES (%s, %s, 383, true, 47, 91000, 3.2, 390.0, 9.7, 0.82, 'complete', "
        "'2025-06-12T00:00Z', '2025-06-12T04:00Z')",
        cid,
        pid,
    )
    row = q(
        conn,
        "SELECT edit_count, size_score, completeness FROM cluster_member "
        "WHERE cluster_id = %s AND page_id = %s",
        cid,
        pid,
    )[0]
    assert row == (47, 0.82, "complete")


def test_size_score는_0에서_1이다(conn):
    cid = _cluster(conn)
    pid = _page(conn, "Overflow Doc")
    with pytest.raises(psycopg.errors.CheckViolation):
        x(
            conn,
            "INSERT INTO cluster_member (cluster_id, page_id, size_score) "
            "VALUES (%s, %s, 1.5)",
            cid,
            pid,
        )


def test_completeness는_정해진_값만_받는다(conn):
    cid = _cluster(conn)
    pid = _page(conn, "Completeness Doc")
    with pytest.raises(psycopg.errors.CheckViolation):
        x(
            conn,
            "INSERT INTO cluster_member (cluster_id, page_id, completeness) "
            "VALUES (%s, %s, 'partial')",  # 목록에 없음
            cid,
            pid,
        )


def test_집계구간은_시작이_종료보다_앞이다(conn):
    cid = _cluster(conn)
    pid = _page(conn, "Window Order Doc")
    with pytest.raises(psycopg.errors.CheckViolation):
        x(
            conn,
            "INSERT INTO cluster_member (cluster_id, page_id, window_start, window_end) "
            "VALUES (%s, %s, '2025-06-12T04:00Z', '2025-06-12T00:00Z')",
            cid,
            pid,
        )


def test_지표없이도_멤버는_들어간다(conn):
    """V1 방식(지표 컬럼 없음)으로 넣던 코드가 계속 돈다 — additive."""
    cid = _cluster(conn)
    pid = _page(conn, "Bare Member")
    x(conn, "INSERT INTO cluster_member (cluster_id, page_id) VALUES (%s, %s)", cid, pid)
    row = q(
        conn,
        "SELECT edit_count, completeness FROM cluster_member "
        "WHERE cluster_id = %s AND page_id = %s",
        cid,
        pid,
    )[0]
    assert row == (None, "complete")  # 지표는 NULL, completeness 는 기본값


# ---------------------------------------------------------------- cluster_edge

def test_clickstream_간선은_기준월을_요구한다(conn):
    cid = _cluster(conn)
    a = _page(conn, "2026 Iran war")
    b = _page(conn, "Sinking of IRIS Dena")
    x(
        conn,
        "INSERT INTO cluster_edge "
        "(cluster_id, source_page_id, target_page_id, kind, directed, weight, "
        " evidence_label, evidence_month) "
        "VALUES (%s, %s, %s, 'clickstream', true, 17499, 'Clickstream 2026-07', '2026-07')",
        cid,
        a,
        b,
    )
    row = q(conn, "SELECT kind, weight, evidence_month FROM cluster_edge")[0]
    assert row == ("clickstream", 17499.0, "2026-07")


def test_clickstream_간선에_월이_없으면_거부(conn):
    cid = _cluster(conn)
    a = _page(conn, "A doc")
    b = _page(conn, "B doc")
    with pytest.raises(psycopg.errors.CheckViolation):
        x(
            conn,
            "INSERT INTO cluster_edge "
            "(cluster_id, source_page_id, target_page_id, kind, directed, weight, evidence_label) "
            "VALUES (%s, %s, %s, 'clickstream', true, 10, '근거')",
            cid,
            a,
            b,
        )


def test_wikidata_간선은_관측시각을_요구한다(conn):
    cid = _cluster(conn)
    a = _page(conn, "Iran")
    b = _page(conn, "Persian Gulf")
    x(
        conn,
        "INSERT INTO cluster_edge "
        "(cluster_id, source_page_id, target_page_id, kind, directed, weight, "
        " evidence_label, evidence_observed_at) "
        "VALUES (%s, %s, %s, 'wikidata', false, 1.0, 'P361 부분', '2026-09-11T00:00Z')",
        cid,
        a,
        b,
    )
    assert q(conn, "SELECT kind, directed FROM cluster_edge")[0] == ("wikidata", False)


def test_자기_자신을_잇는_간선은_거부(conn):
    cid = _cluster(conn)
    a = _page(conn, "Self Doc")
    with pytest.raises(psycopg.errors.CheckViolation):
        x(
            conn,
            "INSERT INTO cluster_edge "
            "(cluster_id, source_page_id, target_page_id, kind, directed, weight, "
            " evidence_label, evidence_month) "
            "VALUES (%s, %s, %s, 'clickstream', true, 5, 'x', '2026-07')",
            cid,
            a,
            a,
        )


def test_같은_쌍_같은_종류_간선은_중복_불가(conn):
    cid = _cluster(conn)
    a = _page(conn, "Dup A")
    b = _page(conn, "Dup B")
    sql = (
        "INSERT INTO cluster_edge "
        "(cluster_id, source_page_id, target_page_id, kind, directed, weight, "
        " evidence_label, evidence_month) "
        "VALUES (%s, %s, %s, 'clickstream', true, 5, 'x', '2026-07')"
    )
    x(conn, sql, cid, a, b)
    with pytest.raises(psycopg.errors.UniqueViolation):
        x(conn, sql, cid, a, b)


def test_클러스터를_지우면_간선도_지워진다(conn):
    cid = _cluster(conn)
    a = _page(conn, "Cascade A")
    b = _page(conn, "Cascade B")
    x(
        conn,
        "INSERT INTO cluster_edge "
        "(cluster_id, source_page_id, target_page_id, kind, directed, weight, "
        " evidence_label, evidence_month) "
        "VALUES (%s, %s, %s, 'clickstream', true, 5, 'x', '2026-07')",
        cid,
        a,
        b,
    )
    x(conn, "DELETE FROM issue_cluster WHERE id = %s", cid)
    assert q(conn, "SELECT count(*) FROM cluster_edge")[0][0] == 0


# ---------------------------------------------------------------- cluster_snapshot

def test_완료된_빈_스냅샷을_남긴다(conn):
    """클러스터 0개여도 '완료됨'을 기록해야 미저장 시점과 구분된다(계약)."""
    x(
        conn,
        "INSERT INTO cluster_snapshot (snapshot_ts, source, cluster_count, score_version) "
        "VALUES ('2026-09-11T00:00Z', 'live', 0, 'v1')",
    )
    row = q(
        conn,
        "SELECT cluster_count, score_version, new_window_hours FROM cluster_snapshot",
    )[0]
    assert row == (0, "v1", 24.0)  # new_window_hours 기본 24


def test_스냅샷은_출처와_시각으로_유일하다(conn):
    sql = (
        "INSERT INTO cluster_snapshot (snapshot_ts, source, cluster_count, score_version) "
        "VALUES ('2026-09-11T00:00Z', 'live', 3, 'v1')"
    )
    x(conn, sql)
    # 제약 위반은 트랜잭션을 중단시킨다. 뒤 구문을 이어 쓰려면 세이브포인트가 필요하다.
    with conn.transaction(force_rollback=True):
        with pytest.raises(psycopg.errors.UniqueViolation):
            x(conn, sql)
    # 같은 시각이라도 출처가 다르면 별개 스냅샷이다.
    x(
        conn,
        "INSERT INTO cluster_snapshot (snapshot_ts, source, cluster_count, score_version) "
        "VALUES ('2026-09-11T00:00Z', 'replay', 3, 'v1')",
    )
    assert q(conn, "SELECT count(*) FROM cluster_snapshot")[0][0] == 2


def test_new_window_hours는_양수여야_한다(conn):
    with pytest.raises(psycopg.errors.CheckViolation):
        x(
            conn,
            "INSERT INTO cluster_snapshot "
            "(snapshot_ts, source, score_version, new_window_hours) "
            "VALUES (now(), 'live', 'v1', 0)",
        )
