"""6h 버킷이 잃는 것 — 시간대 해상도 (WP-88 인수조건 4).

같은 관측에 대해 1h 슬롯 기준선과 6h 슬롯 기준선으로 edit_z 를 각각 내고 비교한다.
기준선 산출은 spike.baseline_rows.build_rows 를 그대로 쓴다(EWMA·28일 창 동일).

    cd data-pipeline && python ../ai/slot-width/slot_cost.py 2025-06
"""
import gzip, json, sys
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

from batch.historical_windows import is_bot_edit
from producer.normalize import canonical_title
from spike.baseline_rows import BASELINE_WINDOW_DAYS, build_rows
from spike.detector import EDIT_Z_THRESHOLD, MIN_BASELINE_SAMPLE_DAYS as THIN

MONTH = sys.argv[1] if len(sys.argv) > 1 else "2025-06"
MIN_EDITS = 100          # 1h 에서 z 경로가 도는 구간(월 100편집 이상, 39.9%)

# (title, day, hour) -> 편집 수
obs = defaultdict(int)
per_title = Counter()
for sh in sorted((Path("out/enwiki")/MONTH).glob("**/part-*.jsonl.gz")):
    with gzip.open(sh, "rt", encoding="utf-8") as h:
        for line in h:
            if not line.strip(): continue
            r = json.loads(line)
            if is_bot_edit(r): continue
            t = canonical_title(r["title"])
            per_title[t] += 1
            obs[(t, r["event_ts"][:10], int(r["event_ts"][11:13]))] += 1

titles = [t for t, n in per_title.items() if n >= MIN_EDITS]
print(f"[{MONTH}] 월 {MIN_EDITS}편집 이상 {len(titles):,} 문서")

def rows_for(title, width):
    out = []
    for (t, day, hour), n in obs.items():
        if t != title: continue
        out.append({"wiki": "enwiki", "title": t,
                    "window_start": f"{day}T{hour:02d}:00:00",
                    "hour_of_day": hour // width, "edit_count": n, "views": None})
    return out

def z_of(count, row):
    if row is None or not row.edit_stddev or row.edit_stddev <= 0:
        return None
    return (count - row.edit_ewma) / row.edit_stddev

by_title_obs = defaultdict(list)
for (t, day, hour), n in obs.items():
    by_title_obs[t].append((day, hour, n))

stat = Counter()
zdiff = []
for t in titles:
    rows1, rows6 = rows_for(t, 1), rows_for(t, 6)
    days = sorted({d for d, _, _ in by_title_obs[t]})
    if len(days) < 10: continue
    as_of = date.fromisoformat(days[-1]) - timedelta(days=1)   # 마지막 날을 판정 대상으로
    target_day = days[-1]
    b1 = {r.hour_of_day: r for r in build_rows(rows1, as_of=as_of)}
    b6 = {r.hour_of_day: r for r in build_rows(rows6, as_of=as_of)}
    for d, hour, n in by_title_obs[t]:
        if d != target_day: continue
        r1, r6 = b1.get(hour), b6.get(hour // 6)
        thin1 = r1 is None or r1.sample_days < THIN
        thin6 = r6 is None or r6.sample_days < THIN
        stat[("thin", thin1, thin6)] += 1
        if thin1 or thin6: continue
        z1, z6 = z_of(n, r1), z_of(n, r6)
        if z1 is None or z6 is None: continue
        zdiff.append((z1, z6))
        stat[("pass", z1 >= EDIT_Z_THRESHOLD, z6 >= EDIT_Z_THRESHOLD)] += 1

print(f"\nz 경로 가능 여부 (판정 대상 윈도우 {sum(v for k,v in stat.items() if k[0]=='thin'):,}개)")
for (kind, a, b), v in sorted(stat.items()):
    if kind != "thin": continue
    print(f"  1h thin={a!s:>5} 6h thin={b!s:>5} : {v:>6,}")

print(f"\n둘 다 z 가능한 윈도우 {len(zdiff):,}개 — 임계 {EDIT_Z_THRESHOLD} 판정 일치")
for (kind, a, b), v in sorted(stat.items()):
    if kind != "pass": continue
    tag = {(True,True):"둘 다 급증", (False,False):"둘 다 아님",
           (True,False):"1h만 급증 (6h 가 놓침)", (False,True):"6h만 급증 (1h 가 놓침)"}[(a,b)]
    print(f"  {tag:<28} {v:>6,}")

if zdiff:
    import statistics
    d = [b - a for a, b in zdiff]
    print(f"\nz 차이 (6h - 1h)  중앙값 {statistics.median(d):+.2f} · "
          f"평균 {statistics.mean(d):+.2f} · 최소 {min(d):+.2f} · 최대 {max(d):+.2f}")
    print(f"  6h 가 더 낮은 비율 {sum(1 for x in d if x < 0)/len(d)*100:.1f}%")
