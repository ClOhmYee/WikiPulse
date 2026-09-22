# -*- coding: utf-8 -*-
import json, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
t2w = json.load(open("ticker2wiki.json", encoding="utf-8"))
ours = {}
for line in open("stocks.tsv", encoding="utf-8"):
    if "\t" not in line: continue
    t, n = line.rstrip("\n").split("\t", 1)
    ours[t.strip().upper()] = n.strip()
hit = {t: (t2w[t], ours[t]) for t in ours if t in t2w}
json.dump(hit, open("targets.json", "w", encoding="utf-8"))
print(f"우리 종목 {len(ours)} · 위키 문서 매칭 {len(hit)}")
