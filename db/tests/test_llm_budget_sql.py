"""일일 LLM 예산 SQL 을 진짜 PostgreSQL 로 검증한다 (WP-191).

`LlmBudget.consumeOrNull` 은 `ON CONFLICT ... DO UPDATE ... WHERE` + `RETURNING` 이라
백엔드 단위 테스트로는 동작이 안 보인다 — 조건이 거짓일 때 **아무 행도 안 돌아오는**
것이 이 설계의 전부다.

🔴 **증가와 상한 검사가 한 문장이어야 한다.** 읽고 나서 쓰면 폴러 둘이 같은 순간에
통과한다. 아래 테스트가 그 한 문장의 계약을 못 박는다.

못 박는 것:
    - 상한 미만이면 증가하고 증가 후 값을 돌려준다
    - 상한에 닿으면 **행이 안 돌아온다**(= 초과 신호)이고 값도 안 늘어난다
    - 요약·검증은 별개 예산이다
    - UTC 날짜가 바뀌면 새 행이라 예산이 리셋된다
"""

from __future__ import annotations

import pytest

from conftest import q, x

psycopg = pytest.importorskip("psycopg", reason="psycopg 미설치 — 이 파일은 건너뛴다")

SUMMARY = "summary"
VERIFICATION = "verification"

# LlmBudget.consumeOrNull 의 SQL. 이름 파라미터만 %s 로 바꿨다.
_CONSUME = """
INSERT INTO llm_daily_usage (usage_date, kind, calls)
VALUES ((now() AT TIME ZONE 'UTC')::date, %(kind)s, 1)
ON CONFLICT (usage_date, kind) DO UPDATE
   SET calls = llm_daily_usage.calls + 1
 WHERE llm_daily_usage.calls < %(limit)s
RETURNING calls
"""


def _consume(conn, kind: str = SUMMARY, limit: int = 3):
    """증가 후 값. 상한이면 None."""
    with conn.cursor() as cur:
        cur.execute(_CONSUME, {"kind": kind, "limit": limit})
        row = cur.fetchone()
        return None if row is None else row[0]


def _used(conn, kind: str = SUMMARY) -> int:
    rows = q(conn,
             "SELECT calls FROM llm_daily_usage "
             "WHERE usage_date = (now() AT TIME ZONE 'UTC')::date AND kind = %s", kind)
    return rows[0][0] if rows else 0


def test_상한_미만이면_증가하고_증가후_값을_돌려준다(conn):
    assert _consume(conn, limit=3) == 1
    assert _consume(conn, limit=3) == 2
    assert _consume(conn, limit=3) == 3
    assert _used(conn) == 3


def test_상한에_닿으면_행이_안_돌아오고_값도_안_는다(conn):
    """🔴 이게 초과 신호다. 예외도 에러도 아니고 '빈 결과' 다."""
    for _ in range(3):
        _consume(conn, limit=3)

    assert _consume(conn, limit=3) is None
    assert _consume(conn, limit=3) is None
    assert _used(conn) == 3  # 초과 시도가 값을 밀어올리지 않는다


def test_요약과_검증은_별개_예산이다(conn):
    """한 통으로 묶으면 검증이 요약을 굶는다 — 이슈당 검증은 후보 수만큼 호출된다."""
    for _ in range(3):
        _consume(conn, VERIFICATION, limit=3)

    assert _consume(conn, VERIFICATION, limit=3) is None
    assert _consume(conn, SUMMARY, limit=3) == 1


def test_날짜가_바뀌면_예산이_리셋된다(conn):
    """새 UTC 날짜는 새 PK 행이라 자연히 0 부터 시작한다."""
    for _ in range(3):
        _consume(conn, limit=3)
    assert _consume(conn, limit=3) is None

    # 어제 자로 옮겨 놓는다 = 오늘 행이 없는 상태.
    x(conn, "UPDATE llm_daily_usage SET usage_date = usage_date - 1")

    assert _consume(conn, limit=3) == 1
    assert _used(conn) == 1


def test_상한을_올리면_다시_통과한다(conn):
    """운영에서 상한을 키웠을 때 그 날 바로 풀려야 한다 — 다음 날까지 막히면 못 쓴다."""
    for _ in range(3):
        _consume(conn, limit=3)
    assert _consume(conn, limit=3) is None

    assert _consume(conn, limit=5) == 4


def test_kind_는_두_값만_받는다(conn):
    """오타가 새 예산 통을 조용히 만들어내면 상한이 통째로 새어 나간다."""
    with pytest.raises(psycopg.errors.CheckViolation):
        x(conn,
          "INSERT INTO llm_daily_usage (usage_date, kind, calls) "
          "VALUES ((now() AT TIME ZONE 'UTC')::date, %s, 1)", "sumary")


def test_calls_는_음수가_될_수_없다(conn):
    with pytest.raises(psycopg.errors.CheckViolation):
        x(conn,
          "INSERT INTO llm_daily_usage (usage_date, kind, calls) "
          "VALUES ((now() AT TIME ZONE 'UTC')::date, %s, -1)", SUMMARY)
