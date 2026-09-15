"""급증 판정을 `spike` 테이블에 적재한다 (WP-94).

    sink = SpikeSink(conn)
    sink.save(wiki="enwiki", title="Hurricane Milton",
              window_start=ws, detected_at=we, edit_count=10, decision=decision)
    conn.commit()

여태 저장소 전체에 `INSERT INTO spike` 가 **스키마 테스트 한 곳**에만 있었다
(`db/tests/test_schema.py`). `detect()` 결과는 `spike/replay.py` 의 stdout 으로 끝나서
파이프라인 밖으로 나가지 못했고, 그래서 `cluster/driver.py` 의 씨드 조회는 입력이
아예 없었다. 이 모듈이 그 출구다.

멱등성
    `spike` 에는 `UNIQUE (page_id, window_start)` 가 이미 있다(V1). 같은 윈도우를 다시
    판정하면 값만 갱신하고 행은 안 는다 — 리플레이를 두 번 돌려도 결과가 같다.

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

#: 재판정은 값만 갱신한다. 충돌 키는 V1 의 spike_unique_window (page_id, window_start).
UPSERT_SPIKE_SQL = """
INSERT INTO spike
    (page_id, detected_at, window_start, edit_count, edit_z, view_ratio, spike_score)
VALUES (%s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (page_id, window_start) DO UPDATE SET
    detected_at = EXCLUDED.detected_at,
    edit_count  = EXCLUDED.edit_count,
    edit_z      = EXCLUDED.edit_z,
    view_ratio  = EXCLUDED.view_ratio,
    spike_score = EXCLUDED.spike_score
"""


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
    """`SpikeDecision` 을 `spike` 행으로. 호출자가 `conn.commit()` 을 책임진다."""

    def __init__(self, conn) -> None:
        self._conn = conn
        #: (wiki, title) -> wiki_page.id. 같은 문서를 매 윈도우마다 다시 해석하지 않게.
        self._page_ids: dict[tuple[str, str], int] = {}

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
    ) -> int:
        """급증 한 건을 적재하고 `spike.page_id` 를 돌려준다.

        🔴 미탐(`is_spike=False`)은 부르지 않는다 — `spike` 는 "판정을 통과한 문서" 다
        (V1 테이블 주석). 호출자(`runtime.py`)가 거른다.
        """
        if not decision.is_spike:
            raise ValueError("미탐 판정은 spike 에 넣지 않는다 (테이블 정의)")

        page_id = self.page_id(wiki, title)
        with self._conn.cursor() as cur:
            cur.execute(UPSERT_SPIKE_SQL, (
                page_id,
                require_utc(detected_at, "detected_at"),
                require_utc(window_start, "window_start"),
                edit_count,
                # 신규 문서 경로는 기준선이 없어 z 를 못 낸다 — NULL 이 맞다(V1 은 NULL 허용).
                decision.edit_z,
                decision.view_ratio,
                decision.spike_score,
            ))
        return page_id
