"""급증 판정을 `spike` 테이블에 적재한다 (WP-94).

    sink = SpikeSink(conn, source="replay")
    sink.save(wiki="enwiki", title="Hurricane Milton",
              window_start=ws, detected_at=we, edit_count=10, decision=decision)
    conn.commit()

여태 저장소 전체에 `INSERT INTO spike` 가 **스키마 테스트 한 곳**에만 있었다
(`db/tests/test_schema.py`). `detect()` 결과는 `spike/replay.py` 의 stdout 으로 끝나서
파이프라인 밖으로 나가지 못했고, 그래서 `cluster/driver.py` 의 씨드 조회는 입력이
아예 없었다. 이 모듈이 그 출구다.

출처(provenance)를 생성 시점에 못박는다
    `SpikeSink(conn, source="live")` — `source` 는 키워드 필수다. 한 인스턴스는 한 출처만
    쓴다. `save()` 인자로 두지 않은 이유는, 그러면 호출 한 번의 실수로 LIVE 윈도우가
    `replay` 로(또는 그 반대로) 들어갈 수 있어서다. 인스턴스에 묶어 두면 그 실수의
    단위가 "한 행" 이 아니라 "한 실행" 이 되어 눈에 띈다.
    값은 `SPIKE_SOURCES` 두 개뿐이고, 생성 시점에 검사한다 — 첫 행을 쓰다가 아니라
    첫 행을 쓰기 전에 막는다.

멱등성
    `spike` 에는 `UNIQUE (source, page_id, window_start)` 가 있다(V5. ~~V1 의
    `(page_id, window_start)`~~ → 출처를 키에 넣었다). 같은 출처가 같은 윈도우를 다시
    판정하면 값만 갱신하고 행은 안 는다 — 리플레이를 두 번 돌려도, 같은 마이크로배치가
    재처리돼도 결과가 같다.

    🔴 **다른 출처는 서로 덮어쓰지 않는다.** 키에 `source` 가 있으니 LIVE 판정이
    리플레이 행에 `ON CONFLICT` 로 닿지 못한다 — DB 가 막는 것이지 여기서 조심하는 게
    아니다. 근거는 `db/migrations/V5__spike_source.sql` 의 🔴 절.

문서 해석은 `baseline_sink` 것을 그대로 쓴다
    `(wiki, title) → wiki_page.id` 규칙을 두 벌 만들면 한쪽만 고쳐졌을 때 같은 문서가
    두 행으로 갈린다. `baseline_sink.resolve_page_ids` 를 import 해서 쓴다 —
    `ON CONFLICT (wiki,title) DO UPDATE ... RETURNING id` 로 없는 문서를 만들어 주고
    id 를 돌려받는 그 패턴이다(`DO NOTHING` 이면 충돌 시 RETURNING 이 비어 id 를 못 받는다).
    적재 경로라 문서를 만드는 게 맞다 — 기준선 **조회**(`baseline_repository`)는 반대로
    순수 SELECT 를 쓴다.

⚠️ **`detected_at` 에 `now()` 를 쓰지 않는다.**
    `spike.detected_at` 은 판정 시각이다. 리플레이가 `now()` 를 찍으면 2024년 급증이
    전부 2026년에 감지된 것으로 남아 시간축이 무너진다 — 뒤에 붙을 클러스터 스냅샷이
    `detected_at` 으로 시점을 잡으므로 조용히 틀린 그래프가 된다. 호출자가 그 윈도우에서
    **판정이 가능해진 가장 이른 시각**(= 윈도우 끝)을 준다. `runtime.py` 가 그 기본값을 정한다.
    덤으로 값이 결정적이라 두 번 돌려도 `updated` 가 안 흔들린다.

🔴 **타임스탬프는 tz-aware UTC 로 넘긴다.** `spike.detected_at`·`window_start` 는
    `TIMESTAMPTZ` 인데 파이프라인 `window_start` 는 naive 문자열("YYYY-MM-DDTHH:00:00", UTC)이다.
    naive 로 그냥 넣으면 드라이버 로컬 시간대(KST)로 해석돼 **9시간 밀리는데 에러가 안 난다**
    (`spike/baseline.py` 가 기록한 2026-09-14 사고와 같은 함정). 여기서 방어한다.
"""

from __future__ import annotations

from datetime import datetime, timezone

from .baseline_sink import resolve_page_ids
from .detector import SpikeDecision

#: `spike.source` 가 가질 수 있는 값. V5 의 CHECK 제약과 한 벌이다 —
#: 한쪽만 늘리면 DB 가 거부하거나(추가 시) 여기가 통과시킨다(삭제 시).
#: `issue_cluster.source` 와 같은 어휘를 쓴다(V1).
SPIKE_SOURCES = ("live", "replay")

#: 재판정은 값만 갱신한다. 충돌 키는 V5 의 spike_unique_window (source, page_id, window_start).
#: 🔴 `source` 는 UPDATE 목록에 없다 — 충돌 키의 일부라 어차피 같은 값이고,
#: 적어 두면 "출처가 갱신될 수 있다" 로 읽힌다.
UPSERT_SPIKE_SQL = """
INSERT INTO spike
    (source, page_id, detected_at, window_start, edit_count, edit_z,
     views, view_baseline, view_ratio, spike_score, max_rev_id, last_edit_ts)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (source, page_id, window_start) DO UPDATE SET
    detected_at   = EXCLUDED.detected_at,
    edit_count    = EXCLUDED.edit_count,
    edit_z        = EXCLUDED.edit_z,
    views         = EXCLUDED.views,
    view_baseline = EXCLUDED.view_baseline,
    view_ratio    = EXCLUDED.view_ratio,
    spike_score   = EXCLUDED.spike_score,
    max_rev_id    = EXCLUDED.max_rev_id,
    last_edit_ts  = EXCLUDED.last_edit_ts
"""


def require_source(value: str) -> str:
    """`spike.source` 로 쓸 수 있는 값인지 확인하고 그대로 돌려준다.

    🔴 **추론하지 않는다.** 호출자가 무엇을 돌리는지(리플레이인지 LIVE 인지)는
    호출자만 안다. 여기서 "DSN 이 있으면 live" 같은 규칙을 만들면 두 경로가 어휘를
    공유하는 순간 조용히 어긋난다.
    """
    if value not in SPIKE_SOURCES:
        raise ValueError(
            f"spike.source 는 {SPIKE_SOURCES} 중 하나다 (받은 값: {value!r}). "
            "V5 의 CHECK 제약과 같은 목록이다."
        )
    return value


def require_utc(ts: datetime, field: str) -> datetime:
    """tz-aware UTC 인지 확인하고 그대로 돌려준다. naive 면 막는다.

    naive datetime 을 TIMESTAMPTZ 에 넣으면 세션 시간대로 해석돼 조용히 밀린다.
    "UTC 로 가정하고 붙여주기"도 하지 않는다 — 호출자가 KST 를 넘긴 경우를
    구분할 방법이 없어서다. 경계에서 계약을 강제한다.
    """
    if ts.tzinfo is None:
        raise ValueError(
            f"{field} 가 naive datetime 이다: {ts!r}. "
            "UTC tz-aware 로 넘긴다 — naive 는 세션 시간대로 해석돼 조용히 밀린다."
        )
    return ts.astimezone(timezone.utc)


class SpikeSink:
    """`SpikeDecision` 을 `spike` 행으로. 호출자가 `conn.commit()` 을 책임진다.

    `source` 는 키워드 필수다 — 기본값을 주지 않는다. 기본값이 있으면 새 writer 가
    그냥 안 적고 지나가는데, 그게 곧 잘못된 라벨이다(모듈 독스트링).
    """

    def __init__(self, conn, *, source: str) -> None:
        self._conn = conn
        #: 이 인스턴스가 쓰는 출처. 생성 시점에 검사해 첫 행 전에 막는다.
        self._source = require_source(source)
        #: (wiki, title) -> wiki_page.id. 같은 문서를 매 윈도우마다 다시 해석하지 않게.
        self._page_ids: dict[tuple[str, str], int] = {}

    @property
    def source(self) -> str:
        """이 싱크가 쓰는 `spike.source`. 로그·테스트에서 실제 라벨을 확인할 때."""
        return self._source

    def page_id(self, wiki: str, title: str) -> int:
        """`(wiki, title)` → `wiki_page.id`. 없으면 만든다(baseline_sink 와 같은 규칙)."""
        key = (wiki, title)
        if key not in self._page_ids:
            with self._conn.cursor() as cur:
                self._page_ids.update(resolve_page_ids(cur, [key]))
        return self._page_ids[key]

    def save(
        self,
        *,
        wiki: str,
        title: str,
        window_start: datetime,
        detected_at: datetime,
        edit_count: int,
        decision: SpikeDecision,
        views: int | None = None,
        view_baseline: float | None = None,
        max_rev_id: int | None = None,
        last_edit_ts: datetime | None = None,
    ) -> int:
        """급증 한 건을 적재하고 `spike.page_id` 를 돌려준다.

        `views`·`view_baseline` 은 판정에 쓴 값 그대로 넣는다 — 호출자(`runtime.py`)가
        윈도우와 기준선을 들고 있어서 거기서 받는다. 지어내지 않는다.

        `max_rev_id`·`last_edit_ts` 는 "무엇까지 보고 판정했는지" 의 증거다 (V9,
        WP-129 2번). 입력에 revision id 가 없으면 None 으로 남는다 —
        ⚠️ 0 이나 지금 시각으로 메우지 않는다. 그러면 감사에서 "증거 없음" 과
        "증거가 이렇다" 가 구분되지 않는다.

        🔴 **확정(`CONFIRMED`)만 넣는다** — `spike` 는 2단계까지 통과한 문서다
        (V1 테이블 주석 · 명세 §3.2 3번). 호출자(`runtime.py`)가 거르지만 여기서도 막는다.

        ⚠️ 후보 대기(`PENDING_VIEWS`)를 넣으면 **조회수를 안 본 문서가 이슈로 노출된다.**
        미탐과 메시지를 갈라 둔 이유다 — 후보 대기가 여기까지 온 건 호출자 배선이
        잘못된 것이지 판정이 틀린 게 아니다 (WP-126).
        """
        if decision.is_pending:
            raise ValueError(
                "후보 대기(조회수 미도착)는 spike 에 넣지 않는다 — 조회수 도착 후 재판정")
        if not decision.is_spike:
            raise ValueError("미탐 판정은 spike 에 넣지 않는다 (테이블 정의)")

        page_id = self.page_id(wiki, title)
        with self._conn.cursor() as cur:
            cur.execute(UPSERT_SPIKE_SQL, (
                self._source,
                page_id,
                require_utc(detected_at, "detected_at"),
                require_utc(window_start, "window_start"),
                edit_count,
                # 신규 문서 경로는 기준선이 없어 z 를 못 낸다 — NULL 이 맞다(V1 은 NULL 허용).
                decision.edit_z,
                # 🔴 판정에 쓴 조회수 원값과 기준선을 같이 남긴다 (V7, WP-129).
                # 여태 view_ratio 만 저장해서 두 결함이 났다: cluster_member.views 가 null 이고,
                # 표본 없는 경로(배수 NULL)가 "판정 미완료" 로 읽혀 completeness=pending 이 됐다.
                views,
                view_baseline,
                decision.view_ratio,
                decision.spike_score,
                # 🔴 시점 감사 증거 (V9, WP-129 2번). 없으면 NULL — 지어내지 않는다.
                max_rev_id,
                None if last_edit_ts is None else require_utc(last_edit_ts, "last_edit_ts"),
            ))
        return page_id
