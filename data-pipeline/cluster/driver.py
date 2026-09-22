"""스냅샷 생산 드라이버 — 실 데이터 소스 배선 (WP-75 · -99 · -102).

    python -m cluster.driver --dsn "$DATABASE_URL" --source replay
    python -m cluster.driver --dsn "$DATABASE_URL" --source live
    python -m cluster.driver --dsn ... --source replay --snapshot-ts 2024-10-07T14:00:00Z
    python -m cluster.driver --dsn ... --source replay \
        --clickstream-root ./data/clickstream \
        --creation-index ./data/page-creation/enwiki/2024-09_2024-10
    python -m cluster.driver --dsn ... --source live --dry-run

`spike` 테이블(WP-94 런타임 출력)을 읽어 씨드를 만들고, 순수 로직
(`snapshot.build_snapshot`)으로 스냅샷을 생산해 `writer.persist_snapshot` 으로 저장한다.
로직·점수·게이트는 여기서 정하지 않는다 — 전부 -75 자산을 그대로 부른다.

배선된 것 / 아직 아닌 것 (~~WP-99~~ → -115, 2026-09-17)
    ✅ 씨드: `spike` + `wiki_page` 조인 → `load_seeds_from_spike`
    ✅ 이전 first_detected_at: `issue_cluster` 의 issue_key 별 min → `load_prior_first_detected`
    ✅ Clickstream 이웃(추가 씨드): `MonthlyNeighborSource` → `--clickstream-root` (-115)
    ✅ 문서 생성 시각(UTC): `batch/page_creation` 인덱스 → `--creation-index` (-115)
    ✅ 날짜별 편집 수(봇 포함): `batch/page_edit_daily` 인덱스 → `--edit-index` (-145).
       **선택이다** — 주면 비-씨드 재급증 멤버가 붙고, 안 주면 추가 씨드만 나온다.
    ✅ 이웃 제목 → page_id: `load_pages_by_title` (-115). 없는 문서는 등록한다
    ⛔ Wikidata 점선 간선: 선택 사항. 없으면 안 그린다.

    🔴 **이웃 경로는 여전히 생성일 창(-51) 하나뿐이다.** 그 창을 통과한 이웃은
      명세 v0.3 §3.2 4번의 **추가 씨드(`is_seed=true`)** 로 저장한다(2026-09-18 정정).
      "기존 문서가 사건으로 재조명되는" 비-씨드
      `is_seed=false`(WP-77: 재급증 비율 >= 5 AND 절대 편집 >= 20)는
      명세에만 있고 **코드에 없다** (2026-09-17 확인). `Mojtaba_Khamenei` 류는 아직
      멤버가 되지 않는다. 이 파일이 그 규칙을 대신 만들지 않는다.

    이웃 인자를 안 주면 예전처럼 **씨드 단독 스냅샷**이다. `_build_cluster` 는 이웃이
    비어도 씨드 멤버 1개·간선 0개로 정상 생산한다(계약상 유효).

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

🔴 **`source` 는 산출물 라벨이 아니라 입력 필터다 (WP-102).**
    ~~`SPIKE_SOURCE`(=replay) 하나만 허용~~ → `live`·`replay` 둘 다 (2026-09-16).

    -99 가 replay 하나로 묶어 둔 이유는 `spike` 에 출처 컬럼이 **없었기** 때문이다.
    어떤 행이 리플레이 산출물이고 어떤 행이 LIVE 산출물인지 가릴 수 없으니, `source`
    를 자유롭게 받으면 리플레이 spike 를 읽어 `issue_cluster.source='live'` 로 저장하는
    **거짓 라벨링**이 성립했다. V5(`db/migrations/V5__spike_source.sql`)가 `spike.source`
    를 만들면서 그 전제가 사라졌고, 여기가 그 가드를 걷는 자리다.

    🔴 **가드를 걷는 조건은 "조회에 source 를 건다" 이지 "라벨을 자유롭게 받는다" 가
    아니다.** `source` 를 출력 라벨로만 쓰고 입력 질의에 안 걸면 -99 가 막던 거짓
    라벨링이 **그대로 돌아온다** — LIVE 스냅샷에 2024년 리플레이 씨드가 섞여 들어가고
    에러는 안 난다. 그래서 `SELECT_SEEDS_SQL`·`SELECT_SNAPSHOT_TIMES_SQL` 둘 다
    `s.source = %s` 를 갖고, 조회 함수가 `source` 를 **필수 인자**로 받는다
    (~~`load_seeds_from_spike` 는 source 를 아예 받지 않는다~~ → 받는다, -102).

    ⚠️ 두 출처는 같은 `(page_id, window_start)` 를 각각 가질 수 있다(V5 가 UNIQUE 키에
    source 를 넣었다). 즉 **같은 `detected_at` 에 replay 행과 live 행이 공존한다** —
    `detected_at` 만으로 시점을 고르면 두 출처가 한 스냅샷에 섞인다. 시점 목록부터
    출처별로 뽑는 이유다.

    산출물 쪽 격리는 이미 서 있다: `issue_key_of` 가 `{source}:{wiki}:{title}` 라
    두 출처의 키가 겹치지 않고, `writer.persist_snapshot` 의 삭제·재적재 단위가
    `(source, snapshot_ts)` 라 한쪽을 다시 돌려도 다른 쪽이 안 지워진다.

    어휘는 `spike.spike_sink.SPIKE_SOURCES` 하나를 쓴다 — V5 의 CHECK 제약·
    `issue_cluster.source`(V1)와 같은 목록이다. 여기서 따로 정의하면 세 벌이 된다.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field as dataclass_field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from batch.clickstream import (
    NeighborRef,
    neighbors_for,
    read_shards,
    select_completed_month,
)
from batch.page_creation import creation_dates_for
from batch.page_edit_daily import coverage_span, edit_days_for, sum_days
from spike.spike_sink import SPIKE_SOURCES

from . import asof_links
from .snapshot import (
    DEFAULT_CREATION_WINDOW_DAYS,
    DEFAULT_RESURGENCE_MIN_EDITS,
    DEFAULT_RESURGENCE_RATIO,
    EditResurgence,
    Neighbor,
    Seed,
    Snapshot,
    build_snapshot,
    _passes_resurgence,
    _within_creation_window,
)
from .writer import persist_snapshot

#: Clickstream 근거 월은 **`batch.clickstream.select_completed_month` 하나가 고른다**
#: (2026-09-18, -115 + develop 머지).
#:
#: ~~`CLICKSTREAM_MONTH_RULES = ("previous", "event")` 와 `clickstream_month_for`~~
#:    -> 제거. -115 브랜치가 develop 머지 전까지 쓰던 로컬 스위치였다. 규칙이 두 벌이면
#:    한쪽만 바뀌어도 에러 없이 결과가 갈린다 — 그래서 머지 시점에 한 벌로 합쳤다.
#:    직전 월 우선 · 미공개·검증 실패 시 최신 완료본(통상 전전월) 폴백 · `_manifest.json`
#:    검증이 전부 그쪽 계약이고, `snapshot._is_completed_clickstream_month` 가 그 위의
#:    이중 방어다(명세 v0.3 §3.2 4번 event-time 상한).
#:
#: 🔴 **사건 당월 덤프는 쓰지 않는다.** 월이 끝나야 나오는 덤프라 운영 당시에는 없던
#:    근거다. §11 이 `-51` 의 당월 dump 실측에 "운영 당시에는 사용할 수 없던 당월 덤프를
#:    월 종료 후 분석한 품질 검증이며, 해당 월 스냅샷 입력으로 사용했다는 뜻이 아니다"
#:    를 달아 두었다. 과거 원본을 나중에 적재하는 리플레이에도 같은 계약이 걸린다.
#:
#: 배선 regression 실측 (2024-09-01~11-01, 스냅샷 1,426 · 클러스터 6,614, 완료 월 규칙):
#:    비-루트 멤버 6,134 · 2+ 멤버 클러스터 1,172(17.7%) · 최대 120 멤버
#:    Milton 1 멤버 · Yagi 1 멤버(둘 다 이웃 0) · Helene 최대 6 멤버.
#:    ~~"셋 다 이웃 0"~~ 은 틀린 서술이었다 (2026-09-18 DB 재확인) — Helene 은
#:    사건일이 09-23 이라 10월 스냅샷의 직전 월(2024-09) 덤프에 이미 들어 있다.
#:
#: ⚠️ **이 수치는 탐지 성능 근거가 아니다.** 기반인 2024-09~10 replay seed 는
#:    조회수를 적재하지 않고 옛 `편집 급증 OR 조회수` detector 로 만든 것이라
#:    WP-109 매니페스트에서 폐기됐다. 현행 2단계 관문(-126)의 산출물이
#:    아니므로 MVP 탐지 성능으로 인용하면 안 되고, **이웃 배선(-115) 자체가
#:    끝까지 이어지는지 보는 regression 데이터**로만 쓴다.

#: 한 시점·한 출처의 씨드. `detected_at` 이 그 시점이다.
#: 🔴 `s.source = %s` 가 이 스토리(-102)의 핵심이다. 빼면 LIVE 스냅샷에 리플레이 씨드가
#: 섞이는데 에러가 안 난다 — V5 가 UNIQUE 키에 source 를 넣어 두 출처가 같은
#: `(page_id, window_start)` 를, 따라서 같은 `detected_at` 을 각각 갖기 때문이다.
#: 정렬은 저장 순서일 뿐 — 노출 순위는 백엔드가 pulse_score 로 다시 매긴다.
SELECT_SEEDS_SQL = """
SELECT s.id, s.page_id, p.wiki, p.title, s.window_start, s.detected_at,
       s.edit_count, s.views, s.view_baseline, s.view_ratio, s.spike_score,
       s.max_rev_id
  FROM spike s
  JOIN wiki_page p ON p.id = s.page_id
 WHERE s.source = %s
   AND s.detected_at = %s
 ORDER BY s.spike_score DESC, s.page_id
"""

#: 저장할 스냅샷 시점들. 오름차순 — first_detected_at 멱등성이 여기 달렸다(위 🔴).
#: 🔴 시점 목록도 출처별이다. 합쳐서 뽑으면 live 실행이 리플레이에만 있는 시점까지
#: 돌아 `cluster_count=0` 인 LIVE 스냅샷을 무더기로 만든다 — "완료된 빈 스냅샷" 과
#: 구분되지 않아 `/issues/snapshots` 에 유령 시점이 뜬다.
SELECT_SNAPSHOT_TIMES_SQL = """
SELECT DISTINCT s.detected_at
  FROM spike s
 WHERE s.source = %s
   AND (%s::timestamptz IS NULL OR s.detected_at >= %s::timestamptz)
   AND (%s::timestamptz IS NULL OR s.detected_at <= %s::timestamptz)
 ORDER BY s.detected_at
"""

#: 여러 시점의 씨드 제목을 한 번에. Clickstream 덤프를 월당 한 번만 훑으려면
#: 그 월에 필요한 씨드 제목을 미리 다 알아야 한다(덤프가 수천만 행이라 시점마다
#: 다시 훑을 수 없다). `s.source = %s` 는 위 🔴 와 같은 이유로 여기도 걸린다.
SELECT_SEED_TITLES_SQL = """
SELECT DISTINCT p.wiki, p.title
  FROM spike s
  JOIN wiki_page p ON p.id = s.page_id
 WHERE s.source = %s
   AND s.detected_at = ANY(%s)
"""

#: 이웃 제목 → page_id. `cluster_member.page_id` 가 `wiki_page` 를 참조하므로
#: 멤버가 되려면 행이 있어야 한다. 🔴 N+1 금지 — 후보를 한 번에 넘긴다.
SELECT_PAGES_BY_TITLE_SQL = """
SELECT title, id FROM wiki_page WHERE wiki = %s AND title = ANY(%s)
"""

#: 없는 이웃 문서를 등록한다. `spike/baseline_sink.py` 의 `RESOLVE_PAGE_SQL` 과 같은
#: UPSERT 다 — 자연키가 같으니 규칙도 같아야 한다.
#: ⚠️ `DO NOTHING` 이라 RETURNING 이 충돌 행을 안 준다. 넣고 나서 다시 SELECT 한다
#: (왕복 2회, 후보 수와 무관). `DO UPDATE last_seen` 으로 바꾸면 이웃 조회가
#: 기존 문서의 last_seen 을 건드려 "최근 본 문서" 의미가 흐려진다.
INSERT_PAGES_SQL = """
INSERT INTO wiki_page (wiki, title) VALUES (%s, %s)
ON CONFLICT (wiki, title) DO NOTHING
"""

#: issue_key 별 최초 감지 시각. build_snapshot 의 prior_first_detected 입력.
SELECT_PRIOR_FIRST_DETECTED_SQL = """
SELECT issue_key, min(snapshot_ts)
  FROM issue_cluster
 WHERE source = %s AND issue_key IS NOT NULL
 GROUP BY issue_key
"""


def _completeness(views: int | None) -> str:
    """`spike` 한 행의 지표 완성도. **조회수 원값이 있으면 2차 판정이 돌았다는 뜻이다.**

    ~~view_ratio 가 있으면 complete~~ → **views 로 판단한다**
    (2026-09-18, WP-129, V7).

    🔴 왜 바꿨나. `view_ratio` 는 두 뜻을 지고 있었다:
        "배수를 낼 수 없음"(기준선 표본 없음)  vs  "아직 판정 안 됨"(조회수 미도착)
    WP-126 의 2단계 계약에서 **표본 없는 문서는 배수가 정당하게 NULL** 이다 —
    분모(view_ewma)가 없다. 신규 문서는 대부분 이 경로로 확정되는데(절대 하한 >= 100,
    "0 에서의 급등"), 그게 전부 pending 으로 저장됐다. 판정은 끝났는데 화면은 대기로
    보였다 — canary 실측(docs/validation/2026-09-18-one-day-e2e-canary.md §5).

    `views` 는 뜻이 하나다: 있으면 조회수를 보고 판정했다.

    ⚠️ 여전히 pending(곧 온다)과 unavailable(그 구간 조회수 적재본이 아예 없다)은
    **구분할 수 없다.** 구분하려면 적재 범위를 아는 쪽이 값을 넣어줘야 한다 — 후속 과제.
    ⚠️ V7 이전에 저장된 옛 행은 `views` 가 NULL 이라 pending 으로 나온다. 재적재하면 찬다.
    """
    return "complete" if views is not None else "pending"


def require_spike_source(source: str) -> str:
    """`spike.source` 로 조회할 수 있는 값인지 검사하고 그대로 돌려준다.

    ~~`replay` 만 (WP-99)~~ → `SPIKE_SOURCES` 둘 다 (WP-102).
    -99 의 제한은 `spike` 에 출처 컬럼이 없어서였고, V5 가 그걸 만들었다.

    🔴 **없는 값을 관용하지 않는다.** `'LIVE'`·`'Replay'` 같은 대소문자 어긋남을
    통과시키면 `s.source = 'LIVE'` 가 **0행**을 돌려준다 — 씨드가 비어 클러스터 0개
    스냅샷이 저장되고, 그건 writer 계약상 "완료된 빈 스냅샷" 이라 에러가 안 난다.
    화면에는 "이 시점엔 이슈가 없다" 로 보인다. 경계에서 막는 이유다.

    `spike_sink.require_source` 와 같은 검사를 같은 목록으로 한다. 쓰기(-100)와
    읽기(-102)가 같은 어휘를 봐야 한쪽만 늘었을 때 조용히 어긋나지 않는다.
    """
    if source not in SPIKE_SOURCES:
        raise ValueError(
            f"cluster 입력 source 는 {SPIKE_SOURCES} 중 하나다 (받은 값: {source!r}). "
            "V5 의 spike.source CHECK 제약·issue_cluster.source 와 같은 목록이다 — "
            "없는 값은 조회가 0행이 되어 빈 스냅샷으로 조용히 저장된다."
        )
    return source


def load_seeds_from_spike(conn, snapshot_ts: datetime, source: str) -> list[Seed]:
    """`spike` + `wiki_page` 를 조인해 **이 출처·이 시점**의 씨드를 만든다.

    🔴 **`source` 는 필수다** (~~아예 받지 않는다, -99~~ → -102). 같은 `detected_at` 에
    replay 행과 live 행이 공존할 수 있어(V5 UNIQUE 키에 source) 시각만으로는 두 출처를
    못 가른다. 안 걸면 LIVE 스냅샷에 리플레이 씨드가 섞이는데 에러가 안 난다.

    ⚠️ 기본값을 주지 않는다. 기본값이 있으면 새 호출자가 빠뜨려도 통과하고, 그 순간
    라벨과 입력이 갈린다 — `SpikeSink(conn, source=...)` 가 키워드 필수인 것과 같은 이유.

    `event_date` = `window_start` 의 날짜(UTC). 생성일 창의 중심이며, 씨드 단독
    스냅샷에서는 쓰이지 않지만(이웃이 없다) 계약대로 채운다.
    """
    require_spike_source(source)
    with conn.cursor() as cur:
        cur.execute(SELECT_SEEDS_SQL, (source, snapshot_ts))
        rows = cur.fetchall()

    seeds: list[Seed] = []
    for (_id, page_id, wiki, title, window_start, detected_at,
         edit_count, views, view_baseline, view_ratio, spike_score,
         max_rev_id) in rows:
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
            # V7 부터 spike 가 조회수 원값·기준선을 들고 있다 (WP-129).
            # ~~None 으로 두어 화면이 '미제공'으로 그린다~~ → 실제 판정값을 그대로 넘긴다.
            views=views,
            # 편집 기준선은 아직 spike 에 없다. 지어내지 않고 None 으로 둔다.
            edit_baseline=None,
            view_baseline=view_baseline,
            completeness=_completeness(views),
            # CORE 의 as-of 링크 앵커 (V9). 없으면 링크를 안 쓰고 singleton 으로 둔다 —
            # 현재 판으로 폴백하지 않는다 (WP-186).
            max_rev_id=max_rev_id,
        ))
    return seeds


def load_snapshot_times(
    conn, source: str, since: datetime | None = None, until: datetime | None = None
) -> list[datetime]:
    """**이 출처**의 스냅샷 시점들을 **오름차순**으로. `spike.detected_at` 의 고유값이다.

    🔴 `source` 는 필수다. 두 출처를 합쳐 뽑으면 한쪽에만 있는 시점까지 돌아
    빈 스냅샷이 남는다(SELECT_SNAPSHOT_TIMES_SQL 🔴).
    """
    require_spike_source(source)
    with conn.cursor() as cur:
        cur.execute(SELECT_SNAPSHOT_TIMES_SQL, (source, since, since, until, until))
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


def load_seed_titles(
    conn, source: str, snapshot_times: Sequence[datetime]
) -> dict[str, set[str]]:
    """여러 시점의 씨드 제목을 wiki 별로 모은다. Clickstream 1회 순회용 입력."""
    require_spike_source(source)
    if not snapshot_times:
        return {}
    by_wiki: dict[str, set[str]] = {}
    with conn.cursor() as cur:
        cur.execute(SELECT_SEED_TITLES_SQL, (source, list(snapshot_times)))
        for wiki, title in cur.fetchall():
            by_wiki.setdefault(wiki, set()).add(title)
    return by_wiki


@dataclass
class NeighborStats:
    """이웃 배선이 각 단계에서 몇 개를 잃었는지. 조용히 0 이 되는 것을 막는다.

    🔴 **`creation_missing` 과 `window_rejected` 를 합치지 않는다.** 앞은 인덱스에
    근거가 없는 것이고 뒤는 근거를 보고 탈락시킨 것이다. 합치면 인덱스 구멍이
    게이트 판정처럼 보여서, 커버리지가 무너져도 "규칙대로 걸렀다" 로 읽힌다.
    """
    seeds: int = 0
    seeds_in_dump: int = 0        # Clickstream 덤프에 씨드 제목이 있던 수
    candidates: int = 0           # 이웃 후보 (씨드-이웃 쌍)
    creation_resolved: int = 0
    creation_missing: int = 0
    window_rejected: int = 0      # 생성일은 알지만 창 밖
    # 창을 떨어진 뒤 재급증(비-씨드) 게이트에서 갈린 수 (WP-145).
    # 🔴 `resurgence_missing` 을 `resurgence_rejected` 와 합치지 않는다 —
    #    위 🔴 와 같은 이유다. 편집 인덱스에 제목이 없는 것과, 세어 보고 미달인
    #    것은 다른 사실이다. 합치면 덤프 구멍이 "규칙대로 걸렀다" 로 읽힌다.
    resurgence_missing: int = 0   # 편집 인덱스에 제목 없음
    resurgence_rejected: int = 0  # 수치는 있는데 게이트 미달
    resurgence_passed: int = 0
    gate_passed: int = 0
    page_resolved: int = 0
    months: dict[str, int] = dataclass_field(default_factory=dict)

    def merge(self, other: "NeighborStats") -> None:
        self.seeds += other.seeds
        self.seeds_in_dump += other.seeds_in_dump
        self.candidates += other.candidates
        self.creation_resolved += other.creation_resolved
        self.creation_missing += other.creation_missing
        self.window_rejected += other.window_rejected
        self.resurgence_missing += other.resurgence_missing
        self.resurgence_rejected += other.resurgence_rejected
        self.resurgence_passed += other.resurgence_passed
        self.gate_passed += other.gate_passed
        self.page_resolved += other.page_resolved
        for month, count in other.months.items():
            self.months[month] = self.months.get(month, 0) + count


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
    created_of_page: dict[int, datetime | None],
    resurgence_of_title: dict[str, EditResurgence] | None = None,
) -> list[Neighbor]:
    """NeighborRef 를 cluster.snapshot.Neighbor 로 변환한다.

    page_of_title: 이웃 제목 → (page_id, wiki)   — wiki_page 조회(미배선)
    created_of_page: page_id → 생성 시각(UTC)      — `batch/page_creation` (-115)
    resurgence_of_title: 제목 → 재급증 수치 — `batch/page_edit_daily` (-145)
    두 소스가 아직 없으면 그 이웃은 건너뛴다(생성 시각 미상은 게이트가 어차피 탈락시킨다).

    재급증 수치는 **창을 떨어진 뒤 2차 관문을 통과한 이웃에만** 있다. 창을 통과한
    추가 씨드에는 없고, 없는 것이 정상이다 — `snapshot.py` 가 창을 먼저 보므로
    그 경로에서는 읽히지 않는다.
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
            resurgence=(resurgence_of_title or {}).get(ref.title),
        ))
    return out


def resurgence_for(
    days: dict[date, int] | None,
    event_date: date,
    window_days: int,
    *,
    snapshot_date: date,
    created_at: datetime | None = None,
    coverage: tuple[date | None, date | None] = (None, None),
) -> EditResurgence | None:
    """한 이웃의 사건기간·기준기간 편집 수를 만든다 (WP-145).

    🔴 **사건기간은 스냅샷에서 끝난다. 미래로 열어 두지 않는다.**
        ~~사건일 ±window_days~~ → **[사건일-window_days, 관측 가능한 끝)** 로 정정
        (2026-09-20, 사용자 지적으로 발견). 앞의 방식은 사건기간 끝이 사건 31일
        뒤라, 게이트의 시점 상한(`event_end <= snapshot_ts`)에 걸려 **사건 31일이
        지나기 전에는 어떤 스냅샷도 통과하지 못했다.** 실시간 판정이 통째로 죽는다.
        내 단위 테스트는 `snapshot_ts` 를 먼 미래로 잡아 둬서 이걸 못 잡았다 —
        실수를 그대로 검증하는 테스트였다.

    관측 가능한 끝 = `min(사건일+window_days+1, 스냅샷 날짜, 커버리지 끝+1)`.
    셋 중 가장 이른 것이다. 스냅샷이 사건 직후면 짧고, 시간이 지나면 창이 다 찬다.

    기준기간 = 사건기간 **직전** 같은 길이. 길이를 사건기간에서 받아 계산하므로
    스냅샷이 일러 사건기간이 짧아지면 기준기간도 같이 짧아진다 — "지금까지 본
    만큼" 과 "그 직전 같은 만큼" 을 비교하는 것이 -77 의 취지다.

    ⚠️ **기준기간이 커버리지 시작보다 앞서면 판정하지 않는다.** 기준선이 과소
        계수되면 비율이 **부풀어** 배경 문서가 재급증으로 통과한다 — 사건기간이
        잘릴 때와 반대로, 틀리는 방향이 오탐이라 더 위험하다.

    ⚠️ `days` 가 None(편집 인덱스에 제목 없음)이면 None 을 돌려준다. 0 으로 채우지
        않는다 — 기준기간이 0 이면 비율이 무한대가 되어 덤프 구멍이 "재급증" 으로
        위장된다(`batch/page_edit_daily` 모듈 ⚠️).

    날짜 경계는 `[start, end)` 다. 반환 datetime 은 자정 UTC 다.
    """
    if days is None:
        return None

    first_day, last_day = coverage
    span = timedelta(days=window_days)

    event_start = event_date - span
    ends = [event_date + span + timedelta(days=1), snapshot_date]
    if last_day is not None:
        ends.append(last_day + timedelta(days=1))
    event_end = min(ends)
    if event_end <= event_start:
        return None                      # 아직 볼 수 있는 구간이 없다
    # 🔴 **사건기간이 사건일을 담지 못하면 판정하지 않는다.** 커버리지나 스냅샷이
    #    사건일보다 이르면 창이 사건 **이전** 구간만 담는데, 그걸로 낸 비율은
    #    "사건 때문에 들썩였나" 가 아니라 "사건 전에 들썩였나" 를 잰 값이다.
    #    통과·탈락 어느 쪽이 나와도 근거가 없다.
    if event_end <= event_date:
        return None

    length = event_end - event_start
    baseline_start = event_start - length
    baseline_end = event_start
    if first_day is not None and baseline_start < first_day:
        return None                      # 기준선이 잘린다 — 위 ⚠️ (오탐 방향)
    # 🔴 **기준기간 내내 존재하지 않았으면 판정하지 않는다** (2026-09-20 실측).
    #    문서가 그때 없었으면 기준 편집이 0 인데, 그건 "조용했다" 가 아니라
    #    "없었다" 다. 실측에서 기준 0 인 3,546개 중 67.5% 가 그 이전에도 편집 0 —
    #    사건 때문에 새로 생긴 문서였다(`2026 Colombia earthquake` 등).
    #    그런 문서는 비-씨드(배경 재조명)가 아니라 추가 씨드 쪽이고, 생성일 창이
    #    ±30일이라 31~61일 전에 생긴 것만 여기로 샌다. 그 구멍을 막는다.
    if created_at is not None and created_at.date() >= baseline_start:
        return None

    def _at(day: date) -> datetime:
        return datetime(day.year, day.month, day.day, tzinfo=timezone.utc)

    return EditResurgence(
        event_edits=sum_days(days, event_start, event_end),
        baseline_edits=sum_days(days, baseline_start, baseline_end),
        event_start=_at(event_start),
        event_end=_at(event_end),
        baseline_start=_at(baseline_start),
        baseline_end=_at(baseline_end),
    )


def neighbors_for_snapshot(
    conn,
    seeds: Sequence[Seed],
    refs_by_title: dict[str, list[NeighborRef]],
    created_of_title: dict[str, datetime],
    month: str,
    *,
    creation_window_days: int,
    stats: NeighborStats,
    snapshot_ts: datetime | None = None,
    edit_days_of_title: dict[str, dict[date, int]] | None = None,
    edit_coverage: tuple[date | None, date | None] = (None, None),
    resurgence_ratio: float = DEFAULT_RESURGENCE_RATIO,
    resurgence_min_edits: int = DEFAULT_RESURGENCE_MIN_EDITS,
) -> dict[int, list[Neighbor]]:
    """한 시점의 씨드들에 이웃을 붙인다. `build_snapshot(neighbors=...)` 입력 형태.

    순서가 중요하다: **창 통과 → page_id 등록** 이다. 뒤집으면 멤버가 될 일 없는
    이웃 수십만 건이 `wiki_page` 에 등록된다.

    🔴 창 판정은 `snapshot._within_creation_window` 를 **그대로 부른다.** 여기에 같은
    조건을 다시 쓰면 게이트가 두 벌이 되고, 한쪽만 바뀌어도 에러 없이 결과가 갈린다.
    재급증 판정(`_passes_resurgence`)도 같은 이유로 그대로 부른다.

    게이트 둘은 배타적이고 순서가 있다 (WP-145). 창을 통과하면 추가 씨드로
    끝내고, **떨어진 후보만** 재급증으로 내린다. 여기서 한 번 거르는 이유는 위의
    page_id 등록 규칙 때문이다 — 재급증까지 떨어진 후보를 넘기면 멤버가 될 일 없는
    문서가 `wiki_page` 에 쌓인다. `snapshot.py` 가 최종 판정을 다시 하므로 이 선별은
    같은 함수를 부르는 사전 통과일 뿐이고 규칙을 새로 만들지 않는다.

    `edit_days_of_title` 이 None 이면 재급증 경로 자체를 돌지 않는다 — 편집 인덱스를
    안 준 호출자(기존 배선·테스트)는 씨드 전용 동작 그대로다.
    """
    kept: dict[int, list[NeighborRef]] = {}
    wanted: dict[str, set[str]] = {}
    # 통과한 후보의 재급증 수치. 제목 단위라 여러 씨드에 걸쳐도 한 번만 잰다 —
    # 사건일이 씨드마다 달라 값이 갈릴 수 있지만, 같은 스냅샷 안에서 같은 제목을
    # 두 번 계산하지 않기 위해 마지막 승자를 쓴다(멤버는 클러스터별로 들어간다).
    resurgence_of_title: dict[str, EditResurgence] = {}

    for seed in seeds:
        stats.seeds += 1
        refs = refs_by_title.get(seed.title) or []
        if refs:
            stats.seeds_in_dump += 1
        survivors: list[NeighborRef] = []
        for ref in refs:
            stats.candidates += 1
            created = created_of_title.get(ref.title)
            if created is None:
                stats.creation_missing += 1
                continue
            stats.creation_resolved += 1
            if not _within_creation_window(created, seed.event_date, creation_window_days):
                stats.window_rejected += 1
                if edit_days_of_title is None or snapshot_ts is None:
                    continue
                # 2차 관문 — 오래전 문서가 사건으로 재조명됐는가 (WP-77).
                spike = resurgence_for(edit_days_of_title.get(ref.title),
                                       seed.event_date, creation_window_days,
                                       snapshot_date=snapshot_ts.date(),
                                       created_at=created,
                                       coverage=edit_coverage)
                if spike is None:
                    stats.resurgence_missing += 1
                    continue
                if not _passes_resurgence(spike, snapshot_ts,
                                          min_ratio=resurgence_ratio,
                                          min_edits=resurgence_min_edits):
                    stats.resurgence_rejected += 1
                    continue
                stats.resurgence_passed += 1
                resurgence_of_title[ref.title] = spike
                survivors.append(ref)
                continue
            stats.gate_passed += 1
            survivors.append(ref)
        kept[seed.page_id] = survivors
        if survivors:
            wanted.setdefault(seed.wiki, set()).update(r.title for r in survivors)

    # page_id 해석 — wiki 당 왕복 2회. 씨드마다 조회하지 않는다.
    page_of_title: dict[str, tuple[int, str]] = {}
    created_of_page: dict[int, datetime | None] = {}
    for wiki, titles in wanted.items():
        for title, page_id in load_pages_by_title(conn, wiki, titles).items():
            page_of_title[title] = (page_id, wiki)
            created_of_page[page_id] = created_of_title.get(title)
    stats.page_resolved += len(page_of_title)
    stats.months[month] = stats.months.get(month, 0) + 1

    return {
        page_id: build_neighbor_inputs(refs, month, page_of_title, created_of_page,
                                       resurgence_of_title)
        for page_id, refs in kept.items()
    }


class MonthlyNeighborSource:
    """Clickstream 월 덤프를 **월당 한 번만** 훑어 시점별 이웃을 공급한다.

    `build_snapshot_at(neighbor_source=...)` 로 넘긴다. 시점이 1,400개가 넘는데
    덤프가 수천만 행이라 시점마다 다시 읽으면 끝나지 않는다 — `prepare()` 가 필요한
    월을 미리 정해 한 번씩 읽고, 시점마다는 메모리의 결과만 쓴다.

    ⚠️ 적재본이 없는 월은 **막는다.** 조용히 빈 이웃을 돌려주면 "이웃이 없는 시점" 과
    "덤프를 안 받은 월" 이 구분되지 않아, 1-멤버 클러스터가 정상 산출물로 저장된다.
    """

    def __init__(
        self,
        shards_root: str | Path,
        creation_index: str | Path,
        *,
        creation_window_days: int = DEFAULT_CREATION_WINDOW_DAYS,
        edit_index: str | Path | Sequence[str | Path] | None = None,
    ) -> None:
        self.shards_root = Path(shards_root)
        self.creation_index = Path(creation_index)
        self.creation_window_days = creation_window_days
        # 비-씨드 재급증 인덱스(`batch/page_edit_daily`, -145). **선택이다** —
        # 주지 않으면 창 게이트만 돌아 추가 씨드만 나온다. 월 덤프가 늦게 공개돼
        # LIVE 최신 구간에는 아직 못 쓰기 때문에 필수로 두지 않는다.
        # 월별 적재본 여러 개를 받는다 (WP-145 — 한 번에 여러 달을
        # 훑으면 적재 쪽 메모리가 터진다). 하나만 줘도 된다.
        self.edit_index = (
            [Path(edit_index)] if isinstance(edit_index, (str, Path))
            else [Path(d) for d in edit_index] if edit_index else None)
        # 적재본이 실제로 담은 마지막 날짜. 매니페스트에 없으면 None 이고, 그때는
        # 경계를 모르는 채로 판정한다 — 옛 적재본은 다시 만드는 편이 낫다.
        self.edit_coverage = (
            coverage_span(self.edit_index) if self.edit_index else (None, None))
        self.stats = NeighborStats()
        # (wiki, month) -> 씨드 제목 -> 이웃. 근거 월이 wiki 마다 다를 수 있어 키가 쌍이다.
        self._refs: dict[tuple[str, str], dict[str, list[NeighborRef]]] = {}
        self._created: dict[str, datetime] = {}
        self._edit_days: dict[str, dict[date, int]] = {}
        self._month_of: dict[tuple[str, datetime], str] = {}

    def month_for(self, wiki: str, snapshot_ts: datetime) -> str:
        """이 스냅샷이 쓸 근거 월. `select_completed_month` 하나만 판단한다.

        🔴 **월 선택 규칙을 이 모듈에 두지 않는다** (2026-09-18, -115 + develop 머지).
        ~~`clickstream_month_for(previous/event)`~~ -> `batch.clickstream.select_completed_month`.
        직전 월 우선 · 미공개·검증 실패 시 최신 완료본 폴백 · manifest 검증이 전부
        그쪽 계약이다. 규칙이 두 벌이면 한쪽만 바뀌어도 에러 없이 결과가 갈린다.
        `snapshot._is_completed_clickstream_month` 는 그 위의 이중 방어다.
        """
        key = (wiki, snapshot_ts)
        if key not in self._month_of:
            month, _path = select_completed_month(self.shards_root, wiki, snapshot_ts)
            self._month_of[key] = month
        return self._month_of[key]

    def shards_dir(self, wiki: str, month: str) -> Path:
        """`clickstream_ingest` 출력 규칙: `{out}/{wiki}/{month}`."""
        return self.shards_root / wiki / month

    def prepare(self, conn, source: str, snapshot_times: Sequence[datetime]) -> None:
        """필요한 (wiki, 월) 을 한 번씩 읽고 생성 시각까지 붙인다."""
        # 어떤 wiki 가 있는지 먼저 안다 — 근거 월이 wiki 마다 다를 수 있다.
        wikis = sorted(load_seed_titles(conn, source, list(snapshot_times)))

        # 🔴 **훑기 전에 전부 고른다.** 뒤에서 고르면 앞 월을 수천만 행 다 읽고 나서
        #    마지막 월에서 죽는다 — 실제로 61일 구간 끝의 경계 스냅샷 1개 때문에
        #    2개월 스캔을 버렸다(2026-09-17). 실패는 빨라야 한다.
        #    완료본이 없으면 `select_completed_month` 가 여기서 FileNotFoundError 를 낸다.
        groups: dict[tuple[str, str], list[datetime]] = {}
        for wiki in wikis:
            for ts in snapshot_times:
                groups.setdefault((wiki, self.month_for(wiki, ts)), []).append(ts)

        all_titles: set[str] = set()
        for (wiki, month), times in sorted(groups.items()):
            titles = load_seed_titles(conn, source, times).get(wiki, set())
            found = neighbors_for(read_shards(self.shards_dir(wiki, month)), titles)
            month_refs: dict[str, list[NeighborRef]] = {}
            for seed_title, refs in found.items():
                if refs:
                    month_refs[seed_title] = refs
                    all_titles.update(r.title for r in refs)
            self._refs[(wiki, month)] = month_refs
            print(f"  clickstream {wiki} {month}: 씨드 {len(titles):,}개 중 "
                  f"이웃 보유 {len(month_refs):,}개")

        self._created = load_creation_dates(self.creation_index, all_titles)
        if self.edit_index is not None:
            # 창을 떨어질 후보가 대다수라 후보 전체를 한 번에 읽는다. 씨드마다
            # 사건일이 달라 고정 구간으로 미리 합칠 수 없어 날짜별 원장을 든다.
            self._edit_days = edit_days_for(self.edit_index, all_titles)
            first, last = self.edit_coverage
            print(f"  편집 인덱스 데이터 구간: {first or '미상'} ~ {last or '미상'}"
                  " (사건·기준기간이 이 밖으로 나가면 판정하지 않는다)")
            print(f"  편집 인덱스: 후보 제목 {len(all_titles):,}개 중 "
                  f"{len(self._edit_days):,}개 resolve "
                  f"({100.0 * len(self._edit_days) / len(all_titles):.1f}%)"
                  if all_titles else "  편집 인덱스: 후보 제목 0개")
        print(f"  생성일: 후보 제목 {len(all_titles):,}개 중 "
              f"{len(self._created):,}개 resolve "
              f"({100.0 * len(self._created) / len(all_titles):.1f}%)"
              if all_titles else "  생성일: 후보 제목 0개")

    def __call__(self, conn, snapshot_ts: datetime, seeds: Sequence[Seed]):
        by_wiki: dict[str, list[Seed]] = {}
        for seed in seeds:
            by_wiki.setdefault(seed.wiki, []).append(seed)

        out: dict[int, list[Neighbor]] = {}
        for wiki, wiki_seeds in sorted(by_wiki.items()):
            month = self.month_for(wiki, snapshot_ts)
            out.update(neighbors_for_snapshot(
                conn, wiki_seeds, self._refs.get((wiki, month), {}), self._created,
                month, creation_window_days=self.creation_window_days,
                stats=self.stats, snapshot_ts=snapshot_ts,
                edit_days_of_title=self._edit_days if self.edit_index else None,
                edit_coverage=self.edit_coverage))
        return out


def load_creation_dates(
    index_dir: str | Path, titles: Iterable[str]
) -> dict[str, datetime]:
    """`batch/page_creation` 인덱스에서 이웃 제목들의 생성 시각(UTC)을 읽는다.

    ~~`raise NotImplementedError` 골격~~ → 배선됨 (WP-115).
    ~~`page_ids` 로 받는다~~ → **제목으로 받는다.** 소스(mediawiki_history)가 제목
    기준이고, 이웃은 page_id 가 아직 없을 수 있다(창을 통과해야 등록한다).

    ⚠️ **없는 제목은 키가 없다.** "창 밖" 과 "생성일 미상" 은 다른 사실이다 —
    게이트는 둘 다 탈락시키지만(`_within_creation_window` 가 None 을 False 로 본다),
    커버리지를 안 재면 인덱스 구멍이 게이트 판정으로 위장된다.
    """
    return creation_dates_for(index_dir, titles)


def load_pages_by_title(
    conn, wiki: str, titles: Iterable[str], *, register_missing: bool = True
) -> dict[str, int]:
    """이웃 제목 → `wiki_page.id`. 없으면 등록하고 다시 읽는다.

    ~~docstring 속 의사코드, 실제 함수 없음~~ → 구현됨 (WP-115).

    🔴 **등록이 필요하다.** `cluster_member.page_id` 가 FK 라 행이 없으면 멤버로
    저장할 수 없는데, 사건 직후에 생긴 추가 씨드 문서는 `wiki_page` 에 없다 — 그 테이블은
    warm-up 기준선(2024-08)과 급증 문서로만 채워져 있기 때문이다. 등록을 안 하면
    **진짜 멤버가 조용히 전부 사라진다**(FK 오류도 안 난다 — 그 전에 걸러지므로).

    🔴 **호출자는 창을 통과한 후보만 넘긴다.** 이웃 전체를 넘기면 멤버가 될 일 없는
    문서 수십만 건이 `wiki_page` 에 쌓인다. 거르는 기준은 이 모듈이 만들지 않고
    `snapshot._within_creation_window` 를 그대로 부른다 — 규칙이 두 벌이 되면 안 된다.

    🔴 **제목은 canonical(공백형)이어야 한다.** `(wiki, title)` 이 자연키라 표기가
    흔들리면 한 문서가 두 행이 된다(명세 §5.1). Clickstream 적재본은 이미
    `canonical_title` 을 통과한 값이라 여기서 다시 바꾸지 않는다 — 집계가 끝난 뒤
    문자열만 바꾸면 이미 키가 갈라진 뒤다.
    """
    wanted = sorted(set(titles))
    if not wanted:
        return {}

    with conn.cursor() as cur:
        cur.execute(SELECT_PAGES_BY_TITLE_SQL, (wiki, wanted))
        found = {title: page_id for title, page_id in cur.fetchall()}

        missing = [t for t in wanted if t not in found]
        if missing and register_missing:
            cur.executemany(INSERT_PAGES_SQL, [(wiki, t) for t in missing])
            cur.execute(SELECT_PAGES_BY_TITLE_SQL, (wiki, missing))
            found.update({title: page_id for title, page_id in cur.fetchall()})

    return found


# --- CORE as-of 링크 ---------------------------------------------------------

def load_root_links(
    conn,
    seeds: Sequence[Seed],
    *,
    fetcher=None,
    log=None,
) -> dict[int, set[str]]:
    """CORE 입력 — root 별 as-of strict 아웃링크 집합 (WP-186).

    `spike.max_rev_id` 를 앵커로 `page_asof_links`(V11) 캐시를 먼저 보고, 없는 것만
    받아 캐시에 넣는다. revision 단위 캐시라 만료가 없다.

    🔴 **`max_rev_id` 가 없는 root 는 결과에서 아예 뺀다.** 호출자가 빈 집합으로 읽어
       singleton 으로 둔다 — 현재 판 링크로 폴백하면 그 순간 미래 정보가 과거 스냅샷에
       섞인다. replay 든 LIVE 든 같은 규칙이다.

    ⚠️ **`fetcher=None` 이면 캐시만 쓴다.** 기본을 이렇게 둔 이유는 리플레이 대량
       재계산이 실수로 수만 건을 받는 것을 막기 위해서다 — 수집은 호출자가 켠다.
       캐시가 비어 있으면 스냅샷이 통째로 singleton 이 되므로 그 경우 경고를 찍는다.
    """
    anchored = [s for s in seeds if s.max_rev_id is not None]
    if not anchored:
        return {}
    by_rev: dict[int, list[Seed]] = {}
    for seed in anchored:
        by_rev.setdefault(int(seed.max_rev_id), []).append(seed)

    cached = asof_links.load_cached(conn, list(by_rev))
    missing = [rev for rev in by_rev if rev not in cached]
    if missing and fetcher is not None:
        fetched = fetcher.fetch_many(missing, log=log)
        asof_links.store(conn, [
            (rev, by_rev[rev][0].wiki, by_rev[rev][0].title, links, error)
            for rev, (_title, links, error) in fetched.items()
        ])
        for rev, (_title, links, error) in fetched.items():
            if not error:
                cached[rev] = set(links)
    elif missing and log:
        log(f"⚠️ as-of 링크 캐시 미보유 {len(missing)}건 — 그 root 는 singleton 이 된다")

    out: dict[int, set[str]] = {}
    for rev, group in by_rev.items():
        if rev in cached:
            for seed in group:
                out[seed.page_id] = cached[rev]
    return out


# --- 런타임 -----------------------------------------------------------------

def build_snapshot_at(
    conn,
    snapshot_ts: datetime,
    source: str,
    *,
    neighbors: dict[int, Sequence[Neighbor]] | None = None,
    neighbor_source=None,
    root_grouping: bool = True,
    expansion: bool = False,
    link_fetcher=None,
    log=None,
) -> Snapshot:
    """한 시점의 스냅샷을 생산한다(저장 안 함). 로직은 전부 -75·-186 자산이다.

    `root_grouping=True`(기본) 면 CORE 로 root 를 묶는다. `expansion=False`(기본) 면
    멤버는 root 뿐이다 — 현재 MVP 정본 경로다(WP-186).

    🔴 **`source` 하나가 입력 필터이자 산출물 라벨이다.** 읽는 씨드(`spike.source`),
    이전 감지 이력(`issue_cluster.source`), 붙는 라벨(`Snapshot.source`) 이 같은 값에서
    나온다 — 따로 받으면 그 둘이 갈릴 수 있고, 갈린 결과가 -99 가 막던 거짓 라벨링이다.

    ~~`neighbors` 를 안 주면 씨드 단독이다~~ → `neighbor_source` 가 배선됐다
    (WP-115). 둘 다 안 주면 여전히 씨드 단독이고, 그건 계약상 유효하다.

    `neighbor_source(conn, snapshot_ts, seeds)` 는 씨드를 받아 이웃을 돌려주는
    호출 가능 객체다(`MonthlyNeighborSource`). **씨드를 먼저 읽어야 이웃을 구할 수
    있어서** 인자로 미리 받지 않고 여기서 부른다 — 호출자가 씨드를 따로 한 번 더
    읽으면 같은 질의가 두 번 나가고, 두 결과가 갈릴 여지가 생긴다.
    """
    require_spike_source(source)
    seeds = load_seeds_from_spike(conn, snapshot_ts, source)
    if expansion and neighbors is None and neighbor_source is not None:
        neighbors = neighbor_source(conn, snapshot_ts, seeds)
    root_links = (load_root_links(conn, seeds, fetcher=link_fetcher, log=log)
                  if root_grouping else None)
    return build_snapshot(
        snapshot_ts, source, seeds, neighbors or {},
        prior_first_detected=load_prior_first_detected(conn, source),
        root_links=root_links,
        expansion=expansion,
    )


def run(
    conn,
    source: str,
    *,
    snapshot_times: Sequence[datetime],
    dry_run: bool = False,
    neighbor_source=None,
    root_grouping: bool = True,
    expansion: bool = False,
    link_fetcher=None,
    log=None,
) -> list[Snapshot]:
    """시점들을 순서대로 생산하고 저장한다. 커밋은 호출자 책임.

    🔴 `snapshot_times` 는 **오름차순**이어야 한다(모듈 독스트링). `load_snapshot_times`
    가 그렇게 돌려준다.

    `source` 는 `SPIKE_SOURCES` 안의 값이어야 한다 — 시점이 0개여도 먼저 막는다.
    늦게 막으면 빈 목록일 때만 통과해 버려서, 나중에 데이터가 생겼을 때 갑자기 실패한다.

    ⚠️ `snapshot_times` 는 **같은 `source` 로 뽑은 것**이어야 한다. 다른 출처의 시점을
    넘기면 그 시점엔 이 출처의 씨드가 없어 `cluster_count=0` 스냅샷이 저장된다 —
    유효한 산출물이라 에러가 안 난다. `load_snapshot_times(conn, source)` 를 쓴다.
    """
    require_spike_source(source)
    if expansion and neighbor_source is not None:
        # 월 덤프 순회는 여기서 한 번에 끝낸다 — 시점 루프 안에서 하면 월당 수천 번이다.
        neighbor_source.prepare(conn, source, snapshot_times)
    produced: list[Snapshot] = []
    for snapshot_ts in snapshot_times:
        snapshot = build_snapshot_at(
            conn, snapshot_ts, source, neighbor_source=neighbor_source,
            root_grouping=root_grouping, expansion=expansion,
            link_fetcher=link_fetcher, log=log)
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
        description="spike → 클러스터 스냅샷 생산·적재 (WP-102)")
    p.add_argument("--dsn", default=os.environ.get("DATABASE_URL", ""),
                   help="PostgreSQL DSN (기본: $DATABASE_URL)")
    # 🔴 **기본값을 주지 않는다** (~~default=replay, -99~~ → required, -102).
    #    기본값이 있으면 `--source` 를 빠뜨린 LIVE 운영이 **에러 없이 리플레이 스냅샷을
    #    다시 만든다**. V5 가 `spike.source` 에서 DEFAULT 를 뗀 것과 같은 이유다.
    #    choices 로 argparse 가 먼저 거절하게 둔다 — 오타는 0행 조회로 조용히 끝난다.
    p.add_argument("--source", required=True, choices=SPIKE_SOURCES,
                   help="읽을 spike.source 이자 붙일 issue_cluster.source 라벨. "
                        "입력 필터와 출력 라벨이 같은 값이다")
    p.add_argument("--snapshot-ts", type=_parse_ts,
                   help="이 시점 하나만 생산한다. 없으면 spike.detected_at 고유값 전부")
    p.add_argument("--since", type=_parse_ts, help="시점 범위 시작(포함)")
    p.add_argument("--until", type=_parse_ts, help="시점 범위 끝(포함)")
    p.add_argument("--dry-run", action="store_true", help="저장 없이 생산만")

    # --- CORE (WP-186, MVP 정본) -------------------------------------
    # 🔴 **기본이 켜짐이다.** 이게 지금 제품 규칙이다.
    p.add_argument("--no-root-grouping", dest="root_grouping", action="store_false",
                   help="CORE grouping 을 끈다 — root 1개 = 클러스터 1개(-186 이전 동작). "
                        "비상용이며 평소에 쓰지 않는다")
    # 🔴 **as-of 링크는 캐시가 기본이다.** 수집은 명시적으로 켠다 — 리플레이 한 판이
    #    root 수만큼(실측 22,080) 요청을 낼 수 있어서, 실수로 켜지면 위키미디어를
    #    그만큼 때린다. 캐시가 비면 스냅샷이 통째로 singleton 이 되고 경고가 찍힌다.
    p.add_argument("--fetch-links", action="store_true",
                   help="캐시에 없는 as-of 링크를 위키미디어에서 받아 V11 캐시에 넣는다 "
                        "(기본: 캐시만 사용). CONTACT_EMAIL 이 필요하다")
    p.add_argument("--link-workers", type=int, default=4,
                   help="--fetch-links 동시 요청 수 (기본 4)")

    # --- LEGACY expansion (기본 OFF, WP-186) --------------------------
    # 🔴 켜면 CORE component 의 각 root 에 Clickstream 이웃이 붙는다. PoC 5 에서 검증한
    #    분포가 보장되지 않고, non-root 멤버는 window_start/end 가 없어 프론트 계약
    #    (`contract.js` 의 metric window)에 걸려 **펄스맵이 통째로 안 그려진다.**
    p.add_argument("--expansion", action="store_true",
                   help="legacy Clickstream/생성일/재급증 멤버 확장을 켠다 "
                        "(기본 꺼짐 — CORE 정본은 root 멤버만 쓴다)")
    # Clickstream 이웃(추가 씨드) 배선 — WP-115. --expansion 과 함께 쓴다.
    # 🔴 **기본이 꺼짐이다.** 적재본 없이 돌던 기존 운영(-109)이 이 변경으로
    #    갑자기 FileNotFoundError 를 내면 안 된다. 주면 켜고, 안 주면 씨드 단독이다.
    p.add_argument("--clickstream-root", default=os.environ.get("CLICKSTREAM_OUT", ""),
                   help="clickstream_ingest 출력 루트. 주면 추가 씨드 이웃을 배선한다 "
                        "(기본 $CLICKSTREAM_OUT, 없으면 씨드 단독)")
    p.add_argument("--creation-index",
                   default=os.environ.get("PAGE_CREATION_OUT", ""),
                   help="batch.page_creation 인덱스 디렉터리. --clickstream-root 와 "
                        "함께 필요하다. 생성일 없이는 창 게이트가 전부 탈락시킨다")
    # 🔴 **선택이다.** 안 주면 창 게이트만 돌아 추가 씨드만 나온다 — 비-씨드 재급증
    #    멤버가 안 생길 뿐 조용히 깨지지 않는다. 월 덤프 공개가 늦어 LIVE 최신
    #    구간에는 아직 못 쓰기 때문에 필수로 두지 않는다 (WP-145).
    p.add_argument("--edit-index", action="append", default=None,
                   help="batch.page_edit_daily 인덱스 디렉터리. 주면 비-씨드 재급증 "
                        "멤버(WP-77)를 배선한다. 없으면 추가 씨드만. "
                        "적재가 월별로 쪼개지므로 **여러 번 줄 수 있다** — 빠진 달이 "
                        "있으면 기동 때 CoverageGap 으로 막는다")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if not args.dsn:
        print("DSN 이 없다. --dsn 또는 $DATABASE_URL 을 준다.", file=sys.stderr)
        return 2
    if args.snapshot_ts and (args.since or args.until):
        print("--snapshot-ts 와 --since/--until 은 같이 못 쓴다.", file=sys.stderr)
        return 2
    # 🔴 expansion 을 안 켠 채 이웃 인자를 주면 막는다. 그냥 무시하면 "붙였는데 왜
    #    멤버가 없지" 로 한참을 헤맨다 — -186 에서 기본이 꺼짐으로 바뀐 걸 모르면
    #    조용히 씨드 단독 결과만 나온다.
    if args.clickstream_root and not args.expansion:
        print("--clickstream-root 는 --expansion 과 함께 준다. CORE 정본(-186)은 "
              "root 멤버만 쓰므로 expansion 없이는 이웃이 붙지 않는다.", file=sys.stderr)
        return 2
    # 🔴 한쪽만 주면 막는다. Clickstream 만 주면 생성일이 전부 미상이 되어 창 게이트가
    #    이웃을 **한 건도** 통과시키지 않는데, 그건 "이웃이 없다" 와 구분되지 않는다.
    if bool(args.clickstream_root) != bool(args.creation_index):
        print("--clickstream-root 와 --creation-index 는 같이 준다. "
              "생성일 없이는 창 게이트가 이웃을 전부 탈락시켜 씨드 단독과 같아진다.",
              file=sys.stderr)
        return 2
    import psycopg     # 이 CLI 에서만 필요 — 순수 로직은 드라이버 없이도 돈다

    with psycopg.connect(args.dsn) as conn:
        times = ([args.snapshot_ts] if args.snapshot_ts
                 else load_snapshot_times(conn, args.source, args.since, args.until))
        if not times:
            print(f"생산할 시점이 없다 — source={args.source} 인 spike 행이 "
                  "없거나 범위 밖이다.")
            return 1

        print(f"시점 {len(times)}개 ({times[0].isoformat()} ~ {times[-1].isoformat()}) "
              f"source={args.source}{' [dry-run]' if args.dry_run else ''}")

        link_fetcher = None
        if args.fetch_links:
            from batch.ingest import user_agent
            link_fetcher = asof_links.WikipediaLinkFetcher(
                user_agent=user_agent(), workers=args.link_workers)
        print("CORE grouping: "
              + ("켬 (as-of strict link → component → focus 0.005 → D2)"
                 if args.root_grouping else "끔 — root 1개 = 클러스터 1개")
              + f" / as-of 링크 {'수집+캐시' if args.fetch_links else '캐시만'}"
              + f" / expansion {'켬(legacy)' if args.expansion else '끔'}")

        neighbor_source = None
        if args.clickstream_root:
            neighbor_source = MonthlyNeighborSource(
                args.clickstream_root, args.creation_index,
                edit_index=args.edit_index or None)
            print(f"이웃 배선: clickstream={args.clickstream_root} "
                  "(근거 월은 select_completed_month 가 고른다)")
            print("  비-씨드 재급증: "
                  + (", ".join(args.edit_index) if args.edit_index
                     else "없음 — 추가 씨드만 배선한다"))

        snapshots = run(conn, args.source, snapshot_times=times,
                        dry_run=args.dry_run, neighbor_source=neighbor_source,
                        root_grouping=args.root_grouping, expansion=args.expansion,
                        link_fetcher=link_fetcher,
                        log=lambda m: print(m, file=sys.stderr, flush=True))
        if not args.dry_run:
            conn.commit()

    if neighbor_source is not None:
        s = neighbor_source.stats
        # 🔴 단계별로 따로 적는다. 합치면 "인덱스에 없음" 이 "규칙대로 탈락" 으로 읽힌다.
        print(f"이웃 배선 집계: 씨드 {s.seeds:,} (덤프에 있던 씨드 {s.seeds_in_dump:,}) / "
              f"후보 {s.candidates:,} / 생성일 resolve {s.creation_resolved:,} "
              f"미상 {s.creation_missing:,} / 창 탈락 {s.window_rejected:,} / "
              f"창 통과(추가 씨드) {s.gate_passed:,} / page_id 해석 {s.page_resolved:,}")
        # 재급증(비-씨드)은 창을 **떨어진** 후보에만 도는 별개 관문이라 따로 적는다.
        # 안 찍으면 "창 통과 0" 만 보이고 비-씨드가 어디서 왔는지 알 수 없다.
        print(f"  비-씨드 재급증: 통과 {s.resurgence_passed:,} / "
              f"미달 {s.resurgence_rejected:,} / 미상 {s.resurgence_missing:,} "
              f"(미상 = 편집 인덱스에 없거나 기준기간을 잴 수 없는 후보)")

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
