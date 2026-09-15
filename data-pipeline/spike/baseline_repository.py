"""`page_baseline` 을 읽어 `detector.Baseline` 으로 준다 (WP-94).

    repo = BaselineRepository(conn)
    baseline = repo.get("enwiki", "Hurricane Milton", hour_of_day=19)   # None 이면 기준선 없음

여태 `page_baseline` 을 **쓰는** 코드(`baseline_sink.py`)만 있고 **읽는** 코드가
저장소에 하나도 없었다. `spike/replay.py` 는 판정할 때마다 `baseline_at()` 으로
메모리에서 기준선을 다시 만든다 — 그래서 -60 이 적재한 행은 아무도 안 봤다.
이 모듈이 그 공백을 메운다. 스트리밍 경로(`streaming/edit_windows.py`)도 같은
객체를 쓸 수 있게 리플레이 얘기는 여기 없다.

🔴 **읽기는 문서를 만들지 않는다.** `baseline_sink.resolve_page_ids` 는
`INSERT ... ON CONFLICT DO UPDATE ... RETURNING id` 라 **없는 문서를 만들어 준다** —
적재 경로에는 맞지만 조회 경로가 그걸 쓰면 판정만 해도 `wiki_page` 가 불어난다.
여기서는 순수 `SELECT` 를 쓴다. 문서를 만드는 건 적재(`baseline_sink`)와
급증 저장(`spike_sink`)의 책임이다.

🔴 **제목은 읽는 지점에서 canonical 로 맞춘다** (WP-92 와 같은 규칙).
`wiki_page.title` 은 공백형이 정본인데(`Hurricane Milton`), 호출자가 덤프 원형
(`Hurricane_Milton`)을 넘기면 `SELECT` 가 **조용히 0행**이 되고, 그건 "기준선 없음"
→ 신규 문서 경로로 읽힌다. 에러가 안 나는 쪽이라 여기서 흡수한다.
변환은 `producer/normalize.canonical_title` 한 곳이며 멱등이다.

없음 vs 얇음
    - **없음** = `get()` 이 `None`. 그 슬롯에 행 자체가 없다(관측이 없었거나 문서 미등록).
    - **얇음** = `Baseline.is_thin` (`sample_days < MIN_BASELINE_SAMPLE_DAYS`).
    `detect()` 는 둘 다 신규 문서 경로로 보내지만 **원인이 다르다** — 진단·로그에서
    구분해야 "적재가 안 된 것"과 "표본이 모자란 것"을 헷갈리지 않는다.
    호출자는 `None` 인지 `.is_thin` 인지로 가른다.

슬롯 24개를 한 번에 읽는다
    한 문서를 여러 윈도우에 걸쳐 판정하면(리플레이는 문서당 272 윈도우) 슬롯당 왕복이
    나온다. `page_baseline` PK 가 `(page_id, hour_of_day)` 라 문서당 최대 24행뿐이므로
    처음 한 번에 다 읽어 캐시한다 — 리플레이 실측에서 왕복이 272 → 1 이 된다.

🔴 **캐시 수명은 호출자가 정한다. 영구 캐시가 아니다.**
    이 객체 자체는 `invalidate()` 를 부를 때까지 캐시를 들고 있다. 그래서 캐시를 언제
    비울지는 `SpikeRuntime.iter_process` 가 **배치 시작마다** 정한다 — 장수명 LIVE
    프로세스가 같은 인스턴스를 계속 쓰더라도 `page_baseline` 재적재가 다음 배치에
    반영된다. 이 규칙이 없으면 기준선을 새로 적재해도 영원히 옛 값으로 판정하는데
    **에러가 안 나고 z 만 틀린다.**
"""

from __future__ import annotations

from producer.normalize import canonical_title

from .detector import Baseline

#: 한 문서의 모든 시간대 슬롯. PK 가 (page_id, hour_of_day) 라 최대 24행이다.
#: 문서 조회를 JOIN 으로 묶어 왕복을 하나로 줄인다 — 없는 문서는 그냥 0행이 온다.
SELECT_BASELINE_SQL = """
SELECT b.hour_of_day, b.edit_ewma, b.edit_stddev, b.view_ewma, b.view_stddev,
       b.sample_days
  FROM page_baseline b
  JOIN wiki_page p ON p.id = b.page_id
 WHERE p.wiki = %s AND p.title = %s
"""


class BaselineRepository:
    """`(wiki, title, hour_of_day)` → `detector.Baseline`. 문서 단위로 캐시한다."""

    def __init__(self, conn) -> None:
        self._conn = conn
        #: (wiki, canonical title) -> {hour_of_day: Baseline}. 빈 dict 는 "조회했는데 없다".
        self._cache: dict[tuple[str, str], dict[int, Baseline]] = {}

    def slots(self, wiki: str, title: str) -> dict[int, Baseline]:
        """한 문서의 시간대별 기준선 전부. 없으면 빈 dict."""
        key = (wiki, canonical_title(title))
        cached = self._cache.get(key)
        if cached is None:
            cached = self._load(*key)
            self._cache[key] = cached
        return cached

    def get(self, wiki: str, title: str, hour_of_day: int) -> Baseline | None:
        """그 슬롯의 기준선. 행이 없으면 `None` (= 신규 문서 경로)."""
        return self.slots(wiki, title).get(hour_of_day)

    def invalidate(self) -> None:
        """캐시를 비운다. 기준선을 재적재한 뒤 같은 인스턴스를 계속 쓸 때."""
        self._cache.clear()

    def _load(self, wiki: str, title: str) -> dict[int, Baseline]:
        with self._conn.cursor() as cur:
            cur.execute(SELECT_BASELINE_SQL, (wiki, title))
            rows = cur.fetchall()
        return {
            int(hour_of_day): Baseline(
                edit_ewma=float(edit_ewma),
                # NULL 은 그대로 넘긴다. 0 으로 채우면 detector._z 가 "분산 0" 과
                # "표본 없음" 을 구분 못 한다 (V4 주석과 같은 이유).
                edit_stddev=None if edit_stddev is None else float(edit_stddev),
                view_ewma=None if view_ewma is None else float(view_ewma),
                sample_days=int(sample_days),
                view_stddev=None if view_stddev is None else float(view_stddev),
            )
            for (hour_of_day, edit_ewma, edit_stddev, view_ewma, view_stddev,
                 sample_days) in rows
        }
