"""sample_days 분포 측정 (WP-88). 측정만 한다 — 코드는 안 고친다.

질문: hour_of_day(24) 슬롯에서 sample_days >= MIN_BASELINE_SAMPLE_DAYS(7) 에
도달하는 문서·슬롯이 얼마나 되나. 슬롯을 넓히면(3h·6h·일) 얼마나 달라지나.

⚠️ 2-pass 다. 1차로 문서별 편집 수만 세고, 2차에서 월 MIN_EDITS_FOR_PASS2 편집 이상
문서만 슬롯별 날짜 집합을 쌓는다. 1-pass 로 전 문서(106만)를 하면 메모리가 터진다 —
MIN_EDITS_FOR_PASS2 를 낮출 때 그 위험이 돌아온다.

    cd data-pipeline && python ../ai/slot-width/slot_dist.py 2025-06 2025-06-01 2025-06-28
"""
import gzip, json, sys
from collections import Counter, defaultdict
from pathlib import Path

from batch.historical_windows import is_bot_edit
from producer.normalize import canonical_title
from spike.detector import MIN_BASELINE_SAMPLE_DAYS as THIN

month = sys.argv[1]
START, END = sys.argv[2], sys.argv[3]          # 28일 창 "YYYY-MM-DD"
MIN_EDITS_FOR_PASS2 = 20

root = Path("out/enwiki") / month
shards = sorted(root.glob("**/part-*.jsonl.gz"))

def events():
    for sh in shards:
        with gzip.open(sh, "rt", encoding="utf-8") as h:
            for line in h:
                if not line.strip():
                    continue
                r = json.loads(line)
                if is_bot_edit(r):
                    continue
                day = r["event_ts"][:10]
                if START <= day <= END:
                    yield canonical_title(r["title"]), day, int(r["event_ts"][11:13])

# pass 1 — 문서별 편집 수
per_title = Counter()
for t, _, _ in events():
    per_title[t] += 1
print(f"[{month}] 창 {START}~{END} · 봇 제외 문서 {len(per_title):,}")

bands = [(1,1),(2,4),(5,9),(10,19),(20,49),(50,99),(100,299),(300,999),(1000,10**9)]
def band_of(n):
    for lo,hi in bands:
        if lo <= n <= hi: return f"{lo}~{hi if hi<10**9 else ''}"
    return "?"
dist = Counter(band_of(n) for n in per_title.values())
print("\n월 편집 수 분포")
for lo,hi in bands:
    k=f"{lo}~{hi if hi<10**9 else ''}"
    print(f"  {k:>10}편집 {dist[k]:>8,} 문서")

# pass 2 — 관심 문서만 슬롯별 관측일 집계
targets = {t for t,n in per_title.items() if n >= MIN_EDITS_FOR_PASS2}
print(f"\n2차 대상(월 {MIN_EDITS_FOR_PASS2}편집 이상) {len(targets):,} 문서")

slots = {w: defaultdict(lambda: defaultdict(set)) for w in (1,3,6,24)}
for t, day, hour in events():
    if t not in targets: continue
    for w in slots:
        slots[w][t][hour // w if w < 24 else 0].add(day)

print(f"\nsample_days >= {THIN} 도달률 (슬롯 폭별)")
print(f"{'슬롯':>6} {'슬롯수':>5} {'슬롯 중 통과':>22} {'문서 중 1개라도 통과':>24}")
for w in (1,3,6,24):
    tot_slot = pass_slot = tot_doc = pass_doc = 0
    for t, per_slot in slots[w].items():
        tot_doc += 1
        ok = 0
        for _, days in per_slot.items():
            tot_slot += 1
            if len(days) >= THIN: ok += 1
        pass_slot += ok
        if ok: pass_doc += 1
    label = {1:"1h(24)",3:"3h(8)",6:"6h(4)",24:"일(1)"}[w]
    print(f"{label:>6} {24//w if w<24 else 1:>5} "
          f"{pass_slot:>8,}/{tot_slot:<8,}={pass_slot/max(tot_slot,1)*100:5.1f}% "
          f"{pass_doc:>8,}/{tot_doc:<8,}={pass_doc/max(tot_doc,1)*100:5.1f}%")

print(f"\n월 편집 수 구간별 — 1h 슬롯에서 문서 중 1개라도 sample_days>={THIN}")
by_band = defaultdict(lambda: [0,0])
for t, per_slot in slots[1].items():
    b = band_of(per_title[t])
    by_band[b][0] += 1
    if any(len(d) >= THIN for d in per_slot.values()): by_band[b][1] += 1
for lo,hi in bands:
    k=f"{lo}~{hi if hi<10**9 else ''}"
    if by_band[k][0]:
        tot,ok = by_band[k]
        print(f"  {k:>10}편집 {ok:>6,}/{tot:<6,} = {ok/tot*100:5.1f}%")

print(f"\n임계 낮추면 (1h 슬롯, 문서 중 1개라도 통과)")
for th in (3,4,5,6,7):
    ok = sum(1 for per_slot in slots[1].values()
             if any(len(d) >= th for d in per_slot.values()))
    print(f"  sample_days>={th}: {ok:>7,}/{len(slots[1]):<7,} = {ok/max(len(slots[1]),1)*100:5.1f}%")
