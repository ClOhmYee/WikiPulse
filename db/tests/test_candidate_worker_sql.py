"""후보 생성 워커(WP-67)의 네이티브 SQL 을 진짜 PostgreSQL+pgvector 로 검증한다.

백엔드의 `CandidateRepository` 는 매핑 엔티티 없이 raw JDBC 로 이 SQL 을 돌린다.
`ddl-auto=validate` 는 매핑 엔티티만 검사하므로 이 쿼리들의 컬럼·연산자·멱등성은
컴파일·부팅에서 안 잡힌다 — 그 실 DB 검증이 여기(db pgserver 테스트) 몫이다.
아래 SQL 은 CandidateRepository 의 문장을 그대로 옮긴 것이다(플레이스홀더 표기만 psycopg).

특히 인수조건 4(verified=false 적재·재실행 갱신)의 두 핵심을 못 박는다:
    - ON CONFLICT upsert 가 LLM 검증 필드(verified·match_path·rationale·verified_at)를 보존
    - stale 삭제가 미확정(check_state<>DONE) 후보만 지우고 DONE 행은 남김

V5(WP-49) 이후: cluster_id 는 스냅샷마다 새로 생기므로(cluster/snapshot.py) 후보
재생성 INSERT 는 issue_key·ticker 로 과거 DONE 판정을 찾아 새 cluster_id 행에 그대로
들고 온다 — 진행 중인 이슈가 재감지될 때마다 LLM 을 다시 안 부르기 위해서다.
"""

from __future__ import annotations

import pytest

from conftest import q, x

psycopg = pytest.importorskip("psycopg", reason="psycopg 미설치 — 이 파일은 건너뛴다")

DIM = 1536


def _vec(index: int, dim: int = DIM) -> str:
    """지정 인덱스만 1 인 dim 차원 단위벡터의 pgvector 리터럴."""
    v = ["0"] * dim
    v[index] = "1"
    return "[" + ",".join(v) + "]"


def _new_cluster(conn, **cols) -> int:
    base = {"snapshot_ts": "now()", "pulse_score": "1.0"}
    base.update(cols)
    keys = ", ".join(base)
    placeholders = ", ".join(["%s"] * len(base))
    rows = q(
        conn,
        f"INSERT INTO issue_cluster ({keys}) VALUES ({placeholders}) RETURNING id",
        *base.values(),
    )
    return rows[0][0]


# CandidateRepository.replaceCandidates() 의 INSERT 문 그대로(자리표시자만 :name -> %s).
# 파라미터 순서: cid, ticker, tier, similarity, gdelt_lift, issue_key(SELECT절),
#              issue_key(WHERE절), ticker(WHERE절) — issue_key·ticker 는 두 번씩 쓰인다.
_UPSERT_CANDIDATE_SQL = """
    INSERT INTO cluster_stock
        (cluster_id, ticker, tier, similarity, gdelt_lift, verified,
         issue_key, prompt_version, check_state, attempt_count,
         match_path, confidence, rationale, verified_at)
    SELECT %s, %s, %s, %s, %s,
           COALESCE(prior.verified, false),
           %s,
           prior.prompt_version,
           COALESCE(prior.check_state, 'PENDING'),
           COALESCE(prior.attempt_count, 0),
           prior.match_path, prior.confidence, prior.rationale, prior.verified_at
      FROM (SELECT 1) AS dual
      LEFT JOIN (
          SELECT verified, prompt_version, check_state, attempt_count,
                 match_path, confidence, rationale, verified_at
            FROM cluster_stock
           WHERE issue_key = CAST(%s AS text)
             AND ticker = %s
             AND check_state = 'DONE'
           ORDER BY verified_at DESC NULLS LAST
           LIMIT 1
      ) AS prior ON true
    ON CONFLICT (cluster_id, ticker) DO UPDATE
       SET tier = EXCLUDED.tier,
           similarity = EXCLUDED.similarity,
           gdelt_lift = EXCLUDED.gdelt_lift
"""

def _delete_stale(conn, cid, keep: tuple[str, ...]) -> None:
    """CandidateRepository.replaceCandidates() 의 stale 삭제 문 그대로.

    Spring 의 NamedParameterJdbcTemplate 은 List 값을 :keep 자리에 넣으면 IN (?,?,...)로
    자동 전개한다. psycopg3 는 튜플 하나를 IN %s 자리에 그대로 못 넣어(오탐 아님 —
    파라미터화 방식 차이) 여기서 개수만큼 자리표시자를 직접 만든다.
    """
    placeholders = ", ".join(["%s"] * len(keep))
    x(
        conn,
        f"DELETE FROM cluster_stock WHERE cluster_id = %s AND check_state <> 'DONE' "
        f"AND ticker NOT IN ({placeholders})",
        cid, *keep,
    )


def _upsert_candidate(conn, cid, ticker, tier, similarity, gdelt_lift, issue_key):
    x(conn, _UPSERT_CANDIDATE_SQL, cid, ticker, tier, similarity, gdelt_lift,
      issue_key, issue_key, ticker)


# ---------------------------------------------------------------- 인수조건 4: 멱등 upsert

def test_재실행_upsert가_LLM_검증필드를_보존한다(conn):
    cid = _new_cluster(conn, issue_key="'nee-hurricane'")
    x(conn, "INSERT INTO stock (ticker, name, exchange) VALUES ('NEE', 'NextEra', 'NYSE')")

    # 1) 후보 최초 적재 (워커: verified=false, check_state=PENDING)
    _upsert_candidate(conn, cid, "NEE", "EMBEDDING_ONLY", 0.20, None, "nee-hurricane")
    # 2) LLM 검증 단계가 확정 (별도 이슈 -68 이 채우는 필드)
    x(
        conn,
        "UPDATE cluster_stock SET verified=true, match_path='DIRECT_MENTION', "
        "check_state='DONE', rationale='허리케인 직접 노출', verified_at=now() "
        "WHERE cluster_id=%s AND ticker='NEE'",
        cid,
    )
    # 3) 워커 재실행(같은 cluster_id) — upsert 문 그대로, tier·점수만 새로 계산됐다고 가정
    _upsert_candidate(conn, cid, "NEE", "BOTH", 0.31, 10.5, "nee-hurricane")

    row = q(
        conn,
        "SELECT tier, similarity, gdelt_lift, verified, match_path, rationale, "
        "       check_state, verified_at IS NOT NULL "
        "FROM cluster_stock WHERE cluster_id=%s AND ticker='NEE'",
        cid,
    )[0]
    tier, sim, lift, verified, match_path, rationale, check_state, has_verified_at = row
    # 신호는 갱신
    assert tier == "BOTH"
    assert sim == 0.31
    assert lift == 10.5
    # 검증 필드는 보존
    assert verified is True
    assert match_path == "DIRECT_MENTION"
    assert rationale == "허리케인 직접 노출"
    assert check_state == "DONE"
    assert has_verified_at is True


def test_stale_삭제는_미확정만_지우고_DONE_행은_남긴다(conn):
    cid = _new_cluster(conn)
    for t in ("NEE", "GNRC", "DUK"):
        x(conn, "INSERT INTO stock (ticker, name, exchange) VALUES (%s, %s, 'NYSE')", t, t)
    # NEE=DONE(탈락이어도 확정), GNRC·DUK=아직 PENDING
    x(
        conn,
        "INSERT INTO cluster_stock (cluster_id, ticker, tier, verified, check_state) VALUES "
        "(%s,'NEE','BOTH',false,'DONE'), (%s,'GNRC','GDELT_ONLY',false,'PENDING'), "
        "(%s,'DUK','GDELT_ONLY',false,'PENDING')",
        cid, cid, cid,
    )
    # 이번 재실행 후보군(keep) = {NEE, GNRC}.
    _delete_stale(conn, cid, ("NEE", "GNRC"))
    left = {r[0] for r in q(conn, "SELECT ticker FROM cluster_stock WHERE cluster_id=%s", cid)}
    # DUK(미확정·keep 밖)만 삭제. DONE 인 NEE 는 verified=false(탈락)여도, keep 밖이어도 남는다.
    assert left == {"NEE", "GNRC"}


# ---------------------------------------------------------------- WP-49: 재사용

def test_같은_이슈의_새_스냅샷_cluster_id가_이전_DONE_판정을_들고온다(conn):
    """핵심 계약 — cluster_id 가 스냅샷마다 바뀌어도 LLM 을 다시 안 부른다."""
    x(conn, "INSERT INTO stock (ticker, name, exchange) VALUES ('CRWD', 'CrowdStrike', 'NASDAQ')")
    c1 = _new_cluster(conn, issue_key="'crowdstrike-2024'", snapshot_ts="'2024-07-19T00:00Z'")
    _upsert_candidate(conn, c1, "CRWD", "BOTH", 0.5, 9.0, "crowdstrike-2024")
    x(
        conn,
        "UPDATE cluster_stock SET check_state='DONE', verified=true, match_path='DIRECT_MENTION', "
        "prompt_version='v1', rationale='결함 업데이트 배포 당사자', verified_at='2024-07-19T01:00Z' "
        "WHERE cluster_id=%s AND ticker='CRWD'",
        c1,
    )

    # 다음 폴 주기 — 새 스냅샷, 새 cluster_id, 같은 issue_key. 워커가 후보를 다시 만든다.
    c2 = _new_cluster(conn, issue_key="'crowdstrike-2024'", snapshot_ts="'2024-07-19T00:05Z'")
    _upsert_candidate(conn, c2, "CRWD", "BOTH", 0.55, 9.2, "crowdstrike-2024")

    row = q(
        conn,
        "SELECT verified, check_state, match_path, prompt_version, similarity FROM cluster_stock "
        "WHERE cluster_id=%s AND ticker='CRWD'",
        c2,
    )[0]
    assert row == (True, "DONE", "DIRECT_MENTION", "v1", 0.55)  # 판정은 이월, similarity 는 재계산값


def test_issue_key가_없으면_재사용_안_하고_PENDING으로_시작한다(conn):
    """V1 이전·issue_key 미배선 클러스터. NULL = NULL 은 매치되지 않아 그냥 새로 시작한다."""
    x(conn, "INSERT INTO stock (ticker, name, exchange) VALUES ('NOKEY', 'No Key Co', 'NYSE')")
    cid = _new_cluster(conn)  # issue_key 없음
    _upsert_candidate(conn, cid, "NOKEY", "BOTH", 0.5, None, None)

    row = q(
        conn,
        "SELECT verified, check_state FROM cluster_stock WHERE cluster_id=%s AND ticker='NOKEY'",
        cid,
    )[0]
    assert row == (False, "PENDING")


# ---------------------------------------------------------------- 후보 조회 SQL

def test_embedding_topk_는_코사인_유사도순이고_null_임베딩은_제외(conn):
    x(conn, "INSERT INTO stock (ticker,name,exchange,embedding) VALUES "
            "('AAA','A','NYSE', CAST(%s AS vector))", _vec(0))
    x(conn, "INSERT INTO stock (ticker,name,exchange,embedding) VALUES "
            "('BBB','B','NYSE', CAST(%s AS vector))", _vec(1))
    x(conn, "INSERT INTO stock (ticker,name,exchange) VALUES ('CCC','C','NYSE')")  # embedding NULL

    rows = q(
        conn,
        "SELECT s.ticker, 1 - (s.embedding <=> CAST(%s AS vector)) AS similarity "
        "FROM stock s WHERE s.embedding IS NOT NULL "
        "ORDER BY s.embedding <=> CAST(%s AS vector) LIMIT %s",
        _vec(0), _vec(0), 20,
    )
    tickers = [r[0] for r in rows]
    assert tickers == ["AAA", "BBB"]      # 쿼리 벡터와 같은 방향인 AAA 가 먼저, NULL 인 CCC 는 빠짐
    assert rows[0][1] == pytest.approx(1.0)   # 코사인 유사도 = 1
    assert rows[1][1] == pytest.approx(0.0)


def test_gdelt_topk_는_티커별_max_lift_상위(conn):
    cid = _new_cluster(conn)
    for t in ("FPL", "DUK"):
        x(conn, "INSERT INTO stock (ticker,name,exchange) VALUES (%s,%s,'NYSE')", t, t)
    # 같은 티커에 기관명 2건(별칭) → MAX 로 접힌다. ticker NULL 은 제외.
    x(conn, "INSERT INTO cluster_org_mention "
            "(cluster_id, org_name, ticker, issue_count, corpus_count, lift) VALUES "
            "(%s,'Florida Power and Light','FPL',5,10,10.5),"
            "(%s,'FPL Group','FPL',3,10,8.0),"
            "(%s,'Duke Energy','DUK',4,10,8.4),"
            "(%s,'Reuters',NULL,9,10,2.0)", cid, cid, cid, cid)

    rows = q(
        conn,
        "SELECT ticker, MAX(lift) AS lift FROM cluster_org_mention "
        "WHERE cluster_id=%s AND ticker IS NOT NULL "
        "GROUP BY ticker ORDER BY MAX(lift) DESC LIMIT %s",
        cid, 10,
    )
    assert rows == [("FPL", 10.5), ("DUK", 8.4)]   # 언론사(NULL) 제외, FPL 은 max(10.5,8.0)


def test_member_정렬은_spike_score_desc_nulls_last(conn):
    cid = _new_cluster(conn)
    ids = {}
    for title in ("High", "Low", "NoScore"):
        r = q(conn, "INSERT INTO wiki_page (wiki, title) VALUES ('enwiki', %s) RETURNING id", title)
        ids[title] = r[0][0]
    x(conn, "INSERT INTO cluster_member (cluster_id, page_id, weight, spike_score) VALUES "
            "(%s,%s,1.0,9.0)", cid, ids["High"])
    x(conn, "INSERT INTO cluster_member (cluster_id, page_id, weight, spike_score) VALUES "
            "(%s,%s,1.0,2.0)", cid, ids["Low"])
    x(conn, "INSERT INTO cluster_member (cluster_id, page_id, weight, spike_score) VALUES "
            "(%s,%s,5.0,NULL)", cid, ids["NoScore"])

    rows = q(
        conn,
        "SELECT wp.title FROM cluster_member cm JOIN wiki_page wp ON wp.id = cm.page_id "
        "WHERE cm.cluster_id=%s ORDER BY cm.spike_score DESC NULLS LAST, cm.weight DESC",
        cid,
    )
    assert [r[0] for r in rows] == ["High", "Low", "NoScore"]


def test_tier_CHECK_는_정의된_세_값만_받는다(conn):
    cid = _new_cluster(conn)
    x(conn, "INSERT INTO stock (ticker,name,exchange) VALUES ('ZZZ','Z','NYSE')")
    with pytest.raises(psycopg.errors.CheckViolation):
        x(conn, "INSERT INTO cluster_stock (cluster_id,ticker,tier,verified) "
                "VALUES (%s,'ZZZ','SOMETHING_ELSE',false)", cid)
