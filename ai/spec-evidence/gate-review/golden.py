# -*- coding: utf-8 -*-
import json, sys, time, urllib.request, urllib.parse
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
UA = "WikiPulse/0.1 (WikiPulse; wikipulse-WikiPulse@example.com)"
def get(u, tries=4):
    for i in range(tries):
        try: return json.load(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": UA}), timeout=60))
        except Exception: time.sleep(1.2*(i+1))
    return None
PV = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia"
def share(title, day):
    q = urllib.parse.quote(title.replace(" ", "_"), safe="")
    out = {}
    for acc in ("desktop", "mobile-web", "mobile-app"):
        r = get(f"{PV}/{acc}/user/{q}/daily/{day}/{day}")
        out[acc] = r["items"][0]["views"] if r and r.get("items") else 0
    tot = sum(out.values())
    return out, (out["mobile-web"] + out["mobile-app"]) / tot * 100 if tot else 0

print("문서                          DESKTOP    MOB-WEB   MOB-APP   MOBILE%   판정")
cases = [("Air India Flight 171", "20250612", "골든데이 정답"),
         ("Boeing 787 Dreamliner", "20250612", "골든데이 연관"),
         ("Roblox", "20260810", "크롤러"),
         ("Google", "20260818", "크롤러 의심"),
         ("Moderna", "20260819", "실제 사건"),
         ("MRNA-4157/V940", "20260819", "실제 사건")]
for title, day, note in cases:
    o, pct = share(title, day)
    verdict = "통과" if pct >= 25 else "탈락"
    print(f"{title:28.28} {o['desktop']:9,} {o['mobile-web']:9,} {o['mobile-app']:8,}  {pct:6.1f}%   {verdict}  ({note})")
