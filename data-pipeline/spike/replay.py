"""과거 사건 리플레이 회귀 검증 (WP-61).

편집 적재본(WP-56)을 시간 윈도우로 집계하고, 각 시점마다 **그 이전 28일**로
기준선을 만들어 detect() 를 돌린다. 과거 실사건이 실제로 잡히는지, 대조군에서 오탐이
나지 않는지 확인한다.

    python -m spike.replay --edits ./out/enwiki/2025-06 \
        --title Strait_of_Hormuz --title Hurricane_Milton --control Cat

왜 이 스토리가 필요한가
    WP-38 의 근거는 **Strait of Hormuz 조회수 한 사건**이고, 기존 문서
    테스트 13개는 전부 조회수 숫자를 편집수 자리에 대입한 것이다
    (`edit_ewma=391, edit_count=9836`). 즉 **편집 분포로는 검증된 적이 없다.**
    이 모듈이 그 공백을 메운다.

🔴 불일치를 발견해도 고치지 않는다
    임계값·수식은 WP-38 확정 자산이다. 리플레이가 기대와 다르면 여기서
    조정하지 말고 **이슈로 등록한다**(명세 §3.2 3번 대비 detector 의 VIEW_Z_THRESHOLD
    미사용이 이미 알려진 예다).

editor_count 는 여기서 직접 센다
    edit_event 를 직접 읽어 서로 다른 편집자 수를 함께 센다. **detect() 의 편집 관문이
    이 값을 본다** (MIN_DISTINCT_EDITORS, WP-85) — 1인 연속 편집을 급증에서
    빼기 위해서다. 신규 문서 spike_score 에도 쓰인다.
    🔴 스트리밍은 approx_count_distinct 라 근사값이고 여기는 정확값이라 **두 값이 갈린다.**
    ~~편집자 1~10명 구간에서 일치함을 실측(불일치 0건)~~ → 표본 200,000 events 로는
    21건 불일치였고 그중 13건이 `2 → 1` 로 편집자 하한을 뒤집었다
    (2026-09-15, WP-83). → rsd=0.01 로 확정해 불일치 0건이 됐다
    (WP-89). 리플레이(정확값)와 스트리밍 판정이 이제 같은 답을 낸다.
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from collections import defaultdict
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from batch.historical_windows import floor_to_hour, hour_of_day, is_bot_edit
from producer.normalize import canonical_title
from .baseline_rows import BASELINE_WINDOW_DAYS, build_rows
from .detector import Baseline, SpikeDecision, Window, detect
from .ewma import DEFAULT_HALFLIFE_DAYS


@dataclass(frozen=True)
class Observation:
    """한 문서의 한 시간 윈도우 관측치."""
    wiki: str
    title: str
    window_start: str        # "YYYY-MM-DDTHH:00:00" (UTC)
    edit_count: int
    editor_count: int
    #: 시점 감사 증거 (V9, WP-129 2번). 판정에는 안 쓴다.
    #: 🔴 리플레이가 이 증거의 주 대상이다 — "snapshot_ts 이하 revision 만 썼다" 를
    #: 나중에 보이려면 무엇까지 봤는지가 결과에 남아 있어야 한다.
    max_rev_id: int | None = None
    last_edit_ts: str | None = None

    @property
    def day(self) -> date:
        return date.fromisoformat(self.window_start[:10])

    @property
    def hour_of_day(self) -> int:
        return hour_of_day(self.window_start)


@dataclass(frozen=True)
class ReplayResult:
    """한 시점의 판정 결과. §11 에 적는 값이 여기서 나온다."""
    title: str
    window_start: str
    edit_count: int
    editor_count: int
    baseline_sample_days: int | None
    decision: SpikeDecision


def read_edit_events(edits_dir: Path) -> Iterator[dict]:
    """편집 적재본(WP-56) shard 를 흘려보낸다."""
    for shard in sorted(edits_dir.glob("**/part-*.jsonl.gz")):
        with gzip.open(shard, "rt", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    yield json.loads(line)


def aggregate(events: Iterable[dict], titles: set[str]) -> dict[str, list[Observation]]:
    """관심 문서만 (wiki, title, 정각) 으로 집계한다. 봇은 제외 — 스트리밍과 같은 판정.

    제목은 **밑줄·공백 아무 형태로나** 줘도 된다. 요청 제목과 레코드 제목을 둘 다
    `canonical_title` 로 맞춘 뒤 비교하고, 결과 키도 canonical(공백형)로 낸다.

    ~~제목은 덤프 원형(밑줄)이다~~ → 덤프 세대가 둘이다 (2026-09-15, WP-91).
    `normalize_dump` 가 WP-79 부터 공백형을 내므로, 재생성 전 적재본(밑줄)과
    재생성 후 적재본(공백)이 섞여 돈다. 형식이 어긋나면 **"관측 없음"** 으로 끝나는데,
    그게 "그 문서는 급증이 없었다" 로 읽히기 쉽다 — 조용히 틀리는 쪽이라 여기서 흡수한다.
    """
    # (wiki, title, hour) -> [편집 수, {편집자}]
    acc: dict[tuple[str, str, str], tuple[list[int], set[str]]] = defaultdict(
        lambda: ([0], set()))
    # 시점 증거. 배치 집계(`batch/historical_windows.aggregate_edits`)와 같은 규칙이다.
    max_rev: dict[tuple[str, str, str], int] = {}
    last_ts: dict[tuple[str, str, str], str] = {}
    wanted = {canonical_title(t) for t in titles}
    for rec in events:
        raw_title = rec.get("title")
        if raw_title is None:
            continue
        title = canonical_title(raw_title)
        if title not in wanted or is_bot_edit(rec):
            continue
        key = (rec["wiki"], title, floor_to_hour(rec["event_ts"]))
        count, editors = acc[key]
        count[0] += 1
        if rec.get("user"):
            editors.add(rec["user"])
        rev_id = rec.get("rev_id")
        if rev_id is not None:
            max_rev[key] = max(max_rev.get(key, 0), int(rev_id))
        event_ts = rec.get("event_ts")
        if event_ts is not None and event_ts > last_ts.get(key, ""):
            last_ts[key] = event_ts

    by_title: dict[str, list[Observation]] = defaultdict(list)
    for (wiki, title, hour), (count, editors) in acc.items():
        key = (wiki, title, hour)
        by_title[title].append(Observation(
            wiki, title, hour, count[0], len(editors),
            max_rev_id=max_rev.get(key), last_edit_ts=last_ts.get(key)))
    for obs in by_title.values():
        obs.sort(key=lambda o: o.window_start)
    return by_title


def _as_windows(observations: Iterable[Observation]) -> list[dict]:
    """build_rows 가 먹는 형태로. 조회수는 이 경로에 없다(편집 덤프만)."""
    return [{"wiki": o.wiki, "title": o.title, "window_start": o.window_start,
             "hour_of_day": o.hour_of_day, "edit_count": o.edit_count, "views": None}
            for o in observations]


def baseline_at(
    observations: list[Observation], target: Observation, halflife_days: float
) -> Baseline | None:
    """target 시점 **직전까지**의 관측으로 그 슬롯의 기준선을 만든다.

    target 자신과 같은 날 이후는 쓰지 않는다 — 판정 대상이 자기 기준선에 들어가면
    급증이 평소로 희석된다(미탐). 창은 (as_of-28, as_of], as_of = target 전날.
    """
    as_of = target.day - timedelta(days=1)
    oldest = as_of - timedelta(days=BASELINE_WINDOW_DAYS)
    prior = [o for o in observations
             if o.hour_of_day == target.hour_of_day and oldest < o.day <= as_of]
    if not prior:
        return None          # 그 슬롯에 과거 관측이 없다 -> 신규 문서 경로

    rows = build_rows(_as_windows(prior), as_of=as_of, halflife_days=halflife_days)
    if not rows:
        return None
    row = rows[0]
    return Baseline(row.edit_ewma, row.edit_stddev, row.view_ewma, row.sample_days,
                    row.view_stddev)


def replay_title(
    observations: list[Observation], halflife_days: float = DEFAULT_HALFLIFE_DAYS
) -> list[ReplayResult]:
    """한 문서의 모든 관측 윈도우를 시간순으로 판정한다.

    조회수는 없다(편집 덤프만 재생) — detect() 는 views=None 이면 편집만으로 '감지됨'
    까지 낸다. 조회수 판정(확정)은 이 경로 밖이다.

    ⚠️ 기존 문서 경로가 AND -> OR 로 바뀌었지만(WP-90) **이 재생 결과는 안 변한다** —
    views=None 이면 조회수 관문이 닫혀 편집 단독 판정과 같아지기 때문이다. 바꾼 뒤 숫자가
    변했다면 OR 구현이 틀린 것이다(회귀 확인점).
    """
    results = []
    for obs in observations:
        baseline = baseline_at(observations, obs, halflife_days)
        decision = detect(
            Window(edit_count=obs.edit_count, editor_count=obs.editor_count, views=None),
            baseline,
        )
        results.append(ReplayResult(
            title=obs.title,
            window_start=obs.window_start,
            edit_count=obs.edit_count,
            editor_count=obs.editor_count,
            baseline_sample_days=None if baseline is None else baseline.sample_days,
            decision=decision,
        ))
    return results


def first_detection(results: Iterable[ReplayResult]) -> ReplayResult | None:
    """가장 이른 **확정**. '사건 시작 시점에 잡히는가'(미탐 없음)를 본다.

    🔴 **조회수 없이 재생하면 항상 None 이다** (2026-09-18, WP-126).
    2단계 계약에서 확정은 조회수 급등을 요구하는데 편집 덤프에는 조회수가 없다.
    이 경로로 재현율을 재던 수치(WP-85: 10/12)는 더는 못 낸다 —
    `first_candidate` 로 1단계 통과 시점만 볼 수 있다.
    """
    for result in results:
        if result.decision.is_spike:
            return result
    return None


def first_candidate(results: Iterable[ReplayResult]) -> ReplayResult | None:
    """가장 이른 **후보**(1단계 통과, 조회수 대기). 편집 신호가 언제 섰는지 본다.

    확정이 아니다. 조회수를 붙이기 전까지 리플레이로 볼 수 있는 건 여기까지다.
    """
    for result in results:
        if result.decision.is_spike or result.decision.is_pending:
            return result
    return None


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="과거 사건 리플레이 회귀 검증 (WP-61)")
    p.add_argument("--edits", required=True, help="편집 적재본 디렉터리 (-56)")
    p.add_argument("--title", action="append", default=[],
                   help="검증할 문서. 밑줄·공백 아무 형태로나 준다. 여러 번 줄 수 있다")
    p.add_argument("--control", action="append", default=[],
                   help="대조군 문서. 오탐이 나면 안 되는 쪽")
    p.add_argument("--halflife-days", type=float, default=DEFAULT_HALFLIFE_DAYS)
    p.add_argument("--max-rows", type=int, default=10,
                   help="문서당 출력할 급증 판정 건수")
    # ⚠️ $DATABASE_URL 로 기본값을 채우지 않는다. baseline_sink 는 어차피 DSN 이
    # 필수라 그래도 되지만, 여기서는 DSN 유무가 **동작을 바꾼다** — 환경변수만으로
    # 회귀 검증이 DB 모드로 넘어가면 그게 바로 조용히 틀리는 경로다. 명시 opt-in 만.
    p.add_argument("--dsn", default="",
                   help="PostgreSQL DSN. 주면 DB 모드(WP-94) — page_baseline 을 "
                        "읽어 판정하고 spike 에 적재한다. 없으면 기존 메모리 재생 그대로")
    return p


def run_db_mode(by_title: dict[str, list[Observation]], targets: list[str],
                args: argparse.Namespace) -> int:
    """DB 모드 — `page_baseline` 을 읽어 판정하고 `spike` 에 적재한다 (WP-94).

    🔴 `baseline_at()` 을 **부르지 않는다.** 메모리에서 기준선을 다시 만들어 놓고 결과만
    저장하면 "`page_baseline` 을 읽는다" 는 이 스토리의 목적이 통째로 빠진다. 기준선은
    `BaselineRepository` 에서만 온다.

    ⚠️ 그래서 판정이 메모리 모드와 다를 수 있다 — 두 기준선의 창이 다르다(`runtime.py`
    상단). 메모리 모드는 임계·수식 회귀 검증, DB 모드는 런타임 경로 검증이다.
    """
    import psycopg     # DB 모드에서만 필요 — 기존 경로는 드라이버 없이도 돈다

    from .baseline_repository import BaselineRepository
    from .runtime import PageWindow, RuntimeSummary, SpikeRuntime, parse_window_start
    from .spike_sink import SpikeSink

    exit_code = 0
    with psycopg.connect(args.dsn) as conn:
        # 🔴 출처를 명시한다. 이 CLI 는 정의상 과거 덤프 재생이다 — LIVE 경로
        # (streaming/live_spike.py)가 같은 테이블에 source='live' 로 쓴다.
        # 키에 source 가 들어가므로(V5) 두 출처가 서로 덮어쓰지 않는다.
        runtime = SpikeRuntime(BaselineRepository(conn),
                               SpikeSink(conn, source="replay"))

        for title in targets:
            kind = "대조군" if title in args.control else "검증"
            observations = by_title.get(canonical_title(title), [])
            if not observations:
                print(f"\n[{kind}] {title} - 관측 없음 (제목/구간 확인)")
                exit_code = 1
                continue

            windows = [
                PageWindow(
                    wiki=o.wiki, title=o.title,
                    window_start=parse_window_start(o.window_start),
                    edit_count=o.edit_count, editor_count=o.editor_count,
                    # 편집 덤프에는 조회수가 없다 — 메모리 모드와 같은 조건이다.
                    views=None,
                    # 무엇까지 보고 판정했는지 (V9, WP-129 2번).
                    max_rev_id=o.max_rev_id,
                    last_edit_ts=(None if o.last_edit_ts is None
                                  else parse_window_start(o.last_edit_ts)),
                )
                for o in observations
            ]
            outcomes = list(runtime.iter_process(windows))

            print(f"\n[{kind}] {title}  (DB 모드)")
            print(f"  {RuntimeSummary.of(outcomes).format()}")
            for outcome in [o for o in outcomes if o.decision.is_spike][:args.max_rows]:
                d, w, b = outcome.decision, outcome.window, outcome.baseline
                # 🔴 기준선 출처와 그 값을 그대로 찍는다 — 판정이 page_baseline 을 탔다는 증거.
                evidence = ("기준선 없음(absent)" if b is None else
                            f"기준선 {outcome.baseline_source} ewma {b.edit_ewma:.2f} "
                            f"sd {'-' if b.edit_stddev is None else format(b.edit_stddev, '.2f')} "
                            f"일수 {b.sample_days}")
                print(f"    {w.window_start.isoformat()}  편집 {w.edit_count:>4} "
                      f"편집자 {w.editor_count:>3}  "
                      f"z {'-' if d.edit_z is None else format(d.edit_z, '.2f'):>7}  "
                      f"score {d.spike_score:>7.2f}  {evidence}")
        conn.commit()
    return exit_code


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    edits_dir = Path(args.edits)
    if not edits_dir.exists():
        print(f"--edits 경로 없음: {edits_dir}", file=sys.stderr)
        return 2

    targets = list(args.title) + list(args.control)
    if not targets:
        print("--title 또는 --control 을 하나 이상 준다.", file=sys.stderr)
        return 2

    by_title = aggregate(read_edit_events(edits_dir), set(targets))

    if args.dsn:
        return run_db_mode(by_title, targets, args)

    exit_code = 0
    for title in targets:
        kind = "대조군" if title in args.control else "검증"
        # by_title 키는 canonical(공백형)이다 — 사용자가 밑줄로 줬어도 찾아진다.
        observations = by_title.get(canonical_title(title), [])
        if not observations:
            print(f"\n[{kind}] {title} - 관측 없음 (제목/구간 확인)")
            exit_code = 1
            continue

        results = replay_title(observations, args.halflife_days)
        spikes = [r for r in results if r.decision.is_spike]
        first = first_detection(results)

        print(f"\n[{kind}] {title}")
        print(f"  관측 윈도우 {len(results):,} / 급증 판정 {len(spikes):,}")
        if first:
            d = first.decision
            print(f"  최초 탐지 {first.window_start} / 편집 {first.edit_count} "
                  f"/ edit_z {d.edit_z if d.edit_z is None else round(d.edit_z, 2)} "
                  f"/ score {d.spike_score} / 신규문서 {d.is_new_page}")
            print(f"    사유: {d.reason}")
        else:
            print("  탐지 없음")

        for r in spikes[:args.max_rows]:
            d = r.decision
            print(f"    {r.window_start}  편집 {r.edit_count:>4} "
                  f"편집자 {r.editor_count:>3}  "
                  f"z {'-' if d.edit_z is None else format(d.edit_z, '.2f'):>7}  "
                  f"score {d.spike_score:>6}  "
                  f"baseline일수 {r.baseline_sample_days}")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
