"""시점별 클러스터·간선 생산 — 순수 로직 (WP-75).

Spark·DB 없이 테스트된다. 실 데이터 소스는 driver.py 가 배선한다.

클러스터링 게이트 (명세 v0.3 §3.2 4번, §11 실측 — WP-51·77)
    루트 씨드(`is_seed=true`) = 급증 판정(detector.py)을 직접 통과한 문서.
        각 루트 씨드가 한 클러스터를 연다.
    추가 씨드(`is_seed=true`) = 루트 씨드의 Clickstream 이웃(월별 덤프, n>=10) 중
        **문서 생성 시각이 씨드 사건일 ±창(기본 30일) 안**인 **새 사건 문서**.
        생성일 근접이 곧 시간 동시성이다 — 신규 사건 문서는 baseline 이 없어
        절대 편집수만으로 이미 급증 판정을 통과할 문서이고, 그래서 배경이 아니라
        사건 자체다. 이 모듈이 배선하는 경로는 여기까지다.
    ⚠️ 비-씨드(`is_seed=false`) = 오래전 생성된 이웃 중 사건기간 편집 재급증
        비율 >= 5 AND 절대 편집 >= 20 인 문서(WP-77). **이 모듈에 없다.**
        재급증 입력 자체를 안 받는다 — 규칙을 여기서 흉내 내지 않는다.

    🔴 ~~생성일 창을 통과한 이웃을 `is_seed=false` 로 저장~~ → **`true`**
        (2026-09-18, -115). 한 칸에 성격이 정반대인 둘이 섞여 있었다. 생성일 창을
        통과한 문서는 사건 **때문에 새로 생긴** 문서고, -77 문서는 사건 **이전부터
        있던 배경** 문서다. 같은 값으로 저장하면 화면도 API 도 "이 문서가 사건
        자체인가, 사건이 끌어온 배경인가"를 구분할 수 없다.
    Clickstream 값에 별도 문턱을 두지 않는다 — 덤프 하한(n>=10)만. 절대 이동량으로는
        "같은 이슈"와 "배경 지식"이 안 갈린다(§11: Hormuz 배경 문서가 사건 문서보다
        30배 더 클릭됨). 포함 여부는 생성일 창이 정하고, n 은 weight 로만 쓴다.

🔴 **근거 월(`Neighbor.clickstream_month`)은 스냅샷 월보다 앞선 완료 월이다**
    (2026-09-18 정정, -115). 이 모듈은 월을 고르지 않는다
    (`cluster/driver.clickstream_month_for` 가 고른다). 아래는 그 계약의 근거다.

    ~~"replay 는 사건월, LIVE 는 전월"~~ — 출처마다 다른 값인 줄 알았는데 아니다.
        명세 v0.3 §3.2 4번이 **리플레이에도 같은 event-time 계약**을 건다:
        "`clickstream_month` 는 스냅샷 월보다 앞선 데이터 기간이어야 한다 … 이 판단은
        원본의 데이터 기간 기준이고 로컬 적재 시각 기준은 아니다. 따라서 과거 원본을
        나중에 적재하는 리플레이도 같은 event-time 계약으로 계산할 수 있다."
        "과거 재생이라 그 달 덤프가 이미 나와 있다" 는 **적재 시각 논거**라 배제된다.
        §11 도 `-51` 의 사건 당월 dump 실측에 "운영 당시에는 사용할 수 없던 당월
        덤프를 월 종료 후 분석한 품질 검증이며, 해당 월 스냅샷 입력으로 사용했다는
        뜻이 아니다" 를 달아 두었다.

    사건월(`event`) 산출물은 **사후 QA / upper-bound 실험**이다. 배선이 이론상 최대
        몇 멤버를 붙일 수 있는지 재는 값이지 제품 성능이 아니다. 인용 금지 사항은
        `cluster/driver.CLICKSTREAM_MONTH_RULES` 에 수치와 함께 적어 두었다.
    Wikidata 관계는 게이트에서 빠졌다(§3.2 4번 — 속성 5종 전수 검사 실패). 화면 근거
        간선(점선)으로만 그린다.
    ⚠️ 기존 문서가 사건으로 재조명되는 비-씨드(예: Mojtaba_Khamenei, 2009 생성)는
        생성일 창으로 못 잡는다 — WP-77 로 분리. 이 모듈은 다루지 않는다.

issue_key
    id 는 스냅샷마다 새로 생기지만, 같은 사건을 시점 간에 이으려면 안정 키가 필요하다.
    씨드 문서의 자연키(source:wiki:title)를 쓴다 — 씨드 문서는 사건 내내 유지된다.
    first_detected_at 은 이 issue_key 가 과거에 처음 잡힌 시각(없으면 이번 스냅샷).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from .score import SCORE_VERSION, pulse_score, size_score

# --- 기본 파라미터 (실측 기반, 운영하며 조정) --------------------------------

#: 씨드 사건일 기준 문서 생성일 창(일). §11 실측 ±14(Milton)~30(Hormuz·Iran).
#: 기본은 넓은 쪽 30 — 셋 다 창 밖에 배경 문서가, 창 안에 사건 문서만 걸렸다.
DEFAULT_CREATION_WINDOW_DAYS = 30

#: Clickstream 월별 덤프 자체의 하한. 이보다 낮은 이동량 행은 덤프에 없다.
CLICKSTREAM_FLOOR = 10

#: HOT(이 스냅샷에서 활발히 급증 중) 판정 임계. 씨드 급등도 최댓값 기준.
#: detector 확정 점수(Milton 9.7)와 편집만 통과(3~4) 사이인 5.0.
DEFAULT_HOT_SPIKE_THRESHOLD = 5.0

#: NEW 배지 창(시간). 0 <= snapshot_ts - first_detected_at < 이 값이면 NEW.
DEFAULT_NEW_WINDOW_HOURS = 24.0

#: 카테고리 확정 전 기본값. LLM 검증 단계가 나중에 덮는다.
DEFAULT_CATEGORY = "other"

#: 생산 직후 상태. LLM 검증(WP-68)이 VERIFYING/CONFIRMED/DISCARDED 로 옮긴다.
DEFAULT_STATUS = "DETECTED"


# --- 입력 -------------------------------------------------------------------

@dataclass(frozen=True)
class Seed:
    """급증 판정을 통과한 문서. 한 클러스터의 앵커."""
    page_id: int
    wiki: str
    title: str
    event_date: date          # 사건일(생성일 창의 중심). 보통 씨드 급증 시점의 날짜.
    spike_score: float
    window_start: datetime     # 지표 집계 구간. 시작 < 종료 <= snapshot_ts.
    window_end: datetime
    edit_count: int | None = None
    views: int | None = None
    edit_baseline: float | None = None
    view_baseline: float | None = None
    completeness: str = "complete"   # complete / pending(조회수 대기) / unavailable


@dataclass(frozen=True)
class Neighbor:
    """루트 씨드의 Clickstream 이웃. 생성일 창을 통과하면 **추가 씨드** 멤버가 된다."""
    page_id: int
    wiki: str
    title: str
    clickstream_n: int         # 이동량. weight 로 쓴다.
    # 근거 월 YYYY-MM. **어느 달을 쓰는지는 출처마다 다르다** — 아래 🔴 참고.
    # 이 모듈은 값을 받아 간선 근거 라벨로 실어 나를 뿐, 월을 고르지 않는다.
    clickstream_month: str
    # 문서 생성 시각. **timezone-aware UTC** 여야 한다 (2026-09-18, -115).
    # 소스는 mediawiki_history page_creation_timestamp (`batch/page_creation`).
    created_at: datetime | None
    directed: bool = True       # Clickstream 은 방향(씨드 -> 이웃) 이동이다.


@dataclass(frozen=True)
class WikidataRelation:
    """씨드와 한 멤버 사이 Wikidata 관계. 점선 근거 간선으로만 쓴다."""
    target_page_id: int
    label: str                 # 예: "P361 부분"
    observed_at: datetime       # 관측 시각(UTC).


# --- 출력 -------------------------------------------------------------------

@dataclass(frozen=True)
class Member:
    page_id: int
    is_seed: bool
    weight: float
    completeness: str
    edit_count: int | None = None
    views: int | None = None
    edit_baseline: float | None = None
    view_baseline: float | None = None
    spike_score: float | None = None
    size_score: float | None = None
    window_start: datetime | None = None
    window_end: datetime | None = None


@dataclass(frozen=True)
class Edge:
    source_page_id: int
    target_page_id: int
    kind: str                  # clickstream / wikidata
    directed: bool
    weight: float
    evidence_label: str
    evidence_month: str | None = None
    evidence_observed_at: datetime | None = None


@dataclass(frozen=True)
class Cluster:
    issue_key: str
    category: str
    status: str
    pulse_score: float
    hot: bool
    first_detected_at: datetime
    members: tuple[Member, ...]
    edges: tuple[Edge, ...]
    label: str | None = None
    seed_page_id: int | None = None


@dataclass(frozen=True)
class Snapshot:
    snapshot_ts: datetime
    source: str                # live / replay
    score_version: str
    new_window_hours: float
    clusters: tuple[Cluster, ...]

    @property
    def cluster_count(self) -> int:
        return len(self.clusters)


# --- 생산 -------------------------------------------------------------------

def issue_key_of(source: str, seed: Seed) -> str:
    """씨드 문서의 자연키로 시점 간 안정 식별자를 만든다."""
    return f"{source}:{seed.wiki}:{seed.title}"


def _as_utc(moment: datetime, field_name: str) -> datetime:
    """timezone-aware 만 통과시키고 UTC 로 맞춘다 (2026-09-18, -115).

    🔴 naive 를 `.replace(tzinfo=utc)` 로 "고쳐" 주지 않는다. 그 순간 로컬 시각이
    UTC 로 둔갑해 조용히 어긋난 값이 쌓인다 — KST 장비에서 9시간이다
    (`streaming/live_spike.py` 가 경계에서 epoch 초로 건네는 것과 같은 이유).
    """
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError(f"{field_name} 은 timezone-aware 여야 한다: {moment!r}")
    return moment.astimezone(timezone.utc)


def _within_creation_window(
    created_at: datetime | None, event_date: date, window_days: int
) -> bool:
    """문서 생성 시각이 사건일 ±창 안인가. 생성 시각 미상은 포함하지 않는다.

    생성 시각을 못 구한 이웃은 게이트를 통과시키지 않는다 — 근거 없이 넣으면
    §11 에서 실측한 "넓어서 못 쓰는" 배경 문서 오염이 재발한다.

    ⚠️ **판정 기준은 안 바뀌었다** (2026-09-18, -115). 입력 타입만 `date` 에서
    tz-aware `datetime` 이 됐고, 비교는 여전히 UTC 날짜끼리 `±window_days` 다.
    창 폭도 `DEFAULT_CREATION_WINDOW_DAYS` 그대로다.
    """
    if created_at is None:
        return False
    created_date = _as_utc(created_at, "Neighbor.created_at").date()
    return abs((created_date - event_date).days) <= window_days


def _build_cluster(
    source: str,
    snapshot_ts: datetime,
    seed: Seed,
    neighbors: Sequence[Neighbor],
    relations: Sequence[WikidataRelation],
    prior_first_detected: Mapping[str, datetime],
    window_days: int,
    hot_threshold: float,
) -> Cluster:
    key = issue_key_of(source, seed)

    seed_member = Member(
        page_id=seed.page_id,
        is_seed=True,
        weight=1.0,
        completeness=seed.completeness,
        edit_count=seed.edit_count,
        views=seed.views,
        edit_baseline=seed.edit_baseline,
        view_baseline=seed.view_baseline,
        spike_score=seed.spike_score,
        size_score=size_score(seed.spike_score),
        window_start=seed.window_start,
        window_end=seed.window_end,
    )

    members: list[Member] = [seed_member]
    edges: list[Edge] = []
    included_page_ids: set[int] = {seed.page_id}

    for nb in neighbors:
        if nb.page_id == seed.page_id:
            continue                         # 자기 자신은 간선·멤버로 안 넣는다
        if nb.page_id in included_page_ids:
            continue                         # 중복 이웃 제거
        if nb.clickstream_n < CLICKSTREAM_FLOOR:
            continue                         # 덤프 하한 미만(있을 수 없지만 방어적)
        if not _within_creation_window(nb.created_at, seed.event_date, window_days):
            continue                         # 생성일 창 밖 — 게이트 탈락

        included_page_ids.add(nb.page_id)
        members.append(Member(
            page_id=nb.page_id,
            # 🔴 **추가 씨드다** (명세 v0.3 §3.2 4번). 생성일 창을 통과했다는 것은
            #    사건 때문에 새로 생긴 문서라는 뜻이고, 그건 배경이 아니라 사건의
            #    일부다. `false` 자리는 -77 재급증 문서 몫으로 비워 둔다.
            is_seed=True,
            weight=float(nb.clickstream_n),
            # 시점 지표(편집·조회수)는 이 경로에서 재지 않는다 — 관계로만 딸려온다.
            # 루트 씨드와 달리 detector 를 직접 통과한 문서가 아니라서 급증 수치가 없다.
            completeness="unavailable",
        ))
        edges.append(Edge(
            source_page_id=seed.page_id,
            target_page_id=nb.page_id,
            kind="clickstream",
            directed=nb.directed,
            weight=float(nb.clickstream_n),
            evidence_label=f"Clickstream {nb.clickstream_month}",
            evidence_month=nb.clickstream_month,
        ))

    # Wikidata 점선 간선 — 양 끝이 모두 이 클러스터 멤버일 때만.
    for rel in relations:
        if rel.target_page_id not in included_page_ids:
            continue
        if rel.target_page_id == seed.page_id:
            continue
        edges.append(Edge(
            source_page_id=seed.page_id,
            target_page_id=rel.target_page_id,
            kind="wikidata",
            directed=False,
            weight=1.0,
            evidence_label=rel.label,
            evidence_observed_at=rel.observed_at,
        ))

    return Cluster(
        issue_key=key,
        category=DEFAULT_CATEGORY,
        status=DEFAULT_STATUS,
        pulse_score=pulse_score([seed.spike_score]),
        hot=seed.spike_score >= hot_threshold,
        first_detected_at=prior_first_detected.get(key, snapshot_ts),
        members=tuple(members),
        edges=tuple(edges),
        label=None,
        seed_page_id=seed.page_id,
    )


def build_snapshot(
    snapshot_ts: datetime,
    source: str,
    seeds: Sequence[Seed],
    neighbors: Mapping[int, Sequence[Neighbor]],
    wikidata: Mapping[int, Sequence[WikidataRelation]] | None = None,
    prior_first_detected: Mapping[str, datetime] | None = None,
    *,
    creation_window_days: int = DEFAULT_CREATION_WINDOW_DAYS,
    hot_spike_threshold: float = DEFAULT_HOT_SPIKE_THRESHOLD,
    new_window_hours: float = DEFAULT_NEW_WINDOW_HOURS,
) -> Snapshot:
    """한 시점의 클러스터·멤버·간선을 생산한다.

    seeds 각각이 한 클러스터를 연다. neighbors[seed.page_id] 는 그 씨드의
    Clickstream 이웃, wikidata[seed.page_id] 는 그 클러스터 안 Wikidata 관계다.
    같은 문서가 여러 씨드의 이웃이면 각 클러스터에 한 번씩 들어간다(계약).

    source 는 'live' 또는 'replay'. 파라미터는 실측 기본값이며 리플레이 재계산에서
    같은 값을 주면 결정적으로 같은 스냅샷이 나온다(재계산 호환).
    """
    if source not in ("live", "replay"):
        raise ValueError(f"source must be live/replay, got {source!r}")

    wikidata = wikidata or {}
    prior_first_detected = prior_first_detected or {}

    clusters = tuple(
        _build_cluster(
            source=source,
            snapshot_ts=snapshot_ts,
            seed=seed,
            neighbors=neighbors.get(seed.page_id, ()),
            relations=wikidata.get(seed.page_id, ()),
            prior_first_detected=prior_first_detected,
            window_days=creation_window_days,
            hot_threshold=hot_spike_threshold,
        )
        for seed in seeds
    )

    return Snapshot(
        snapshot_ts=snapshot_ts,
        source=source,
        score_version=SCORE_VERSION,
        new_window_hours=new_window_hours,
        clusters=clusters,
    )
