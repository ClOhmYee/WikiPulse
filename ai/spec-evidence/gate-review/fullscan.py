# -*- coding: utf-8 -*-
import json, sys, time, urllib.request, urllib.parse
from concurrent.futures import ThreadPoolExecutor
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
UA = "WikiPulse/0.1 (WikiPulse; wikipulse-WikiPulse@example.com)"
def get(u, tries=4):
    for i in range(tries):
        try:
            return json.load(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": UA}), timeout=60))
        except Exception:
            time.sleep(1.2 * (i + 1))
    return None
PV = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia"

cands = json.load(open("cands.json", encoding="utf-8"))
def check(c):
    ratio, v, med, day, t, title, name = c
    dd = day.replace("-", "")
    q = urllib.parse.quote(title.replace(" ", "_"), safe="")
    mo = get(f"{PV}/mobile-web/user/{q}/daily/{dd}/{dd}")
    de = get(f"{PV}/desktop/user/{q}/daily/{dd}/{dd}")
    mo = mo["items"][0]["views"] if mo and mo.get("items") else 0
    de = de["items"][0]["views"] if de and de.get("items") else 0
    tot = mo + de
    pct = mo / tot * 100 if tot else 0
    r = get("https://en.wikipedia.org/w/api.php?action=query&prop=revisions&titles="
            + urllib.parse.quote(title) +
            f"&rvlimit=50&rvstart={day}T23:59:59Z&rvend={day}T00:00:00Z&rvdir=older"
            "&rvprop=timestamp|user|comment&format=json&formatversion=2")
    revs = r["query"]["pages"][0].get("revisions", []) if r else []
    human = [x for x in revs if not x.get("user","").lower().endswith("bot")]
    return (ratio, v, med, day, t, title, pct, len(human),
            human[0].get("comment","")[:60] if human else "")

with ThreadPoolExecutor(max_workers=3) as ex:
    res = list(ex.map(check, cands))
json.dump(res, open("scanned.json", "w", encoding="utf-8"))

ok = [r for r in res if r[6] >= 25 and r[7] >= 1]     # 모바일 25%+ (크롤러 배제) · 사람 편집 1+
print(f"후보 {len(res)} → 두 관문 통과 {len(ok)}\n")
print("RATIO   VIEWS   BASE  DAY         TICKER  MOB%  EDIT  ARTICLE / 편집요약")
for r, v, m, d, t, a, pct, ne, cm in sorted(ok, reverse=True):
    print(f"{r:6.1f} {v:7,} {m:6,}  {d}  {t:6} {pct:5.1f}% {ne:5}  {a} | {cm}")
