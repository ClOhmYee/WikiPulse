"""스냅샷 생산 드라이버 — 실 데이터 소스 배선 (WP-75 · -99).

    python -m cluster.driver --dsn "$DATABASE_URL" --source replay
    python -m cluster.driver --dsn ... --source replay --snapshot-ts 2024-10-07T14:00:00Z
    python -m cluster.driver --dsn ... --source replay --dry-run

`spike` 테이블(WP-94 런타임 출력)을 읽어 씨드를 만들고, 순수 로직
(`snapshot.build_snapshot`)으로 스냅샷을 생산해 `writer.persist_snapshot` 으로 저장한다.
로직·점수·게이트는 여기서 정하지 않는다 — 전부 -75 자산을 그대로 부른다.

배선된 것 / 아직 아닌 것 (WP-99)
    ✅ 씨드: `spike` + `wiki_page` 조인 → `load_seeds_from_spike`
    ✅ 이전 first_detected_at: `issue_cluster` 의 issue_key 별 min → `load_prior_first_detected`
    ⛔ Clickstream 이웃(비-씨드): 적재본이 아직 없다(-81 코드는 Done, 산출물 0건).
       `load_clickstream_neighbors` 는 구현돼 있으니 덤프가 생기면 `--clickstream` 으로 잇는다.
    ⛔ 문서 생성일: `load_creation_dates` 는 여전히 골격 — **비-씨드 경로 전용**이라
       씨드만 있는 지금은 호출되지 않는다.
    ⛔ Wikidata 점선 간선: 선택 사항. 없으면 안 그린다.

    → 지금은 **씨드 단독 스냅샷**이다. `_build_cluster` 는 이웃이 비어도 씨드 멤버 1개·
      간선 0개로 정상 생산한다(계약상 유효). 비-씨드 규칙(WP-77)은 이 파일 밖이다.

스냅샷 시점을 어떻게 고르나
    `spike.detected_at` 의 **고유값 하나가 스냅샷 하나**다. 새 문턱이나 lookback 창을
    만들지 않으려고 이렇게 했다 — 기존 행을 다시 묶기만 한다. 같은 순간에 잡힌 급증들이
    한 스냅샷의 클러스터들이 되고, 같은 문서는 `issue_key` 로 시점 간에 이어진다.

🔴 **오름차순으로 처리해야 `first_detected_at` 이 멱등이다.**
    `first_detected_at` 은 "이 issue_key 가 과거에 처음 잡힌 시각"이라 앞 시점이 먼저
    저장돼 있어야 한다. 내림차순으로 돌리면 뒤 시점이 먼저 들어가 그게 '최초'가 되고,
    재실행 때마다 값이 바뀐다 — 에러 없이 NEW 배지가 흔들린다.

⚠️ **`spike` 에는 `window_end` 컬럼이 없다.** `Seed.window_end` 는 `spike.detected_at`
    에서 온다 — WP-94 의 런타임이 `detected_at = 윈도우 끝`으로 쓰기 때문이다
    (`spike/runtime.py`). 그 규칙이 바뀌면 여기가 조용히 어긋나므로 `window_start` 보다
    뒤인지 확인하고, 아니면 막는다.

🔴 **이 DB 입력 경로는 `replay` 전용이다 (WP-99).**
    `spike` 에는 출처(live/replay) 컬럼이 **없다.** 그래서 이 어댑터는 어떤 행이 리플레이
    산출물이고 어떤 행이 LIVE 산출물인지 가릴 수 없다. `source` 를 자유롭게 받으면
    **리플레이 spike 를 읽어 `issue_cluster.source='live'` 로 저장하는 거짓 라벨링**이
    가능해진다 — 화면·API 가 그걸 실시간 이슈로 그리는데 에러는 안 난다.
    그래서 `SPIKE_SOURCE`(=`replay`) 하나만 허용하고 나머지는 거부한다.
    LIVE 연결은 `spike` 에 provenance 컬럼을 두는 계약과 함께 **별도 스토리**에서 한다
    (스키마 변경이라 이 스토리 범위 밖).

    `load_seeds_from_spike` 는 아예 `source` 를 받지 않는다 — 받으면 조회 필터로
    오해된다. 라벨은 상위 런타임(`build_snapshot_at`)이 붙이고 거기서 검사한다.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from datetime import date, datetime, timezone
from pathlib import Path

from batch.clickstream import NeighborRef, neighbors_for, read_shards

from .snapshot import Neighbor, Seed, Snapshot, build_snapshot
from .writer import persist_snapshot

#: 이 DB 입력 경로가 낼 수 있는 유일한 산출물 라벨 (모듈 독스트링 🔴).
#: `spike` 에 provenance 컬럼이 생기기 전까지 LIVE 는 여기서 만들 수 없다.
SPIKE_SOURCE = "replay"

#: 한 시점의 씨드. `detected_at` 이 그 시점이다.
#: 정렬은 저장 순서일 뿐 — 노출 순위는 백엔드가 pulse_score 로 다시 매긴다.
SELECT_SEEDS_SQL = """
SELECT s.id, s.page_id, p.wiki, p.title, s.window_start, s.detected_at,
       s.edit_count, s.view_ratio, s.spike_score
  FROM spike s
  JOIN wiki_page p ON p.id = s.page_id
 WHERE s.detected_at = %s
 ORDER BY s.spike_score DESC, s.page_id
"""

#: 저장할 스냅샷 시점들. 오름차순 — first_detected_at 멱등성이 여기 달렸다(위 🔴).
SELECT_SNAPSHOT_TIMES_SQL = """
SELECT DISTINCT s.detected_at
  FROM spike s
 WHERE (%s::timestamptz IS NULL OR s.detected_at >= %s::timestamptz)
   AND (%s::timestamptz IS NULL OR s.detected_at <= %s::timestamptz)
 ORDER BY s.detected_at
"""

#: issue_key 별 최초 감지 시각. build_snapshot 의 prior_first_detected 입력.
SELECT_PRIOR_FIRST_DETECTED_SQL = """
SELECT issue_key, min(snapshot_ts)
  FROM issue_cluster
 WHERE source = %s AND issue_key IS NOT NULL
 GROUP BY issue_key
"""


def _completeness(view_ratio: float | None) -> str:
    """`spike` 한 행의 지표 완성도. V1 의 view_ratio 주석 그대로 읽는다.

    "Pageviews 가 1시간 늦어서 판정 시점에 NULL 일 수 있다. NULL = 아직 2차 판정 전."
    → 값이 있으면 complete, 없으면 pending.

    ⚠️ `spike` 만으로는 pending(곧 온다)과 unavailable(그 구간 조회수 적재본이 아예 없다)을
    **구분할 수 없다.** 2024-10 처럼 조회수 덤프가 없는 구간도 pending 으로 나온다.
    구분하려면 적재 범위를 아는 쪽이 값을 넣어줘야 한다 — 후속 과제.
    """
    return "complete" if view_ratio is not None else "pending"


def require_spike_source(source: str) -> str:
    """이 DB 입력 경로가 낼 수 있는 라벨인지 검사한다. 아니면 거부.

    ~~`source` 를 자유롭게 받았다~~ → `replay` 만 (WP-99). `spike` 에 출처
    컬럼이 없어 리플레이 행과 LIVE 행을 못 가르기 때문이다 — 그대로 두면 리플레이
    산출물이 `source='live'` 로 저장되고, API·화면이 그걸 실시간 이슈로 그린다.
    조용히 틀리는 쪽이라 경계에서 막는다.
    """
    if source != SPIKE_SOURCE:
        raise ValueError(
            f"이 경로는 source={SPIKE_SOURCE!r} 만 만든다 (받은 값: {source!r}). "
            "spike 테이블에 provenance 컬럼이 없어 LIVE 행과 리플레이 행을 가릴 수 없다 "
            "— LIVE 연결은 그 계약과 함께 별도 스토리에서 한다."
        )
    return source


def load_seeds_from_spike(conn, snapshot_ts: datetime) -> list[Seed]:
    """`spike` + `wiki_page` 를 조인해 이 시점의 씨드를 만든다.

    🔴 **`source` 를 받지 않는다.** `spike` 에 출처 컬럼이 없어 걸 수 있는 조건이 아니고,
    파라미터로 두면 "이 source 로 거른다"로 오해된다(~~-75 골격 시그니처~~ →
    2026-09-15, WP-99). 산출물 라벨은 `build_snapshot_at` 이 붙이고 거기서
    `require_spike_source` 로 검사한다.

    `event_date` = `window_start` 의 날짜(UTC). 생성일 창의 중심이며, 씨드 단독
    스냅샷에서는 쓰이지 않지만(이웃이 없다) 계약대로 채운다.
    """
    with conn.cursor() as cur:
        cur.execute(SELECT_SEEDS_SQL, (snapshot_ts,))
        rows = cur.fetchall()

    seeds: list[Seed] = []
    for (_id, page_id, wiki, title, window_start, detected_at,
         edit_count, view_ratio, spike_score) in rows:
        # spike 에 window_end 가 없어 detected_at 을 쓴다(모듈 독스트링 ⚠️).
        # Seed 계약은 "시작 < 종료" 다 — 어긋나면 조용히 이상한 구간이 저장되므로 막는다.
        if detected_at <= window_start:
            raise ValueError(
                f"spike(page_id={page_id}, window_start={window_start}) 의 "
                f"detected_at({detected_at}) 이 window_start 보다 뒤가 아니다. "
                "WP-94 런타임은 detected_at = 윈도우 끝으로 쓴다 — "
                "다른 생산자가 처리 시각을 넣었는지 확인할 것."
            )
        seeds.append(Seed(
            page_id=page_id,
            wiki=wiki,
            title=title,
            event_date=window_start.astimezone(timezone.utc).date(),
            spike_score=float(spike_score),
            window_start=window_start,
            window_end=detected_at,
            edit_count=edit_count,
            # spike 는 조회수 원값·기준선을 저장하지 않는다(edit_z·view_ratio 만).
            # 없는 값을 지어내지 않고 None 으로 둔다 — 화면이 '미제공'으로 그린다.
            views=None,
            edit_baseline=None,
            view_baseline=None,
            completeness=_completeness(view_ratio),
        ))
    return seeds


def load_snapshot_times(
    conn, since: datetime | None = None, until: datetime | None = None
) -> list[datetime]:
    """저장할 스냅샷 시점들을 **오름차순**으로. `spike.detected_at` 의 고유값이다."""
    with conn.cursor() as cur:
        cur.execute(SELECT_SNAPSHOT_TIMES_SQL, (since, since, until, until))
        return [row[0] for row in cur.fetchall()]


def load_prior_first_detected(conn, source: str) -> dict[str, datetime]:
    """이미 저장된 스냅샷에서 issue_key 별 최초 감지 시각을 읽는다.

    `build_snapshot(prior_first_detected=...)` 입력이다. 같은 사건이 여러 시점에 걸쳐
    잡히면 모든 시점의 `first_detected_at` 이 가장 이른 시각을 가리켜야 NEW 배지가
    흔들리지 않는다.

    🔴 스냅샷 **하나를 저장할 때마다 다시 읽는다.** 앞 시점이 방금 저장됐을 수 있어서다.
    """
    with conn.cursor() as cur:
        cur.execute(SELECT_PRIOR_FIRST_DETECTED_SQL, (source,))
        return {key: ts for key, ts in cur.fetchall()}


def load_clickstream_neighbors(
    shards_dir: str | Path, seeds: list[Seed]
) -> dict[str, list[NeighborRef]]:
    """적재본(WP-81)에서 각 씨드의 Clickstream 이웃을 한 번의 순회로 읽는다.

    씨드 제목 → 이웃(title, n, directed) 목록. 반환값의 title/n/directed 를
    build_clusters 가 page_id·생성일과 합쳐 cluster.snapshot.Neighbor 로 만든다
    (아래 build_neighbor_inputs). 덤프가 수백만 행이라 씨드별 재스캔은 하지 않는다.
    """
    seed_titles = {s.title for s in seeds}
    return neighbors_for(read_shards(shards_dir), seed_titles)


def build_neighbor_inputs(
    refs: list[NeighborRef],
    month: str,
    page_of_title: dict[str, tuple[int, str]],
    created_of_page: dict[int, date | None],
) -> list[Neighbor]:
    """NeighborRef 를 cluster.snapshot.Neighbor 로 변환한다.

    page_of_title: 이웃 제목 → (page_id, wiki)   — wiki_page 조회(미배선)
    created_of_page: page_id → 생성일             — mediawiki_history(WP-56, 미배선)
    두 소스가 아직 없으면 그 이웃은 건너뛴다(생성일 미상은 게이트가 어차피 탈락시킨다).
    """
    out: list[Neighbor] = []
    for ref in refs:
        page = page_of_title.get(ref.title)
        if page is None:
            continue
        page_id, wiki = page
        out.append(Neighbor(
            page_id=page_id,
            wiki=wiki,
            title=ref.title,
            clickstream_n=ref.n,
            clickstream_month=month,
            created_at=created_of_page.get(page_id),
            directed=ref.directed,
        ))
    return out


def load_creation_dates(page_ids: list[int]) -> dict[int, object]:
    """mediawiki_history page_creation_timestamp 로 생성일을 채운다. (미구현 — 골격)

    🔴 **비-씨드(Clickstream 이웃) 경로 전용이다.** 씨드 단독 스냅샷(WP-99)에서는
    호출되지 않는다 — 생성일 창은 이웃을 거르는 게이트라 이웃이 없으면 쓸 데가 없다.
    Clickstream 적재본(-81 산출물)이 생길 때 `load_pages_by_title` 과 함께 채운다.
    """
    raise NotImplementedError("mediawiki_history 생성일 어댑터는 소스 배선 시 구현한다")


# --- 런타임 -----------------------------------------------------------------

def build_snapshot_at(
    conn,
    snapshot_ts: datetime,
    source: str,
    *,
    neighbors: dict[int, Sequence[Neighbor]] | None = None,
) -> Snapshot:
    """한 시점의 스냅샷을 생산한다(저장 안 함). 로직은 전부 -75 자산이다.

    🔴 `source` 는 `SPIKE_SOURCE`(=replay) 만 받는다 — 여기가 "spike 를 읽어 라벨을
    붙이는" 유일한 지점이라 거짓 라벨링을 여기서 막는다(모듈 독스트링).

    `neighbors` 를 안 주면 씨드 단독이다. Clickstream 적재본이 생기면 호출자가
    `load_clickstream_neighbors` → `build_neighbor_inputs` 결과를 넘기면 된다 —
    `build_snapshot` 계약이 이미 그 형태다.
    """
    require_spike_source(source)
    seeds = load_seeds_from_spike(conn, snapshot_ts)
    return build_snapshot(
        snapshot_ts, source, seeds, neighbors or {},
        prior_first_detected=load_prior_first_detected(conn, source),
    )


def run(
    conn,
    source: str,
    *,
    snapshot_times: Sequence[datetime],
    dry_run: bool = False,
) -> list[Snapshot]:
    """시점들을 순서대로 생산하고 저장한다. 커밋은 호출자 책임.

    🔴 `snapshot_times` 는 **오름차순**이어야 한다(모듈 독스트링). `load_snapshot_times`
    가 그렇게 돌려준다.

    `source` 는 `SPIKE_SOURCE` 만 — 시점이 0개여도 먼저 막는다. 늦게 막으면 빈 목록일 때만
    통과해 버려서, 나중에 데이터가 생겼을 때 갑자기 실패한다.
    """
    require_spike_source(source)
    produced: list[Snapshot] = []
    for snapshot_ts in snapshot_times:
        snapshot = build_snapshot_at(conn, snapshot_ts, source)
        if not dry_run:
            # 멱등은 writer 계약 그대로 — (source, snapshot_ts) 단위 지우고 다시 넣는다.
            persist_snapshot(conn, snapshot)
        produced.append(snapshot)
    return produced


def _parse_ts(value: str) -> datetime:
    """CLI 시각 인자 → tz-aware UTC. naive 면 막는다(세션 시간대로 밀린다)."""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError(
            f"시각에 시간대가 없다: {value!r}. 끝에 Z 나 +09:00 을 붙인다 — "
            "naive 는 세션 시간대로 해석돼 조용히 밀린다."
        )
    return parsed.astimezone(timezone.utc)


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="spike → 클러스터 스냅샷 생산·적재 (WP-99)")
    p.add_argument("--dsn", default=os.environ.get("DATABASE_URL", ""),
                   help="PostgreSQL DSN (기본: $DATABASE_URL)")
    # 🔴 replay 만. spike 에 provenance 컬럼이 없어 LIVE 를 여기서 만들 수 없다
    # (모듈 독스트링). choices 를 좁혀 argparse 가 먼저 거절하게 둔다.
    p.add_argument("--source", default=SPIKE_SOURCE, choices=(SPIKE_SOURCE,),
                   help=f"산출물 라벨(issue_cluster.source). 현재 {SPIKE_SOURCE} 전용 — "
                        "spike 에 출처 컬럼이 없어 LIVE 는 별도 스토리에서 잇는다")
    p.add_argument("--snapshot-ts", type=_parse_ts,
                   help="이 시점 하나만 생산한다. 없으면 spike.detected_at 고유값 전부")
    p.add_argument("--since", type=_parse_ts, help="시점 범위 시작(포함)")
    p.add_argument("--until", type=_parse_ts, help="시점 범위 끝(포함)")
    p.add_argument("--dry-run", action="store_true", help="저장 없이 생산만")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if not args.dsn:
        print("DSN 이 없다. --dsn 또는 $DATABASE_URL 을 준다.", file=sys.stderr)
        return 2
    if args.snapshot_ts and (args.since or args.until):
        print("--snapshot-ts 와 --since/--until 은 같이 못 쓴다.", file=sys.stderr)
        return 2

    import psycopg     # 이 CLI 에서만 필요 — 순수 로직은 드라이버 없이도 돈다

    with psycopg.connect(args.dsn) as conn:
        times = ([args.snapshot_ts] if args.snapshot_ts
                 else load_snapshot_times(conn, args.since, args.until))
        if not times:
            print("생산할 시점이 없다 — spike 테이블이 비었거나 범위 밖이다.")
            return 1

        print(f"시점 {len(times)}개 ({times[0].isoformat()} ~ {times[-1].isoformat()}) "
              f"source={args.source}{' [dry-run]' if args.dry_run else ''}")
        snapshots = run(conn, args.source, snapshot_times=times, dry_run=args.dry_run)
        if not args.dry_run:
            conn.commit()

    clusters = sum(s.cluster_count for s in snapshots)
    members = sum(len(c.members) for s in snapshots for c in s.clusters)
    edges = sum(len(c.edges) for s in snapshots for c in s.clusters)
    print(f"스냅샷 {len(snapshots)} / 클러스터 {clusters} / 멤버 {members} / 간선 {edges}")
    for snapshot in snapshots:
        for cluster in snapshot.clusters:
            print(f"  {snapshot.snapshot_ts.isoformat()}  {cluster.issue_key}  "
                  f"pulse {cluster.pulse_score:.3f}  hot {cluster.hot}  "
                  f"최초감지 {cluster.first_detected_at.isoformat()}  "
                  f"멤버 {len(cluster.members)} 간선 {len(cluster.edges)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
