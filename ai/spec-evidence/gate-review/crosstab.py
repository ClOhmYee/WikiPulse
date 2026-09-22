# -*- coding: utf-8 -*-
import json, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
S = json.load(open("scanned.json", encoding="utf-8"))
# r = (ratio, views, med, day, ticker, article, mobile%, human_edits, comment)
def cnt(f): return sum(1 for r in S if f(r))
edit = lambda r: r[7] >= 1
mob  = lambda r: r[6] >= 25
print(f"급등 후보 {len(S)}건 (기준선 200+ · 3배+)\n")
print(f"  편집 게이트만          통과 {cnt(edit):3}  ({cnt(edit)/len(S)*100:.0f}%)")
print(f"  모바일 게이트만        통과 {cnt(mob):3}  ({cnt(mob)/len(S)*100:.0f}%)")
print(f"  둘 다                  통과 {cnt(lambda r: edit(r) and mob(r)):3}")
print(f"  편집 X · 모바일 O      {cnt(lambda r: not edit(r) and mob(r)):3}   ← 편집 게이트가 버리는 사람 트래픽")
print(f"  편집 O · 모바일 X      {cnt(lambda r: edit(r) and not mob(r)):3}   ← 편집은 있으나 크롤러 급등")
print(f"  둘 다 X                {cnt(lambda r: not edit(r) and not mob(r)):3}\n")
print("편집 게이트가 버리는 것 중 큰 것 (모바일 25%+, 편집 0):")
print("RATIO   VIEWS   DAY         TICKER  MOB%   ARTICLE")
for r in sorted([r for r in S if not edit(r) and mob(r)], reverse=True)[:14]:
    print(f"{r[0]:6.1f} {r[1]:7,}  {r[3]}  {r[4]:6} {r[6]:5.1f}%  {r[5]}")
