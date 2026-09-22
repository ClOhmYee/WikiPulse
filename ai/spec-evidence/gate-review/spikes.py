# -*- coding: utf-8 -*-
import json, sys, datetime as dt, statistics as st
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
views = json.load(open("views.json", encoding="utf-8"))
targets = json.load(open("targets.json", encoding="utf-8"))
start, end = dt.date(2026, 7, 17), dt.date(2026, 9, 17)

rows = []
for t, s in views.items():
    if not s: continue
    d = start
    while d <= end:
        key = d.strftime("%Y%m%d")
        v = s.get(key)
        if v:
            base = [s.get((d - dt.timedelta(days=k)).strftime("%Y%m%d"), 0) for k in range(1, 29)]
            base = [x for x in base if x]
            med = st.median(base) if len(base) >= 14 else 0
            if med >= 200 and v / med >= 3:
                rows.append((v / med, v, int(med), d.isoformat(), t, targets[t][0], targets[t][1]))
        d += dt.timedelta(days=1)

print(f"후보 {len(rows)}건 (기준선 200+ · 3배+)\n")
print("RATIO    VIEWS   BASE  DAY         TICKER  ARTICLE")
for r, v, m, d, t, a, n in sorted(rows, reverse=True)[:30]:
    print(f"{r:6.1f} {v:8,} {m:6,}  {d}  {t:6}  {a}")
json.dump(sorted(rows, reverse=True), open("cands.json", "w", encoding="utf-8"))
