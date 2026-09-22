# -*- coding: utf-8 -*-
import gzip, sys
from collections import defaultdict
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
NS = ("User:","User_talk:","Wikipedia:","Wikipedia_talk:","File:","File_talk:","MediaWiki:",
      "MediaWiki_talk:","Template:","Template_talk:","Help:","Help_talk:","Category:",
      "Category_talk:","Portal:","Portal_talk:","Draft:","Draft_talk:","Talk:","Special:",
      "Module:","Module_talk:","TimedText:")
desk, mob = defaultdict(int), defaultdict(int)
with gzip.open("hour.gz", "rt", encoding="utf-8", errors="replace") as f:
    for line in f:
        fs = line.split(" ")
        if len(fs) < 3 or fs[0] not in ("en", "en.m"): continue
        t = fs[1]
        if t == "Main_Page" or any(t.startswith(n) for n in NS): continue
        try: v = int(fs[2])
        except ValueError: continue
        (desk if fs[0] == "en" else mob)[t] += v

tot = {t: desk[t] + mob[t] for t in set(desk) | set(mob)}
top = sorted(tot.items(), key=lambda kv: -kv[1])[:25]
print("2026-09-21 15:00Z · 편집 게이트를 빼면 이 시간 상위에 올라오는 문서\n")
print(f"{'VIEWS':>7} {'MOB%':>6}  ARTICLE")
low = 0
for t, v in top:
    pct = mob[t] / v * 100 if v else 0
    flag = "  ← 봇 의심" if pct < 25 else ""
    if pct < 25: low += 1
    print(f"{v:7,} {pct:5.1f}%  {t[:58]}{flag}")
print(f"\n상위 25개 중 모바일 25% 미만: {low}개")

# 전체 규모에서 봇 의심 비율
for floor in (50, 100, 500):
    sel = [t for t, v in tot.items() if v >= floor]
    bad = sum(1 for t in sel if (mob[t] / tot[t] * 100 if tot[t] else 0) < 25)
    print(f"  {floor:>4}회 이상 {len(sel):>7,}개 중 모바일 25% 미만 {bad:>6,}개 ({bad/len(sel)*100:.0f}%)")
