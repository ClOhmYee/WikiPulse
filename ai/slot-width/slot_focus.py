"""-85 대상·대조군이 슬롯 폭별로 z 경로를 타는지 (WP-88 측정).
⚠️ 여기 값은 **4개월 전체 최대치라 상한**이다(28일 창을 안 건다). 28일 창을 적용한 건
slot_dist.py 뿐이다. 판정 기준으로 쓰려면 창을 걸어야 한다.

    cd data-pipeline && python ../ai/slot-width/slot_focus.py
"""
import gzip, json
from collections import defaultdict
from pathlib import Path
from batch.historical_windows import is_bot_edit
from producer.normalize import canonical_title
from spike.detector import MIN_BASELINE_SAMPLE_DAYS as THIN

MONTHS = ["2025-05", "2025-06", "2024-09", "2024-10"]
TARGETS = ["Air India Flight 171","June 2025 Israeli strikes on Iran",
  "June 2025 Los Angeles protests","2025 shootings of Minnesota legislators",
  "American strikes on Iranian nuclear sites","Strait of Hormuz",
  "2025 Iran threat of Strait of Hormuz closure","Hurricane Milton","Liam Payne",
  "Ratan Tata","October 2024 Iranian strikes against Israel","Hurricane Helene"]
CONTROLS = ["List of people named Peter","Deaths in 2025","Deaths in 2024",
  "Timeline of science fiction","Association football","Cat","India","YouTube",
  "World War II","Chess","Taylor Swift","The Beatles","Elizabeth II","Solar System"]
want = set(TARGETS) | set(CONTROLS)

# (title, width, slot) -> {day}
acc = {w: defaultdict(lambda: defaultdict(set)) for w in (1,3,6,24)}
for m in MONTHS:
    for sh in sorted((Path("out/enwiki")/m).glob("**/part-*.jsonl.gz")):
        with gzip.open(sh,"rt",encoding="utf-8") as h:
            for line in h:
                if not line.strip(): continue
                r = json.loads(line)
                if is_bot_edit(r): continue
                t = canonical_title(r["title"])
                if t not in want: continue
                day, hour = r["event_ts"][:10], int(r["event_ts"][11:13])
                for w in acc:
                    acc[w][t][hour // w if w < 24 else 0].add(day)

def best(t, w):
    """그 문서의 최대 sample_days (창 필터 없이 4개월 전체 — 상한값)."""
    return max((len(d) for d in acc[w][t].values()), default=0)

for label, titles in (("대상", TARGETS), ("대조군", CONTROLS)):
    print(f"\n=== {label} — 최대 sample_days (4개월 전체, 상한) · z 경로 가능 여부 ===")
    print(f"{'문서':46s} {'1h':>5} {'3h':>5} {'6h':>5} {'일':>5}")
    for t in titles:
        vals = [best(t, w) for w in (1,3,6,24)]
        mark = lambda v: f"{v:>4}{'*' if v>=THIN else ' '}"
        print(f"{t:46s} " + " ".join(mark(v) for v in vals))
    print(f"  * = sample_days >= {THIN} (z 경로 가능)")
