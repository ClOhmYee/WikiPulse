"""연속 구간 bulk 리플레이 — Historical Window 전체를 판정해 `spike` 에 적재한다.

WP-109.

    python -m spike.bulk_replay --windows ./data/baseline-input/enwiki/2024-09 \\
        --dsn "$DATABASE_URL"
    python -m spike.bulk_replay --windows ... --since 2024-09-01 --until 2024-09-07
    python -m spike.bulk_replay --windows ... --dry-run          # 저장 없이 판정만

`spike/replay.py` 와 무엇이 다른가
    `replay.py` 는 **회귀 검증** 도구다 — `--title` 로 준 문서만 재생해 임계·수식이
    과거 사건을 잡는지 본다(WP-61). 그래서 제목을 안 주면 아무것도 안 한다.
    이 모듈은 반대다: **구간 안의 모든 문서·모든 윈도우**를 넣는다. 제목 목록을
    받지 않는다 — 받으면 "연속 구간 리플레이" 가 아니라 심어 둔 사건 재생이 된다.

    입력도 다르다. `replay.py` 는 편집 적재본(-56)을 직접 읽어 메모리에서 기준선을
    다시 만들고, 여기는 Historical Window 산출물(-58)을 읽어 `page_baseline`(-60 적재)
    을 조회한다. 즉 이 경로는 LIVE 와 **같은** 런타임(`SpikeRuntime`)·같은 기준선
    소스·같은 싱크를 쓴다. 판정 로직은 한 줄도 새로 쓰지 않는다.

LIVE 와의 대응
    streaming/edit_windows.py  →  PageWindow  →  SpikeRuntime  →  spike(source='live')
    batch/historical_windows   →  PageWindow  →  SpikeRuntime  →  spike(source='replay')
    차이는 윈도우를 만드는 쪽뿐이고, 그 집계 계약은 이미 맞춰져 있다
    (`batch/historical_windows.py` §AC, 대조 회귀 `tests/test_stream_batch_parity.py`).

🔴 기준선을 읽기 전에 거른다 (`detector.may_spike`)
    `SpikeRuntime.evaluate` 는 윈도우마다 기준선을 조회한다(문서당 왕복 1회). 60일
    전체는 문서가 수백만이라 그대로 넣으면 왕복이 문서 수만큼 난다. `may_spike` 는
    **급증의 필요조건**이라 여기서 걸러도 판정 결과가 안 바뀐다 — 근거는 그 함수
    독스트링. 걸러진 수는 `skipped_prefilter` 로 보고한다(숨기지 않는다).

멱등성·재실행
    `SpikeSink` 가 `(source, page_id, window_start)` upsert 라 같은 구간을 다시 돌려도
    행이 안 는다. 중간에 죽으면 그 구간을 다시 돌리면 된다 — 완료 표시는
    `--state` 파일에 남기고, 이미 완료된 (입력, 구간) 은 건너뛴다.

⚠️ `spike` 적재 순서는 아무 의미가 없다. 시점 순서는 `cluster/driver.py` 가
    `detected_at` 오름차순으로 다시 잡는다(그쪽 🔴 항목). 그래서 chunk 를 어떤 순서로
    돌려도 `first_detected_at` 이 흔들리지 않는다.
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import sys
import time
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

from .detector import Window, may_spike
from .runtime import PageWindow, RuntimeSummary, SpikeRuntime
from .spike_sink import require_source

#: 이 CLI 가 쓰는 출처. 정의상 과거 덤프 재생이다 — LIVE 경로는 streaming/live_spike.py.
#: `require_source` 로 import 시점에 검사한다 — 오타가 첫 행을 쓸 때가 아니라 여기서 걸린다.
SOURCE = require_source("replay")

#: 커밋 간격(판정한 윈도우 수). 한 트랜잭션이 너무 길면 실패 시 되돌리는 양이 커지고,
#: 너무 짧으면 왕복이 는다. 실패 복구 단위를 분 단위로 두는 값이다.
DEFAULT_COMMIT_EVERY = 20_000


def read_windows(input_dir: Path) -> Iterator[dict]:
    """-58 산출물 shard 를 흘려보낸다. `baseline_sink.read_windows` 와 같은 규칙."""
    for shard in sorted(input_dir.glob("**/part-*.jsonl.gz")):
        with gzip.open(shard, "rt", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    yield json.loads(line)


def in_range(window_start: str, since: date | None, until: date | None) -> bool:
    """`window_start` 의 날짜가 [since, until] 안인가. 경계 포함."""
    day = date.fromisoformat(window_start[:10])
    if since is not None and day < since:
        return False
    if until is not None and day > until:
        return False
    return True


@dataclass
class BulkCounts:
    """한 실행에서 무슨 일이 있었는지. 매니페스트·로그에 그대로 나간다."""
    read: int = 0                  # shard 에서 읽은 행
    out_of_range: int = 0          # --since/--until 밖
    skipped_prefilter: int = 0     # may_spike 탈락 (기준선 조회 안 함)
    evaluated: int = 0             # detect() 를 실제로 부른 윈도우
    detected: int = 0
    persisted: int = 0
    baseline_db: int = 0
    baseline_thin: int = 0
    baseline_absent: int = 0
    unique_pages_evaluated: int = 0
    elapsed_seconds: float = 0.0
    earliest_window: str | None = None
    latest_window: str | None = None

    def merge_summary(self, summary: RuntimeSummary) -> None:
        self.evaluated += summary.evaluated
        self.detected += summary.detected
        self.persisted += summary.persisted
        self.baseline_db += summary.baseline_db
        self.baseline_thin += summary.baseline_thin
        self.baseline_absent += summary.baseline_absent

    def format(self) -> str:
        return (
            f"읽음 {self.read:,} / 구간 밖 {self.out_of_range:,} / "
            f"사전필터 통과 전 탈락 {self.skipped_prefilter:,}\n"
            f"  판정 {self.evaluated:,} (문서 {self.unique_pages_evaluated:,}) / "
            f"급증 {self.detected:,} / spike 적재 {self.persisted:,}\n"
            f"  기준선 db {self.baseline_db:,} · 얇음 {self.baseline_thin:,} · "
            f"없음 {self.baseline_absent:,}\n"
            f"  윈도우 범위 {self.earliest_window} ~ {self.latest_window} / "
            f"{self.elapsed_seconds:.1f}s"
        )


def candidate_windows(
    rows: Iterator[dict],
    counts: BulkCounts,
    *,
    since: date | None = None,
    until: date | None = None,
) -> Iterator[PageWindow]:
    """-58 행에서 판정 대상 `PageWindow` 만 흘려보낸다. 세는 일도 여기서 한다.

    거르는 순서가 중요하다: 구간 → 사전필터 → PageWindow 생성. 뒤로 갈수록 비싸다
    (PageWindow 는 canonical 변환·tz 검사를 한다).
    """
    for row in rows:
        counts.read += 1
        window_start = row["window_start"]
        if not in_range(window_start, since, until):
            counts.out_of_range += 1
            continue

        views = row.get("views")
        probe = Window(
            edit_count=int(row["edit_count"]),
            editor_count=int(row.get("editor_count") or 0),
            views=None if views is None else int(views),
        )
        if not may_spike(probe):
            counts.skipped_prefilter += 1
            continue

        if counts.earliest_window is None or window_start < counts.earliest_window:
            counts.earliest_window = window_start
        if counts.latest_window is None or window_start > counts.latest_window:
            counts.latest_window = window_start
        yield PageWindow.from_row(row)


def run(
    conn,
    input_dir: Path,
    *,
    since: date | None = None,
    until: date | None = None,
    dry_run: bool = False,
    commit_every: int = DEFAULT_COMMIT_EVERY,
    progress_every: int = 0,
) -> BulkCounts:
    """한 입력 디렉터리(구간)를 통째로 판정하고 적재한다. 커밋은 여기서 한다.

    `dry_run` 이면 싱크를 안 달아 판정만 한다 — 기준선 조회는 그대로 일어나므로
    "몇 건이 급증으로 잡히는지" 를 저장 없이 볼 수 있다.
    """
    from .baseline_repository import BaselineRepository
    from .spike_sink import SpikeSink

    started = time.monotonic()
    counts = BulkCounts()
    sink = None if dry_run else SpikeSink(conn, source=SOURCE)
    runtime = SpikeRuntime(BaselineRepository(conn), sink)

    seen_pages: set[tuple[str, str]] = set()
    windows = candidate_windows(read_windows(input_dir), counts,
                                since=since, until=until)

    since_commit = 0
    summary = RuntimeSummary()
    for outcome in runtime.iter_process(windows):
        summary.record(outcome)
        seen_pages.add((outcome.window.wiki, outcome.window.title))
        since_commit += 1
        if progress_every and summary.evaluated % progress_every == 0:
            print(f"    … 판정 {summary.evaluated:,} / 급증 {summary.detected:,} "
                  f"/ 읽음 {counts.read:,}", flush=True)
        if not dry_run and since_commit >= commit_every:
            conn.commit()
            since_commit = 0

    if not dry_run:
        conn.commit()

    counts.merge_summary(summary)
    counts.unique_pages_evaluated = len(seen_pages)
    counts.elapsed_seconds = round(time.monotonic() - started, 1)
    return counts


def state_key(input_dir: Path, since: date | None, until: date | None) -> str:
    """완료 표시 키. 같은 입력·같은 구간이면 같은 키다."""
    return f"{input_dir.as_posix()}|{since or '-'}|{until or '-'}"


def load_state(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def _parse_day(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"YYYY-MM-DD 형식이어야 한다: {value!r}") from exc


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="연속 구간 bulk 리플레이 — Historical Window 전체 → spike (WP-109)")
    p.add_argument("--windows", required=True,
                   help="Historical Window 산출물 디렉터리 (-58)")
    p.add_argument("--since", type=_parse_day, help="처리 시작일 YYYY-MM-DD (포함)")
    p.add_argument("--until", type=_parse_day, help="처리 종료일 YYYY-MM-DD (포함)")
    p.add_argument("--dsn", default=os.environ.get("DATABASE_URL", ""),
                   help="PostgreSQL DSN (기본: $DATABASE_URL)")
    p.add_argument("--dry-run", action="store_true", help="적재 없이 판정만")
    p.add_argument("--commit-every", type=int, default=DEFAULT_COMMIT_EVERY,
                   help=f"몇 윈도우마다 커밋할지 (기본 {DEFAULT_COMMIT_EVERY:,})")
    p.add_argument("--progress-every", type=int, default=0,
                   help="N 윈도우마다 진행 상황 출력 (0이면 끔)")
    p.add_argument("--state", help="완료 chunk 를 기록할 JSON 경로")
    p.add_argument("--force", action="store_true",
                   help="이미 완료로 기록된 chunk 도 다시 돌린다")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    input_dir = Path(args.windows)
    if not input_dir.exists():
        print(f"--windows 경로 없음: {input_dir}", file=sys.stderr)
        return 2
    if args.since and args.until and args.since > args.until:
        print(f"--since({args.since}) 가 --until({args.until}) 보다 뒤다", file=sys.stderr)
        return 2
    # dry-run 도 DSN 이 필요하다 — 판정이 `page_baseline` 을 읽어야 해서다.
    # 안 쓰는 건 싱크(적재)뿐이다. `baseline_sink --dry-run` 과 다른 점이라 여기 적는다.
    if not args.dsn:
        print("DSN 이 없다. --dsn 또는 $DATABASE_URL 을 준다 "
              "(--dry-run 도 기준선 조회에 DB 가 필요하다).", file=sys.stderr)
        return 2

    state_path = Path(args.state) if args.state else None
    key = state_key(input_dir, args.since, args.until)
    state = load_state(state_path) if state_path else {}
    if state.get(key) and not args.force:
        print(f"이미 완료된 chunk 다 — 건너뜀: {key}\n  {state[key]}")
        return 0

    import psycopg     # 판정에 기준선이 필요해 dry-run 도 DB 를 쓴다

    print(f"chunk {key}  (source={SOURCE})", flush=True)
    with psycopg.connect(args.dsn) as conn:
        counts = run(conn, input_dir,
                     since=args.since, until=args.until,
                     dry_run=args.dry_run,
                     commit_every=args.commit_every,
                     progress_every=args.progress_every)

    print(counts.format())
    if counts.read == 0:
        print("⚠️ 읽은 행이 0이다 — --windows 경로에 part-*.jsonl.gz 가 있는지 확인한다.",
              file=sys.stderr)
        return 1

    if state_path and not args.dry_run:
        state[key] = {"finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                      **asdict(counts)}
        save_state(state_path, state)
        print(f"완료 기록: {state_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
