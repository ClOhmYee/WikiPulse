# -*- coding: utf-8 -*-
import json, sys, urllib.request, urllib.error
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
UA = "WikiPulse/0.1 (WikiPulse; wikipulse-WikiPulse@example.com)"
B = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia"
def views(access, agent, d="20260810"):
    u = f"{B}/{access}/{agent}/Roblox/daily/{d}/{d}"
    try:
        r = json.load(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": UA}), timeout=60))
        return r["items"][0]["views"]
    except urllib.error.HTTPError as e:
        return f"HTTP {e.code}"

print("== 2026-08-10 Roblox ==")
for agent in ("user", "automated", "spider", "all-agents"):
    row = [f"{agent:11}"]
    for access in ("all-access", "desktop", "mobile-web", "mobile-app"):
        row.append(f"{access}={views(access, agent)!s:>10}")
    print("  " + "  ".join(row))

print("\n== 비교: 평소 (08-09) ==")
for agent in ("user", "automated", "spider"):
    print(f"  {agent:11}  all-access={views('all-access', agent, '20260809')!s:>10}")
