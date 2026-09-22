# -*- coding: utf-8 -*-
import json, sys, datetime as dt, statistics as st
from collections import defaultdict
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
views = json.load(open("views.json", encoding="utf-8"))
targets = json.load(open("targets.json", encoding="utf-8"))
scanned = json.load(open("scanned.json", encoding="utf-8"))
gated = {(r[3], r[4]) for r in scanned if r[6] >= 25 and r[7] >= 1}   # (day, ticker) 통과분

by_day = defaultdict(list)
start, end = dt.date(2026, 7, 17), dt.date(2026, 9, 17)
for t, s in views.items():
    if not s: continue
    d = start
    while d <= end:
        key = d.strftime("%Y%m%d"); v = s.get(key)
        if v:
            base = [s.get((d - dt.timedelta(days=k)).strftime("%Y%m%d"), 0) for k in range(1, 29)]
            base = [x for x in base if x]
            med = st.median(base) if len(base) >= 14 else 0
            if med >= 100 and v / med >= 2:
                by_day[d.isoformat()].append((v / med, t, targets[t][0], v))
        d += dt.timedelta(days=1)

print("같은 날 2배+ 동시 급등 종목 (★ = 두 관문 통과)\n")
rank = sorted(by_day.items(), key=lambda kv: -len(kv[1]))
for day, lst in rank[:10]:
    if len(lst) < 2: continue
    marks = sum(1 for _, t, _, _ in lst if (day, t) in gated)
    print(f"{day}  종목 {len(lst)}개 (통과 {marks})")
    for r, t, a, v in sorted(lst, reverse=True)[:6]:
        star = "★" if (day, t) in gated else " "
        print(f"   {star} {r:5.1f}배 {v:8,}  {t:6} {a}")
    print()
