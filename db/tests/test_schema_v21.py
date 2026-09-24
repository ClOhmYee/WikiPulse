"""이슈 리포트 섹션 — V21 (WP-223).

여기서 보는 것은 세 가지다.
  1. 요약 워커의 upsert 가 리포트 컬럼을 지우지 않는가 — 지우면 요약이 다시 돌 때마다
     리포트가 조용히 사라진다.
  2. 상세 API 의 읽기 질의(`IssueQueryRepository.findReport`)가 리포트 없는 이슈에서 빈 결과를 낸다.
  3. report_sections 는 배열만 받는다.

백엔드 테스트는 DB 없이 도는 목 검사라 실제 SQL 이 맞는지는 이 파일이 본다.
"""

from __future__ import annotations

import json

import pytest

from conftest import q, x  # 공용 픽스처(conn·rollback)·헬퍼

pytest.importorskip("psycopg", reason="psycopg 미설치")
import psycopg  # noqa: E402

SNAPSHOT = "2026-07-19T23:00:00Z"

SECTIONS = [{"id": "overview", "title": "이슈 개요", "body": "본문", "evidenceIds": ["1"]}]

#: IssueSummaryRepository 의 upsert 와 같은 문장.
SUMMARY_UPSERT = """
INSERT INTO issue_report (cluster_id, summary, model, generated_at)
VALUES (%s, %s, %s, now())
ON CONFLICT (cluster_id) DO UPDATE
   SET summary      = EXCLUDED.summary,
       model        = EXCLUDED.model,
       generated_at = EXCLUDED.generated_at
"""

#: IssueQueryRepository.findReport 와 같은 문장.
FIND_REPORT = """
SELECT report_sections::text, report_model, report_generated_at
  FROM issue_report
 WHERE cluster_id = %s AND report_sections IS NOT NULL
"""


def _cluster(conn) -> int:
    x(conn, "INSERT INTO issue_cluster (snapshot_ts, pulse_score, source) VALUES (%s, 1.0, 'replay')",
      SNAPSHOT)
    return q(conn, "SELECT max(id) FROM issue_cluster")[0][0]


def test_요약이_다시_써져도_리포트는_남는다(conn):
    cid = _cluster(conn)
    x(conn, SUMMARY_UPSERT, cid, "첫 요약", "m1")
    x(conn, "UPDATE issue_report SET report_sections = %s::jsonb, report_model = 'r1', "
            "report_generated_at = now() WHERE cluster_id = %s",
      json.dumps(SECTIONS, ensure_ascii=False), cid)

    x(conn, SUMMARY_UPSERT, cid, "둘째 요약", "m2")

    sections, model, _ = q(conn, FIND_REPORT, cid)[0]
    assert json.loads(sections) == SECTIONS
    assert model == "r1"
    assert q(conn, "SELECT summary FROM issue_report WHERE cluster_id = %s", cid)[0][0] == "둘째 요약"


def test_리포트가_없으면_읽기_질의가_비어_있다(conn):
    cid = _cluster(conn)
    x(conn, SUMMARY_UPSERT, cid, "요약만", "m1")
    assert q(conn, FIND_REPORT, cid) == []


def test_섹션은_배열만_받는다(conn):
    cid = _cluster(conn)
    x(conn, SUMMARY_UPSERT, cid, "요약", "m1")
    with pytest.raises(psycopg.errors.CheckViolation):
        x(conn, "UPDATE issue_report SET report_sections = '{\"id\": 1}'::jsonb WHERE cluster_id = %s",
          cid)
