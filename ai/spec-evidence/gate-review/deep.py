# -*- coding: utf-8 -*-
import json, sys, time, urllib.request, urllib.parse
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
UA = "WikiPulse/0.1 (WikiPulse; wikipulse-WikiPulse@example.com)"
def get(u, tries=4):
    for i in range(tries):
        try: return json.load(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": UA}), timeout=60))
        except Exception: time.sleep(1.2*(i+1))
    return None
PV = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user"
views = json.load(open("views.json", encoding="utf-8"))

def curve(title, a, b):
    q = urllib.parse.quote(title.replace(" ", "_"), safe="")
    r = get(f"{PV}/{q}/daily/{a}/{b}")
    return {i["timestamp"][:8]: i["views"] for i in r["items"]} if r else {}

def revs(title, day):
    r = get("https://en.wikipedia.org/w/api.php?action=query&prop=revisions&titles="
            + urllib.parse.quote(title) +
            f"&rvlimit=20&rvstart={day}T23:59:59Z&rvend={day}T00:00:00Z&rvdir=older"
            "&rvprop=timestamp|user|comment&format=json&formatversion=2")
    return r["query"]["pages"][0].get("revisions", []) if r else []

print("=== A. Moderna-Merck 흑색종 백신 Phase 3 (2026-08-19~26) ===")
for title in ("Moderna", "Merck_%26_Co.", "Merck & Co.", "Pembrolizumab", "Melanoma", "MRNA-4157/V940"):
    c = curve(title, "20260815", "20260827")
    if not c: print(f"  {title:24} (문서 없음)"); continue
    print(f"  {title:24} " + " ".join(f"{k[6:]}:{v:,}" for k, v in sorted(c.items())))
print("\n  Moderna 08-21 편집:")
for r in revs("Moderna", "2026-08-21"):
    print(f"    {r['timestamp']}  {r.get('user','?'):16.16} {r.get('comment','')[:80]}")

print("\n=== B. Norfolk Southern 합병 (2026-07-25) ===")
for t in ("NSC", "UNP", "CSX", "CP", "CNI"):
    s = views.get(t) or {}
    if s: print(f"  {t:5} " + " ".join(f"{k[6:]}:{s.get(k,0):,}" for k in ("20260723","20260724","20260725","20260726","20260727")))
print("  NSC 07-25 편집:")
for r in revs("Norfolk Southern Railway", "2026-07-25"):
    print(f"    {r['timestamp']}  {r.get('user','?'):16.16} {r.get('comment','')[:80]}")
