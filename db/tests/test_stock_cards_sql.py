"""종목 목록 카드 SQL 을 진짜 PostgreSQL 로 검증한다 (WP-189).

`StockRepository.findCards` 는 상관 서브쿼리 두 개(issueCount·lastClose)를 쓰는 native
query 라 `ddl-auto=validate` 로도 백엔드 단위 테스트(@WebMvcTest, service mock)로도
안 잡힌다 — 실 DB 검증이 여기 몫이다(`test_candidate_scope_sql.py` 와 같은 관습).
아래 SQL 은 그 문장을 그대로 옮겼고, 이름 파라미터(:q 등)만 psycopg 스타일 %(...)s 로
바꾸면서 raw 드라이버가 NULL 파라미터의 타입을 못 정하지 않도록 캐스트를 붙였다
(candidate 테스트가 `%(source)s::text` 로 한 것과 같은 이유).

못 박는 것:
    - lastClose 는 그 티커의 **가장 최근 거래일** 종가다(trade_date DESC, 적재 순서 무관)
    - 일봉이 없는 종목은 lastClose 가 NULL — FE 가 "미제공"을 찍는 근거다
    - issueCount 서브쿼리와 독립적으로 동작한다(가격만 있고 이슈 0, 그 반대도)
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from conftest import q, x

psycopg = pytest.importorskip("psycopg", reason="psycopg 미설치 — 이 파일은 건너뛴다")

# StockRepository.findCards 의 SQL. 이름 파라미터를 %(...)s 로 바꾸고 raw 드라이버용
# 캐스트만 더했다.
_SELECT = """
SELECT s.ticker AS ticker, s.name AS name, s.exchange AS exchange,
       s.sector AS sector,
       (SELECT count(DISTINCT cs.cluster_id) FROM cluster_stock cs
         JOIN issue_cluster c ON c.id = cs.cluster_id
        WHERE cs.ticker = s.ticker AND cs.verified AND c.status <> 'DISCARDED') AS issueCount,
       (SELECT sp.close FROM stock_price sp
         WHERE sp.ticker = s.ticker
         ORDER BY sp.trade_date DESC LIMIT 1) AS lastClose
FROM stock s
WHERE (%(q)s::text IS NULL OR lower(s.name) LIKE %(q)s::text OR lower(s.ticker) LIKE %(q)s::text)
  AND (%(sector)s::text IS NULL OR s.sector = %(sector)s::text)
  AND (%(exchange)s::text IS NULL OR s.exchange = %(exchange)s::text)
  AND (%(hasIssues)s::boolean = false OR EXISTS (
         SELECT 1 FROM cluster_stock cs2 JOIN issue_cluster c2 ON c2.id = cs2.cluster_id
          WHERE cs2.ticker = s.ticker AND cs2.verified AND c2.status <> 'DISCARDED'))
ORDER BY s.ticker
OFFSET %(offset)s::int LIMIT %(limit)s::int
"""


def _cards(conn, *, q_=None, sector=None, exchange=None, has_issues=False,
           offset=0, limit=50):
    with conn.cursor() as cur:
        cur.execute(_SELECT, {
            "q": q_, "sector": sector, "exchange": exchange,
            "hasIssues": has_issues, "offset": offset, "limit": limit,
        })
        # {ticker: {"issueCount": int, "lastClose": Decimal|None}}
        return {
            row[0]: {"issueCount": row[4], "lastClose": row[5]}
            for row in cur.fetchall()
        }


def _stock(conn, ticker: str, *, sector=None, exchange: str = "NASDAQ") -> None:
    x(conn, "INSERT INTO stock (ticker, name, exchange, sector) "
            "VALUES (%s, %s, %s, %s) ON CONFLICT (ticker) DO NOTHING",
      ticker, ticker + " Inc", exchange, sector)


def _price(conn, ticker: str, trade_date: str, close: str) -> None:
    x(conn, "INSERT INTO stock_price (ticker, trade_date, close) VALUES (%s, %s, %s)",
      ticker, trade_date, close)


def _verified_match(conn, ticker: str) -> None:
    rows = q(conn, "INSERT INTO issue_cluster (snapshot_ts, pulse_score, status) "
                   "VALUES ('2026-09-01T00:00:00+00:00', 9.0, 'CONFIRMED') RETURNING id")
    cluster_id = rows[0][0]
    x(conn, "INSERT INTO cluster_stock (cluster_id, ticker, tier, verified) "
            "VALUES (%s, %s, 'BOTH', true)", cluster_id, ticker)


def test_최신_거래일_종가를_돌려준다(conn):
    _stock(conn, "BA")
    # 일부러 날짜 역순으로 적재해 ORDER BY trade_date DESC 가 정말 최신을 고르는지 본다.
    _price(conn, "BA", "2026-01-05", "201.1500")
    _price(conn, "BA", "2026-01-03", "195.0000")
    _price(conn, "BA", "2026-01-04", "198.2500")

    cards = _cards(conn)

    # NUMERIC(14,4) → Decimal, 정확 비교(부동소수 오차 없음).
    assert cards["BA"]["lastClose"] == Decimal("201.1500")


def test_가격이_없으면_null(conn):
    _stock(conn, "ZZZZ")

    cards = _cards(conn)

    assert cards["ZZZZ"]["lastClose"] is None


def test_lastClose_와_issueCount_는_서로_독립이다(conn):
    # 가격만 있고 이슈 0
    _stock(conn, "AAA")
    _price(conn, "AAA", "2026-02-01", "10.0000")
    # 이슈만 있고 가격 0
    _stock(conn, "BBB")
    _verified_match(conn, "BBB")

    cards = _cards(conn)

    assert cards["AAA"]["lastClose"] == Decimal("10.0000")
    assert cards["AAA"]["issueCount"] == 0
    assert cards["BBB"]["lastClose"] is None
    assert cards["BBB"]["issueCount"] == 1


def test_hasIssues_필터는_lastClose_없이도_동작한다(conn):
    _stock(conn, "AAA")  # 이슈 없음
    _stock(conn, "BBB")
    _verified_match(conn, "BBB")

    cards = _cards(conn, has_issues=True)

    assert set(cards) == {"BBB"}
