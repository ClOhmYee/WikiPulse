# -*- coding: utf-8 -*-
import json, sys, time, urllib.request, urllib.parse
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
UA = "WikiPulse/0.1 (WikiPulse; wikipulse-WikiPulse@example.com)"
def get(u, tries=4):
    for i in range(tries):
        try: return json.load(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": UA}), timeout=60))
        except Exception: time.sleep(1.2*(i+1))
    return None
def revs(title, d0, d1):
    r = get("https://en.wikipedia.org/w/api.php?action=query&prop=revisions&titles="
            + urllib.parse.quote(title) +
            f"&rvlimit=40&rvstart={d1}T23:59:59Z&rvend={d0}T00:00:00Z&rvdir=older"
            "&rvprop=timestamp|user|comment&format=json&formatversion=2")
    return r["query"]["pages"][0].get("revisions", []) if r else []
for t in ("Moderna", "Merck & Co.", "Pembrolizumab", "MRNA-4157/V940", "Melanoma"):
    rs = revs(t, "2026-08-18", "2026-08-20")
    human = [r for r in rs if not r.get("user","").lower().endswith("bot")]
    print(f"\n== {t} — 08-18~20 편집 {len(rs)}건 (사람 {len(human)}) ==")
    for r in rs[:6]:
        print(f"   {r['timestamp']}  {r.get('user','?'):18.18} {r.get('comment','')[:72]}")
