"""반감기 후보 비교 도구 (WP-59).

Historical Window 산출물(WP-58, baseline 입력)에 반감기 후보를 돌려, 단순평균
대비 기준선이 얼마나 달라지는지 슬롯별로 집계한다. 이 수치로 반감기를 고르고 명세 §11 에
날짜와 함께 기록한다.

    python -m spike.ewma_compare --input ./data/baseline-input/enwiki/2025-06

🔴 실덤프(-56·-57)·HDFS(-28) 적재 전이라 아직 실측 비교를 돌리지 못한다. 이 도구는
   그 데이터가 서면 바로 돌려 확정값을 뽑기 위한 것이다. 확정 전까지 ewma.DEFAULT_HALFLIFE_DAYS
   는 잠정값이다.
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from collections import defaultdict
from collections.abc import Iterable
from datetime import date
from pathlib import Path

from .ewma import CANDIDATE_HALFLIFE_DAYS, Observation, ewma_mean_std


def _day(window_start: str) -> date:
    """window_start "YYYY-MM-DDTHH:00:00" 에서 날짜만."""
    return date.fromisoformat(window_start[:10])


def summarize(
    rows: Iterable[dict], candidates: tuple[float, ...] = CANDIDATE_HALFLIFE_DAYS
) -> dict[float, dict[str, float]]:
    """(wiki,title,slot_index) 슬롯별 관측치를 모아 후보 반감기마다 요약한다.

    각 후보에 대해: 슬롯 수, 평균 edit_ewma, 그리고 단순평균 대비 평균 절대차
    (|가중평균 − 단순평균|). 절대차가 클수록 최근 가중이 단순평균과 다른 답을 준다.
    """
    slots: dict[tuple, list[tuple[date, float]]] = defaultdict(list)
    for row in rows:
        key = (row["wiki"], row["title"], row["slot_index"])
        slots[key].append((_day(row["window_start"]), float(row["edit_count"])))
    if not slots:
        return {h: {"slots": 0, "mean_ewma": 0.0, "mean_abs_diff_vs_simple": 0.0}
                for h in candidates}

    # 나이 기준점 = 데이터 전체에서 가장 최근 날짜(윈도우 끝 근사).
    latest = max(day for obs in slots.values() for day, _ in obs)

    result: dict[float, dict[str, float]] = {}
    for halflife in candidates:
        ewma_sum = 0.0
        diff_sum = 0.0
        for obs in slots.values():
            weighted = [Observation((latest - day).days, val) for day, val in obs]
            mean, _ = ewma_mean_std(weighted, halflife)
            simple = sum(val for _, val in obs) / len(obs)
            ewma_sum += mean
            diff_sum += abs(mean - simple)
        n = len(slots)
        result[halflife] = {
            "slots": n,
            "mean_ewma": round(ewma_sum / n, 4),
            "mean_abs_diff_vs_simple": round(diff_sum / n, 4),
        }
    return result


def read_rows(input_dir: Path) -> Iterable[dict]:
    for shard in sorted(input_dir.glob("**/part-*.jsonl.gz")):
        with gzip.open(shard, "rt", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    yield json.loads(line)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="반감기 후보 비교 (WP-59)")
    p.add_argument("--input", required=True, help="baseline 입력 디렉터리 (-58 산출물)")
    args = p.parse_args(argv)

    input_dir = Path(args.input)
    if not input_dir.exists():
        print(f"--input 경로 없음: {input_dir}", file=sys.stderr)
        return 2

    summary = summarize(read_rows(input_dir))
    print(f"반감기 비교 ({input_dir})")
    print(f"{'반감기(일)':>10} {'슬롯':>8} {'평균 edit_ewma':>16} {'단순평균 대비 절대차':>20}")
    for halflife, stats in summary.items():
        print(f"{halflife:>10.0f} {stats['slots']:>8} "
              f"{stats['mean_ewma']:>16.4f} {stats['mean_abs_diff_vs_simple']:>20.4f}")
    print("\n확정값·근거는 명세 §11 에 날짜와 함께 기록한다 (실데이터로 고른 뒤).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
