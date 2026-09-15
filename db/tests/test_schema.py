"""데이터 모델 v1 검증 — 진짜 PostgreSQL 을 띄워서 돌린다.

Docker 없이 돈다. pgserver 가 PostgreSQL 바이너리를 번들로 들고 있고
pgvector 확장도 들어 있다.

여기서 확인하려는 것
    1. DDL 이 실제로 실행된다 (문법·타입·제약)
    2. 명세 §3.2 의 파이프라인 흐름을 이 스키마로 실제로 담을 수 있다
    3. 실수로 깨지면 안 되는 제약이 진짜로 막는다

느리다(서버 기동 ~10초). 모듈 스코프 픽스처로 한 번만 띄운다.
"""

from __future__ import annotations

import pytest

# 공용 픽스처(conn·rollback)와 헬퍼(q·x)는 conftest.py 가 제공한다.
from conftest import q, x

psycopg = pytest.importorskip("psycopg", reason="psycopg 미설치 — 이 파일은 건너뛴다")


# ---------------------------------------------------------------- 구조

def test_pgvector_확장이_있다(conn):
    rows = q(conn, "SELECT extname FROM pg_extension WHERE extname = 'vector'")
    assert rows == [("vector",)]


def test_명세에_적힌_테이블이_모두_있다(conn):
    rows = q(
        conn,
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY 1",
    )
    actual = {r[0] for r in rows}
    expected = {
        # 위키 신호
        "wiki_page", "page_edit_window", "page_view_hourly", "page_baseline", "spike",
        # 이슈
        "issue_cluster", "cluster_member", "issue_report",
        # 펄스맵 스냅샷·그래프 (V2)
        "cluster_edge", "cluster_snapshot",
        # 종목
        "stock", "stock_price", "cluster_stock", "cluster_org_mention",
        # 사용자
        "member", "watchlist", "notification", "comment_thread", "thread_comment",
    }
    assert expected <= actual, f"빠진 테이블: {expected - actual}"


# ---------------------------------------------------------------- 제약

def test_같은_문서를_두_번_넣을_수_없다(conn):
    """EventStreams 에 page_id 가 없어 (wiki, title) 이 자연키다."""
    x(conn, "INSERT INTO wiki_page (wiki, title) VALUES ('enwiki', 'Hurricane Milton')")
    with pytest.raises(psycopg.errors.UniqueViolation):
        x(conn, "INSERT INTO wiki_page (wiki, title) VALUES ('enwiki', 'Hurricane Milton')")


def test_다른_위키의_같은_제목은_다른_문서다(conn):
    x(conn, "INSERT INTO wiki_page (wiki, title) VALUES ('enwiki', 'Iran'), ('kowiki', 'Iran')")
    rows = q(conn, "SELECT count(*) FROM wiki_page WHERE title = 'Iran'")
    assert rows[0][0] == 2


def test_이슈_상태는_정해진_값만_받는다(conn):
    """피드 3단계 노출이 오타로 조용히 깨지는 걸 막는다."""
    with pytest.raises(psycopg.errors.CheckViolation):
        x(
            conn,
            "INSERT INTO issue_cluster (snapshot_ts, pulse_score, status) "
            "VALUES (now(), 1.0, 'CONFIRMD')",  # 오타
        )


def test_매칭_등급은_정해진_값만_받는다(conn):
    """tier 는 3등급 우선순위의 근거라 오타가 들어가면 정렬이 깨진다."""
    x(conn, "INSERT INTO stock (ticker, name, exchange) VALUES ('TST', 'Test', 'NYSE')")
    x(conn, "INSERT INTO issue_cluster (snapshot_ts, pulse_score) VALUES (now(), 1.0)")
    cluster_id = q(conn, "SELECT max(id) FROM issue_cluster")[0][0]

    with pytest.raises(psycopg.errors.CheckViolation):
        x(
            conn,
            "INSERT INTO cluster_stock (cluster_id, ticker, tier) VALUES (%s, 'TST', 'GDELT')",
            cluster_id,
        )


def test_근거_경로도_정해진_값만_받는다(conn):
    x(conn, "INSERT INTO stock (ticker, name, exchange) VALUES ('TS2', 'Test2', 'NYSE')")
    x(conn, "INSERT INTO issue_cluster (snapshot_ts, pulse_score) VALUES (now(), 1.0)")
    cluster_id = q(conn, "SELECT max(id) FROM issue_cluster")[0][0]

    # 제약 위반은 트랜잭션을 중단시킨다. 뒤 구문을 이어 쓰려면 세이브포인트가 필요하다.
    with conn.transaction(force_rollback=True):
        with pytest.raises(psycopg.errors.CheckViolation):
            x(
                conn,
                "INSERT INTO cluster_stock (cluster_id, ticker, tier, match_path) "
                "VALUES (%s, 'TS2', 'BOTH', 'VIBES')",
                cluster_id,
            )

    # NULL 은 허용된다 — 아직 LLM 검증 전이라는 뜻이다.
    x(
        conn,
        "INSERT INTO cluster_stock (cluster_id, ticker, tier) VALUES (%s, 'TS2', 'BOTH')",
        cluster_id,
    )
    assert q(conn, "SELECT match_path FROM cluster_stock WHERE ticker = 'TS2'") == [(None,)]


def test_기준선_슬롯은_0에서_3이다(conn):
    x(conn, "INSERT INTO wiki_page (wiki, title) VALUES ('enwiki', 'Baseline Test')")
    page_id = q(conn, "SELECT id FROM wiki_page WHERE title = 'Baseline Test'")[0][0]
    with pytest.raises(psycopg.errors.CheckViolation):
        x(
            conn,
            "INSERT INTO page_baseline (page_id, slot_index, edit_ewma, sample_days) "
            "VALUES (%s, 4, 1.0, 28)",
            page_id,
        )


def test_클러스터를_지우면_멤버도_지워진다(conn):
    x(conn, "INSERT INTO wiki_page (wiki, title) VALUES ('enwiki', 'Cascade Test')")
    page_id = q(conn, "SELECT id FROM wiki_page WHERE title = 'Cascade Test'")[0][0]
    x(conn, "INSERT INTO issue_cluster (snapshot_ts, pulse_score) VALUES (now(), 5.0)")
    cluster_id = q(conn, "SELECT max(id) FROM issue_cluster")[0][0]
    x(
        conn,
        "INSERT INTO cluster_member (cluster_id, page_id) VALUES (%s, %s)",
        cluster_id,
        page_id,
    )

    x(conn, "DELETE FROM issue_cluster WHERE id = %s", cluster_id)
    assert q(conn, "SELECT count(*) FROM cluster_member")[0][0] == 0


# ---------------------------------------------------------------- 흐름

def test_파이프라인_한_바퀴가_스키마에_담긴다(conn):
    """명세 §3.2 의 흐름을 실제 INSERT 로 따라가 본다.

    편집 급증 → 조회수 확인 → 클러스터 → 종목 매칭 → 피드 조회.
    중간에 컬럼이 모자라면 여기서 걸린다.
    """
    # 1~2. 문서와 편집 윈도우
    x(conn, "INSERT INTO wiki_page (wiki, title) VALUES ('enwiki', 'Hurricane Milton')")
    page_id = q(conn, "SELECT id FROM wiki_page WHERE title = 'Hurricane Milton'")[0][0]
    x(
        conn,
        "INSERT INTO page_edit_window "
        "(page_id, window_start, window_end, edit_count, editor_count, byte_delta_sum) "
        "VALUES (%s, '2024-10-10T12:00Z', '2024-10-10T13:00Z', 47, 12, 8200)",
        page_id,
    )

    # 3. 조회수 2차 판정 + 급증 확정
    x(
        conn,
        "INSERT INTO page_view_hourly (page_id, ts_hour, views) "
        "VALUES (%s, '2024-10-10T12:00Z', 91000)",
        page_id,
    )
    x(
        conn,
        "INSERT INTO spike "
        "(page_id, detected_at, window_start, edit_count, edit_z, view_ratio, spike_score) "
        "VALUES (%s, now(), '2024-10-10T12:00Z', 47, 8.4, 12.1, 9.7)",
        page_id,
    )

    # 4. 클러스터
    x(
        conn,
        "INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, status) "
        "VALUES ('2024-10-10T13:00Z', 'Hurricane Milton 상륙', 9.7, 'CONFIRMED')",
    )
    cluster_id = q(conn, "SELECT max(id) FROM issue_cluster")[0][0]
    x(
        conn,
        "INSERT INTO cluster_member (cluster_id, page_id, weight, is_seed) "
        "VALUES (%s, %s, 1.0, true)",
        cluster_id,
        page_id,
    )

    # 5. 종목 매칭 — GDELT lift 로 잡힌 정답 (명세 §11 실측)
    x(
        conn,
        "INSERT INTO stock (ticker, name, exchange, sector) VALUES "
        "('NEE', 'NextEra Energy', 'NYSE', 'Utilities'), "
        "('GNRC', 'Generac Holdings', 'NYSE', 'Industrials'), "
        "('NVDA', 'NVIDIA', 'NASDAQ', 'Technology')",
    )
    x(
        conn,
        "INSERT INTO cluster_stock "
        "(cluster_id, ticker, tier, gdelt_lift, verified, match_path, rationale) VALUES "
        "(%s, 'NEE', 'BOTH', 10.5, true, 'REGION', '플로리다 전력망 운영사'), "
        "(%s, 'GNRC', 'GDELT_ONLY', 9.3, true, 'PRODUCT_INDUSTRY', '비상 발전기 수요')",
        cluster_id,
        cluster_id,
    )

    # 6. 피드 조회 — 화면이 실제로 던질 질의
    rows = q(
        conn,
        """
        SELECT c.label, cs.ticker, s.name, cs.tier, cs.gdelt_lift, cs.rationale
        FROM issue_cluster c
        JOIN cluster_stock cs ON cs.cluster_id = c.id AND cs.verified
        JOIN stock s ON s.ticker = cs.ticker
        WHERE c.snapshot_ts = (SELECT max(snapshot_ts) FROM issue_cluster)
          AND c.status = 'CONFIRMED'
        ORDER BY cs.gdelt_lift DESC
        """,
    )
    assert [r[1] for r in rows] == ["NEE", "GNRC"]
    assert rows[0][0] == "Hurricane Milton 상륙"
    assert "NVDA" not in [r[1] for r in rows], "검증 안 된 종목이 피드에 나오면 안 된다"


def test_리플레이는_같은_클러스터의_과거_시점을_읽는다(conn):
    """버블맵 시간 슬라이더가 이 질의를 쓴다."""
    x(
        conn,
        "INSERT INTO issue_cluster (snapshot_ts, label, pulse_score, source) VALUES "
        "('2024-10-09T12:00Z', 'Milton 접근', 3.1, 'replay'), "
        "('2024-10-10T12:00Z', 'Milton 상륙', 9.7, 'replay'), "
        "('2024-10-11T12:00Z', 'Milton 통과', 5.2, 'replay')",
    )
    rows = q(
        conn,
        "SELECT label, pulse_score FROM issue_cluster "
        "WHERE snapshot_ts = %s AND source = 'replay'",
        "2024-10-10T12:00Z",
    )
    assert rows == [("Milton 상륙", 9.7)]


def vec(*head: float) -> str:
    """앞자리만 주고 나머지를 0으로 채운 1536차원 리터럴."""
    values = list(head) + [0.0] * (1536 - len(head))
    return "[" + ",".join(str(v) for v in values) + "]"


def test_벡터_유사도_검색이_된다(conn):
    """pgvector 코사인 Top-K. 인덱스가 vector_cosine_ops 라 <=> 를 써야 한다."""
    x(
        conn,
        "INSERT INTO stock (ticker, name, exchange, embedding) VALUES "
        "('AAA', 'Alpha', 'NYSE', %s), "
        "('BBB', 'Beta',  'NYSE', %s), "
        "('CCC', 'Gamma', 'NYSE', %s)",
        vec(1, 0, 0),
        vec(0.9, 0.1, 0),
        vec(0, 1, 0),
    )
    rows = q(
        conn,
        "SELECT ticker FROM stock WHERE embedding IS NOT NULL "
        "ORDER BY embedding <=> %s LIMIT 2",
        vec(1, 0, 0),
    )
    assert [r[0] for r in rows] == ["AAA", "BBB"]


def test_차원이_다른_벡터는_거부된다(conn):
    """임베딩 모델을 바꾸면 여기서 걸린다. 조용히 들어가면 검색이 망가진다."""
    with pytest.raises(psycopg.errors.DataException):
        x(
            conn,
            "INSERT INTO stock (ticker, name, exchange, embedding) "
            "VALUES ('DIM', 'Wrong', 'NYSE', %s)",
            "[1,0,0]",
        )


def test_종목이_사라져도_토론과_알림은_남는다(conn):
    """탈퇴·상장폐지가 사용자 데이터를 지우면 안 된다."""
    x(conn, "INSERT INTO stock (ticker, name, exchange) VALUES ('ZZZ', 'Zeta', 'NYSE')")
    x(
        conn,
        "INSERT INTO member (email, display_name) VALUES ('a@example.com', '팀원 2')",
    )
    member_id = q(conn, "SELECT id FROM member WHERE email = 'a@example.com'")[0][0]
    x(
        conn,
        "INSERT INTO notification (member_id, ticker, body) VALUES (%s, 'ZZZ', '새 이슈')",
        member_id,
    )

    x(conn, "DELETE FROM stock WHERE ticker = 'ZZZ'")
    rows = q(conn, "SELECT ticker, body FROM notification WHERE member_id = %s", member_id)
    assert rows == [(None, "새 이슈")], "종목이 지워져도 알림 본문은 남아야 한다"
