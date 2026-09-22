"""ROOT SELECTION — `spike` 후보 중 클러스터링에 넣을 root 를 고른다.

MVP 정본 클러스터링은 **두 단계**다 (2026-09-22 확정, WP-161).

    1. ROOT SELECTION   이 모듈. spike 후보 → 시점당 20 root (views DESC, 24h 쿨다운)
    2. CORE GROUPING    `rootgraph.py`. as-of direct link → component → focus → D2

🔴 **판정이 아니다.** `spike` 행은 하나도 지우거나 고치지 않는다. detector 임계·공식·
`page_baseline` 은 이 모듈과 무관하다. 여기서 정하는 것은 **클러스터링에 무엇을 넣을지**
하나뿐이다.

출처
    WP-137 의 `cluster/seed_selection.py` 를 가져왔다. 선택 로직(`select`)은
    **규칙을 바꾸지 않았다** — 고정 2개월 산출물 22,080 root 를 만든 바로 그 코드이고,
    `(snapshot_ts, page_id)` 집합이 정확히 일치하는 것을 실측으로 확인했다(-161).
    바뀐 것은 이름(`seed_` → `root_`), **기본값이 켜짐이 된 것**, 그리고 아래 두 가지
    보강(입력 재정렬·증분 실행 쿨다운 이어받기)뿐이다.

왜 필요한가 (2026-09-21 실측)
    고정 warm-up 기준선이 `(page, hour_of_day)` 슬롯당 평균 1.08일밖에 관측하지 못해
    판정의 99.77%가 "표본 없음 → 조회수 >= 100" 경로로 떨어졌다. 그 결과 46일 구간에
    spike 가 162,775건(3,539건/일)이다. 기준선 관측을 채우는 작업은 따로 가고,
    그 전에도 화면은 나와야 하므로 **노출 단계에서만** 자른다.

    🔴 이 컷이 없으면 CORE 가 giant 를 만든다 (2026-09-22 실측). spike 전량
    162,775 root 에 CORE 를 돌리면 component 146,988 · **max 63 · 20+ giant 59** 다.
    22,080 root 에서는 max 16 · giant 0 이다. **giant 0 은 두 단계가 함께 만드는
    성질이지 CORE 만의 성질이 아니다.**

정렬은 `views` 다 — `spike_score` 를 쓰지 않는다
    🔴 `detector._score` 는 경로마다 **다른 단위**를 같은 컬럼에 넣는다:
       표본 없음 경로는 `log1p(views)`(실측 4.62~14.57), z 경로는 `log1p(view_z)`
       (실측 1.39~4.76). 그래서 `spike_score DESC` 로 정렬하면 **통계 관문을 통과한
       369건이 미검증 162,406건 아래로 전부 밀린다.** `view_ratio`(NULL 99.77%)와
       `view_baseline`(NULL 67.48%)도 같은 이유로 못 쓴다. NULL 이 없고 뜻이 하나인
       컬럼은 `views` 뿐이다.
    ⚠️ `views` 정렬은 "급등"이 아니라 **절대 인기** 순위다. 진짜 배수 신호는 기준선
       관측이 채워진 뒤에 생긴다 — 이 컷은 그때까지의 임시 표시 규칙이다.

반복 노출은 **제외가 아니라 쿨다운**으로 다룬다
    🔴 "너무 자주 나오는 문서를 빼는" 방식은 실측에서 **진짜 대형 사건을 정확히 골라
    죽였다.** 110시간 초과 제외로 `Dolly Parton`(111h)·`2026 Colombia earthquake`(133h)·
    `SummerSlam (2026)`(202h)·`Lanterns (TV series)`(163h)가 전부 0회가 됐다 — 큰 사건일
    수록 오래 지속되기 때문이다. 쿨다운은 같은 문서를 **살려 두되 간격만** 둔다
    (같은 실측에서 top-10 고유 문서 1,670 → 4,886, 스냅샷은 전부 채워짐).

    그래서 이 모듈에는 "N 회 이상이면 영구 제외" 같은 규칙이 없다. 넣지 말 것.

🔴 상한은 "훑은 개수" 가 아니라 "선택된 개수" 다
    쿨다운에 걸린 문서는 그 자리를 비우지 않는다 — 건너뛰고 **다음 후보가 그 칸을
    채운다.** "먼저 top-20 을 뽑고 중복을 버린다" 와는 다른 결과가 나온다.

순서
    쿨다운은 앞 시점의 선택 결과를 본다. 처리 순서는 **시각 오름차순 → 조회수
    내림차순(NULL 뒤) → page_id 오름차순** 이고, `SELECT_ROOT_RANKING_SQL` 의 ORDER BY
    가 그 순서를 준다. ⚠️ `select()` 는 받은 행을 **다시 정렬한다**(-161) — 호출자가
    ORDER BY 를 빠뜨려도 조용히 다른 root 가 뽑히지 않게 하려는 것이다.

문서 동일성은 `page_id` 다
    제목이 아니다. 제목은 이동·정규화로 바뀔 수 있고, `cluster_member.page_id` 가
    `wiki_page` 를 참조하므로 키도 그쪽이다. `source` 는 질의에서 이미 걸린다.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta

#: 시점당 root 상한. 고정 2개월 산출물(22,080 = 1,104 × 20)을 만든 값.
DEFAULT_LIMIT_PER_SNAPSHOT = 20

#: 같은 문서를 다시 고르기까지 비울 시간. **되돌아보는 창**이지 달력 날짜가 아니다.
DEFAULT_COOLDOWN_HOURS = 24

#: root 후보 전체를 시각·조회수 순으로. 선택은 파이썬에서 한다 — 쿨다운이 앞 시점의
#: 결과에 의존해서 SQL 창 함수로는 한 번에 못 낸다.
#: 🔴 `views DESC NULLS LAST` — V7 이전 행은 views 가 NULL 이라, NULL 을 앞에 두면
#:    조회수를 모르는 행이 상위를 먹는다.
SELECT_ROOT_RANKING_SQL = """
SELECT s.detected_at, s.page_id, s.views
  FROM spike s
 WHERE s.source = %s
   AND (%s::timestamptz IS NULL OR s.detected_at >= %s::timestamptz)
   AND (%s::timestamptz IS NULL OR s.detected_at <= %s::timestamptz)
 ORDER BY s.detected_at, s.views DESC NULLS LAST, s.page_id
"""

#: 범위 시작 직전 쿨다운 창 안에서 **이미 root 로 뽑혔던** 문서.
#: 🔴 LIVE 는 한 시점씩 돈다. 이게 없으면 증분 실행에서 쿨다운이 통째로 무력화되고,
#:    "시점 하나만 돌릴 때" 와 "전 구간을 한 번에 돌릴 때" 의 결과가 갈린다.
SELECT_RECENT_PICKS_SQL = """
SELECT cm.page_id, max(ic.snapshot_ts)
  FROM issue_cluster ic
  JOIN cluster_member cm ON cm.cluster_id = ic.id AND cm.spike_score IS NOT NULL
 WHERE ic.source = %s
   AND ic.snapshot_ts < %s::timestamptz
   AND ic.snapshot_ts >= %s::timestamptz
 GROUP BY cm.page_id
"""


@dataclass(frozen=True)
class RootSelectionConfig:
    """ROOT SELECTION 설정. **기본이 켜짐이다** (-161 에서 MVP 정본이 됐다).

    limit_per_snapshot: 한 시점에 고를 root 수 상한. None 이면 제한 없음.
    cooldown_hours    : 같은 문서를 다시 고르기까지 비울 시간. 0 이면 쿨다운 없음.
                        ⚠️ **되돌아보는 창(rolling)** 이지 달력 날짜가 아니다 —
                        24 를 주면 08:00 에 뽑힌 문서는 다음 날 08:00 이후에야
                        다시 뽑힌다. 달력 기준보다 약간 더 촘촘하게 막는다.
    """

    limit_per_snapshot: int | None = DEFAULT_LIMIT_PER_SNAPSHOT
    cooldown_hours: int = DEFAULT_COOLDOWN_HOURS

    @property
    def enabled(self) -> bool:
        return self.limit_per_snapshot is not None or self.cooldown_hours > 0

    def describe(self) -> str:
        return (f"limit/snapshot={self.limit_per_snapshot or '무제한'} · "
                f"cooldown={self.cooldown_hours}h")


def select(
    rows: Iterable[tuple[datetime, int, int | None]],
    config: RootSelectionConfig,
    prior_picks: dict[int, datetime] | None = None,
) -> set[tuple[datetime, int]]:
    """(detected_at, page_id, views) 들 → 선택된 `(detected_at, page_id)` 집합.

    `prior_picks` 는 범위 시작 이전에 이미 root 로 뽑힌 `page_id → 마지막 시각` 이다.
    증분 실행에서 쿨다운을 이어 가려고 받는다(전 구간 실행이면 비어 있다).

    쿨다운에 걸린 문서는 그 자리를 비우지 않는다 — 건너뛰고 **다음 후보가 그 칸을
    채운다.** 상한이 N 이면 "선택된 것이 N 개" 이지 "훑은 것이 N 개" 가 아니다.
    """
    if not config.enabled:
        return {(ts, page_id) for ts, page_id, _ in rows}

    # 🔴 계약 순서로 다시 정렬한다 — 호출자가 ORDER BY 를 빠뜨려도 같은 결과가 나오게.
    #    순서가 틀리면 에러 없이 다른 root 가 뽑힌다.
    ordered = sorted(rows, key=lambda r: (r[0], -(r[2] or 0), r[1]))

    window = timedelta(hours=config.cooldown_hours) if config.cooldown_hours else None
    chosen: set[tuple[datetime, int]] = set()
    last_pick: dict[int, datetime] = dict(prior_picks or {})
    taken: dict[datetime, int] = {}

    for detected_at, page_id, _views in ordered:
        if (config.limit_per_snapshot is not None
                and taken.get(detected_at, 0) >= config.limit_per_snapshot):
            continue
        if window is not None:
            previous = last_pick.get(page_id)
            if previous is not None and detected_at - previous < window:
                continue
        chosen.add((detected_at, page_id))
        last_pick[page_id] = detected_at
        taken[detected_at] = taken.get(detected_at, 0) + 1

    return chosen


def load_prior_picks(
    conn, source: str, config: RootSelectionConfig, since: datetime | None
) -> dict[int, datetime]:
    """범위 시작 직전 쿨다운 창 안에서 이미 root 로 뽑힌 문서.

    `since` 가 없으면(전 구간) 빈 dict — 그 앞에는 아무것도 없다.
    """
    if since is None or not config.cooldown_hours:
        return {}
    window_start = since - timedelta(hours=config.cooldown_hours)
    with conn.cursor() as cur:
        cur.execute(SELECT_RECENT_PICKS_SQL, (source, since, window_start))
        return {page_id: ts for page_id, ts in cur.fetchall()}


def load_selection(
    conn, source: str, config: RootSelectionConfig,
    since: datetime | None = None, until: datetime | None = None,
) -> set[tuple[datetime, int]] | None:
    """DB 에서 후보를 읽어 선택 집합을 만든다. 꺼져 있으면 None(= 전부 통과).

    None 과 빈 집합은 뜻이 다르다 — None 은 "컷 없음", 빈 집합은 "아무것도 안 고름"
    이다. 호출자가 `if selection is None` 으로 갈라야 한다.
    """
    if not config.enabled:
        return None
    with conn.cursor() as cur:
        cur.execute(SELECT_ROOT_RANKING_SQL, (source, since, since, until, until))
        rows = cur.fetchall()
    return select(rows, config, load_prior_picks(conn, source, config, since))
