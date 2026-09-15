"""cluster_org_mention 멱등 저장 (WP-65).

한 이슈 클러스터(cluster_id)의 기관명 lift 목록을 통째로 쓴다. cluster/writer.py
와 같은 규약이다 — 같은 cluster_id 를 다시 저장하면 기존 행을 지우고 새로 넣어,
리플레이 배치가 재계산해도 중복이 쌓이지 않는다(재계산 호환). 한 클러스터 저장은
한 트랜잭션이고, commit 은 호출자가 책임진다(배치 단위 커밋·테스트 롤백을 위해).

ticker 는 None 일 수 있다(종목 마스터 미매칭). 스키마상 NULL 허용이고, 미매칭
기관도 RAG 컨텍스트로 저장한다.
"""

from __future__ import annotations

from collections.abc import Sequence

from .lift import OrgLift


def _delete_existing(cur, cluster_id: int) -> None:
    cur.execute("DELETE FROM cluster_org_mention WHERE cluster_id = %s", (cluster_id,))


def persist_org_mentions(
    conn, cluster_id: int, mentions: Sequence[tuple[OrgLift, str | None]]
) -> int:
    """(OrgLift, ticker) 목록을 cluster_org_mention 에 멱등 저장. 저장 행수 반환.

    mentions 는 rank() 결과에 match_ticker() 로 ticker(또는 None)를 붙인 것이다.
    org_name 은 (cluster_id, org_name) PK 라 이슈 내에서 유일해야 한다 — rank()
    가 이미 기관명당 한 행이라 그대로 만족한다.
    """
    with conn.cursor() as cur:
        _delete_existing(cur, cluster_id)
        for lift, ticker in mentions:
            cur.execute(
                """
                INSERT INTO cluster_org_mention
                    (cluster_id, org_name, ticker, issue_count, corpus_count, lift)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    cluster_id, lift.org_name, ticker,
                    lift.issue_count, lift.corpus_count, lift.lift,
                ),
            )
    return len(mentions)
