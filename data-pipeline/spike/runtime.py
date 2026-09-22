"""윈도우 한 건을 판정해 `spike` 까지 보내는 런타임 경로 (WP-94).

    runtime = SpikeRuntime(BaselineRepository(conn), SpikeSink(conn, source="replay"))
    outcome = runtime.process(window)      # 급증이면 저장, 아니면 안 저장
    conn.commit()

지금까지 이 경로가 통째로 없었다. `page_baseline` 을 읽는 코드도, `spike` 에 쓰는
코드도 없어서 `Historical Window → baseline → 판정 → 저장` 이 한 번도 이어지지 않았다.

🔴 **이 모듈은 리플레이 전용이 아니다.**
    입력이 `PageWindow` 한 건이라, 과거 덤프 재생과 `streaming/edit_windows.py` 의
    윈도우 집계가 **같은 함수를 부른다**. 리플레이 쪽 어휘(`replay_*`)를 이름에 넣지
    않은 이유다. 스트리밍을 붙일 때 고쳐야 할 건 여기가 아니라 `PageWindow` 를 만드는
    쪽이다 — 집계 계약이 같으므로(`batch/historical_windows.py` 상단 §AC) 변환만 하면 된다.

⚠️ **DB 기준선과 리플레이 메모리 기준선은 같은 답을 내지 않는다.**
    `spike/replay.py` 의 `baseline_at()` 은 **판정 대상 시점 직전까지**로 창을 잘라
    기준선을 만든다(판정 대상이 자기 기준선에 들어가면 급증이 평소로 희석되므로).
    반면 `page_baseline` 은 `baseline_sink` 가 적재한 시점(`--as-of`)에 **고정된** 값이고,
    그 창에는 사건 구간이 통째로 들어가 있을 수 있다.
    → **같은 문서·같은 윈도우에서 두 모드의 판정이 갈릴 수 있다. 버그가 아니라 정의 차이다.**
    메모리 모드는 임계·수식 **회귀 검증용**, DB 모드는 **런타임 경로 검증용**이다.
    숫자를 비교할 때 이 둘을 섞으면 "리플레이가 깨졌다" 로 오진한다.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from batch.historical_windows import WINDOW_HOURS
from producer.normalize import canonical_title

from .baseline_repository import BaselineRepository
from .detector import Baseline, SpikeDecision, Window, detect
from .spike_sink import SpikeSink, require_utc


def parse_window_start(value: str | datetime) -> datetime:
    """Historical Window 의 `window_start` 를 tz-aware UTC datetime 으로.

    -58 산출물은 naive **문자열** "YYYY-MM-DDTHH:00:00" 이고 그 계약이 UTC 다
    (`batch/historical_windows.py`). 그래서 문자열에 한해 UTC 를 붙여 준다.

    ⚠️ naive **datetime 객체**는 반대로 막는다(`require_utc`). 문자열은 출처가 -58 로
    정해져 있지만 객체는 호출자가 어디서 만들었는지 알 수 없어서다 — KST datetime 을
    UTC 로 가정해 붙이면 9시간이 조용히 밀린다.
    """
    if isinstance(value, datetime):
        return require_utc(value, "window_start")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True)
class PageWindow:
    """한 문서의 한 시간 윈도우 관측치 — 판정 입력.

    Historical Window 한 행(-58)이자 스트리밍 윈도우 한 행이다. 두 경로가 같은 형태를
    내도록 집계 계약이 이미 맞춰져 있다(`batch/historical_windows.py` §AC: 1시간 창,
    봇 제외, 키 `(wiki, title)`).

    `views` 가 `None` 이면 조회수 미도착이다 — `detect()` 가 **후보 대기**(PENDING_VIEWS)를
    낸다. ~~편집만으로 '감지됨'~~ → 2단계 계약에서 바뀌었다 (WP-126): 조회수 없이는
    확정하지 않는다.
    ⚠️ -58 산출물은 조회수 적재본이 없을 때 **0** 을 낸다(`None` 이 아니다). 그 0 은
    "진짜 0회" 와 구분되지 않는데, 그건 -58 의 성질이고 여기서 뒤집지 않는다 —
    ⚠️ 2단계 계약에서 `view_ewma` 가 0/None 이면 관문이 **닫히는 게 아니라** 절대 하한
    (`views >= 100`)만으로 판정한다 — 명세 §3.2 3번 "0에서의 급등". 그래서 -58 의 0 이
    진짜 0회로 들어오면 100회 이상일 때 확정될 수 있다. 조회수 투입 경로(별건)에서
    -58 의 0 과 진짜 0 을 가르는 게 맞다.

    🔴 **`window_end` 는 소스가 주면 그 값을 쓴다.** 두 경로가 다르다:
        배치(-58) 행에는 `window_end` 가 없다 — 정각 tumbling 이라 길이가 `WINDOW_HOURS`
        상수로 고정이다. 그래서 없으면 `window_start + WINDOW_HOURS` 로 채운다.
        스트리밍(`streaming/edit_windows.py`)은 `F.col("window.end")` 를 **이미 내보낸다**.
        그 길이는 `WINDOW_SIZE` 환경변수라 `WINDOW_HOURS` 와 갈릴 수 있고, 갈리면
        `detected_at` 이 에러 없이 어긋난다. 실제 끝을 들고 있으면 그걸 쓴다.
    """
    wiki: str
    title: str
    window_start: datetime      # tz-aware UTC
    edit_count: int
    editor_count: int
    views: int | None = None
    #: `views` 중 모바일 몫 (V15, WP-210). 1단계 대체 경로의 봇 필터 입력이다.
    #: 🔴 None 은 **"모바일 0" 이 아니라 "안 쟀다"** — V15 이전 적재분이 그렇다.
    #: 0 으로 메우면 그 구간이 전부 봇으로 판정된다.
    mobile_views: int | None = None
    #: 윈도우 끝. 안 주면 `window_start + WINDOW_HOURS`. 소스가 주면 그 값이 이긴다.
    window_end: datetime | None = None
    #: 이 윈도우 집계에 들어간 최대 revision id. 판정에는 안 쓰고 **증거로만** 남긴다
    #: (V9, WP-129 2번). 없으면 None — 0 으로 메우지 않는다.
    max_rev_id: int | None = None
    #: 이 윈도우에서 본 마지막 편집 시각. `last_edit_ts <= window_end` 가 자체 검증식이다.
    last_edit_ts: datetime | None = None

    def __post_init__(self) -> None:
        # 제목은 읽는 지점에서 canonical 로 (WP-92 와 같은 규칙). 멱등이다.
        object.__setattr__(self, "title", canonical_title(self.title))
        start = require_utc(self.window_start, "window_start")
        object.__setattr__(self, "window_start", start)

        end = (start + timedelta(hours=WINDOW_HOURS) if self.window_end is None
               else require_utc(self.window_end, "window_end"))
        if end <= start:
            raise ValueError(f"window_end({end}) 가 window_start({start}) 보다 뒤가 아니다")
        object.__setattr__(self, "window_end", end)

        # 🔴 증거가 증거 구실을 하려면 여기서 막아야 한다 (WP-129 2번).
        #    마지막 편집이 윈도우 끝보다 뒤면 그 윈도우에 미래 편집이 섞인 것이다 —
        #    리플레이에서 덤프 구간을 잘못 자르면 이렇게 된다. 통과시키면 그 행은
        #    "증거가 있는데 그 증거가 규칙 위반" 인 상태로 저장되고, 아무도 안 본다.
        if self.last_edit_ts is not None:
            last = require_utc(self.last_edit_ts, "last_edit_ts")
            object.__setattr__(self, "last_edit_ts", last)
            if last >= end:
                raise ValueError(
                    f"last_edit_ts({last}) 가 window_end({end}) 뒤다 — 이 윈도우에 "
                    "윈도우 밖 편집이 섞였다")

    @classmethod
    def from_row(cls, row: dict) -> PageWindow:
        """Historical Window(-58) 행 또는 스트리밍 윈도우 행에서 만든다.

        `window_end` 는 있으면 쓰고 없으면 `WINDOW_HOURS` 로 채운다 — -58 은 안 내고
        `streaming/edit_windows.py` 는 낸다.

        🔴 **`views == 0` 을 미도착(None)으로 읽는다** (2026-09-18, WP-126).
            -58 은 조회수 적재본이 없으면 `None` 이 아니라 **0** 을 낸다. 2단계 계약에서
            그 0 을 액면대로 받으면 판정이 `REJECTED` 가 되고, 폐기는 다시 안 본다 —
            조회수 원본이 나중에 도착해도 재판정 대상에서 빠진다. 반대로 미도착으로
            읽으면 후보 대기로 남아 도착 시 다시 판정된다.

            ⚠️ 진짜 "그 시간에 0회 조회" 와 구분이 안 되는 건 그대로다. 다만 진짜 0 이어도
            확정 조건(`views >= 100`)을 못 넘으므로 **확정 결과는 안 바뀐다.** 바뀌는 건
            "폐기냐 대기냐" 뿐이고, 둘 중에는 대기가 안전한 쪽이다.

            이 애매함의 진짜 해결은 -58 이 미적재를 `None` 으로 내는 것이다 — 조회수
            투입 경로(별건)에서 정리한다.
        """
        views = row.get("views")
        if views == 0:
            views = None
        end = row.get("window_end")
        return cls(
            wiki=row["wiki"],
            title=row["title"],
            window_start=parse_window_start(row["window_start"]),
            edit_count=int(row["edit_count"]),
            editor_count=int(row.get("editor_count") or 0),
            views=None if views is None else int(views),
            # ⚠️ 없으면 None 이다 — 0 으로 메우지 않는다. V15 이전 산출물에는 아예
            #    이 키가 없고, 0 으로 채우면 "모바일 0%" = 봇으로 판정된다.
            mobile_views=(None if row.get("mobile_views") is None
                          else int(row["mobile_views"])),
            window_end=None if end is None else parse_window_start(end),
            # 시점 감사 증거. 안 싣는 입력(옛 산출물)도 있어서 없으면 None 이다.
            max_rev_id=(None if row.get("max_rev_id") is None
                        else int(row["max_rev_id"])),
            last_edit_ts=(None if row.get("last_edit_ts") is None
                          else parse_window_start(row["last_edit_ts"])),
        )

    @property
    def hour_of_day(self) -> int:
        """0..23 (UTC). `page_baseline` 슬롯 키 — V3 이후 hour_of_week 이 아니다."""
        return self.window_start.hour

    def as_detector_window(self) -> Window:
        return Window(edit_count=self.edit_count,
                      editor_count=self.editor_count,
                      views=self.views,
                      mobile_views=self.mobile_views)


@dataclass(frozen=True)
class DetectionOutcome:
    """한 윈도우의 판정 결과 + 무엇을 근거로 판정했는지.

    `baseline` 은 **DB 에서 읽은 그 객체 그대로**다 — 판정이 실제로 `page_baseline` 을
    탔다는 증거로 쓴다(테스트·로그). 메모리에서 다시 만든 값이 아니다.
    """
    window: PageWindow
    baseline: Baseline | None
    decision: SpikeDecision
    persisted: bool

    @property
    def baseline_source(self) -> str:
        """`absent` / `thin` / `db` — 신규 문서 경로로 간 **이유**를 가른다.

        `detect()` 는 '없음' 과 '얇음' 을 똑같이 신규 문서 경로로 보내지만 원인이 다르다:
        없음은 **적재가 안 된 것**, 얇음은 **표본이 모자란 것**이다. 둘을 안 가르면
        기준선을 안 넣고 돌린 실행을 "표본 부족" 으로 오진한다.
        """
        if self.baseline is None:
            return "absent"
        return "thin" if self.baseline.is_thin else "db"


@dataclass
class RuntimeSummary:
    """한 배치의 집계. 실행 로그·AC 확인용."""
    evaluated: int = 0
    detected: int = 0
    #: 1단계(편집)는 통과했는데 조회수가 아직 안 온 윈도우. 저장하지 않는다.
    #: 🔴 미탐과 섞어 세면 "조회수만 오면 잡힐 것" 과 "봤는데 아니었다" 가 구분되지
    #: 않는다 (WP-126). 조회수 투입 경로가 설 때 이 수가 곧 재판정 대상이다.
    pending_views: int = 0
    persisted: int = 0
    baseline_db: int = 0        # 두꺼운 기준선으로 z 경로를 탄 윈도우
    baseline_thin: int = 0      # 기준선은 있으나 sample_days < 7
    baseline_absent: int = 0    # page_baseline 에 행이 없음

    @classmethod
    def of(cls, outcomes: Iterable[DetectionOutcome]) -> RuntimeSummary:
        summary = cls()
        for outcome in outcomes:
            summary.record(outcome)
        return summary

    def record(self, outcome: DetectionOutcome) -> None:
        self.evaluated += 1
        if outcome.decision.is_spike:
            self.detected += 1
        elif outcome.decision.is_pending:
            self.pending_views += 1
        if outcome.persisted:
            self.persisted += 1
        setattr(self, f"baseline_{outcome.baseline_source}",
                getattr(self, f"baseline_{outcome.baseline_source}") + 1)

    def format(self) -> str:
        return (f"윈도우 {self.evaluated:,} / 확정 {self.detected:,} / "
                f"조회수 대기 {self.pending_views:,} / spike 적재 {self.persisted:,}  "
                f"[기준선 db {self.baseline_db:,} · 얇음 {self.baseline_thin:,} · "
                f"없음 {self.baseline_absent:,}]")


class SpikeRuntime:
    """`page_baseline` 조회 → `detect()` → `spike` 적재. LIVE·리플레이 공용.

    `sink` 를 안 주면 판정만 하고 저장하지 않는다(진단·드라이런).
    커밋은 호출자 책임이다 — 여러 윈도우를 한 트랜잭션으로 묶을 수 있게.

    배치 단위는 `iter_process`/`process_all` 한 번이다. 기준선 캐시가 그 단위로 산다
    (아래 `iter_process`). 윈도우를 `process` 로 직접 하나씩 넣으면 캐시는 유지된다 —
    그건 호출자가 명시적으로 고른 경우다.
    """

    def __init__(self, baselines: BaselineRepository, sink: SpikeSink | None = None,
                 candidates=None, *, view_only_gate: bool = False) -> None:
        self._baselines = baselines
        self._sink = sink
        #: 1단계 대체 경로(WP-210). **기본 꺼짐** — 켜면 편집이 없어도
        #: `조회수 >= 100 AND 모바일 >= 25%` 인 윈도우가 1단계를 통과한다.
        #: 🔴 `spike/view_candidates.harvest` 와 **짝이다.** 여기만 켜면 판정은 열리는데
        #:    그런 윈도우가 후보로 들어오지 않아 아무것도 안 바뀐다.
        self._view_only_gate = view_only_gate
        #: 후보 대기 보관소(`spike/candidate_store.CandidateStore`). 없으면 대기를 세기만
        #: 하고 버린다 — 그게 WP-128 이전의 동작이고, LIVE 가 확정을 못 내던 이유다.
        self._candidates = candidates

    def evaluate(self, window: PageWindow) -> DetectionOutcome:
        """판정만 한다. 저장하지 않는다."""
        baseline = self._baselines.get(window.wiki, window.title, window.hour_of_day)
        decision = detect(window.as_detector_window(), baseline,
                          view_only_gate=self._view_only_gate)
        return DetectionOutcome(window=window, baseline=baseline,
                                decision=decision, persisted=False)

    def process(self, window: PageWindow) -> DetectionOutcome:
        """판정하고, **확정이면** `spike` 에 저장한다.

        미탐은 아무 데도 안 남긴다. **후보 대기는 보관소가 있으면 거기 담는다**
        (WP-128) — `spike` 에는 못 넣는다. 2단계까지 통과한 문서만 담는 테이블이라
        대기를 넣으면 조회수를 안 본 문서가 이슈로 노출된다.

        🔴 대기가 아닌 판정이 나면 **보관소에서 지운다.** 재판정으로 확정·폐기된 윈도우가
        남아 있으면 다음 실행이 같은 것을 또 판정하고, 폐기된 것이 영영 안 사라진다.
        """
        outcome = self.evaluate(window)
        if self._candidates is not None:
            self._record_candidate(outcome)
        if not (outcome.decision.is_spike and self._sink is not None):
            return outcome
        self._sink.save(
            wiki=window.wiki,
            title=window.title,
            window_start=window.window_start,
            # 판정 시각 = 윈도우 끝. now() 를 쓰면 과거 재생이 전부 '오늘 감지' 가 된다
            # (spike_sink 독스트링). 결정적이라 재실행에도 값이 안 흔들린다.
            detected_at=window.window_end,
            edit_count=window.edit_count,
            decision=outcome.decision,
            # 판정에 실제로 쓴 값 그대로 (V7, WP-129). 여기서만 둘 다 들고 있다 —
            # decision 은 배수(view_ratio)만 갖고, 원값과 기준선은 입력 쪽에 있다.
            views=window.views,
            view_baseline=outcome.baseline.view_ewma if outcome.baseline else None,
            # 무엇까지 보고 판정했는지 (V9, WP-129 2번). 판정에는 안 들어간다.
            max_rev_id=window.max_rev_id,
            last_edit_ts=window.last_edit_ts,
        )
        return DetectionOutcome(window=outcome.window, baseline=outcome.baseline,
                                decision=outcome.decision, persisted=True)

    def _record_candidate(self, outcome: DetectionOutcome) -> None:
        """후보 대기는 보관하고, 확정·폐기는 보관소에서 지운다.

        page_id 는 싱크가 이미 캐시하고 있다 — 보관만 하는 실행(싱크 없음)에서는
        보관소가 직접 해석한다.
        """
        window = outcome.window
        page_id = self._page_id(window)
        if outcome.decision.is_pending:
            self._candidates.save(page_id, window)
        else:
            self._candidates.drop(page_id, window.window_start)

    def _page_id(self, window: PageWindow) -> int:
        if self._sink is not None:
            return self._sink.page_id(window.wiki, window.title)
        return self._candidates.page_id(window.wiki, window.title)

    def process_all(self, windows: Iterable[PageWindow]) -> RuntimeSummary:
        """여러 윈도우를 한 배치로. 커밋은 호출자가 한 번에 한다."""
        return RuntimeSummary.of(self.iter_process(windows))

    def iter_process(self, windows: Iterable[PageWindow]) -> Iterator[DetectionOutcome]:
        """한 배치를 흘려보낸다. 호출자가 건별로 찍어보고 싶을 때.

        🔴 **배치 시작에서 기준선 캐시를 비운다.** 캐시는 한 배치 안에서만 산다.
        안 그러면 장수명 LIVE 프로세스(`foreachBatch` 가 같은 `SpikeRuntime` 을 계속
        부르는 구조)에서 `page_baseline` 을 재적재해도 **영원히 옛 기준선으로 판정한다** —
        에러 없이 z 만 틀리는 쪽이다. 리플레이는 프로세스가 곧 끝나 원래 안 겪지만,
        LIVE 를 붙일 때 이 함정을 기억해야 하는 구조로 두지 않는다.

        비용은 배치당 문서 수만큼의 왕복이다. 한 배치 안에서는 문서당 24슬롯을 한 번에
        읽어 캐시하므로(`BaselineRepository`), 리플레이 실측 왕복 수는 안 변한다
        (문서당 1회 — 272 윈도우가 아니라).
        """
        self._baselines.invalidate()
        for window in windows:
            yield self.process(window)
