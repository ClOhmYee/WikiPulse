# -*- coding: utf-8 -*-
import json, os, sys, time, random, urllib.request, urllib.parse, urllib.error
from concurrent.futures import ThreadPoolExecutor
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
UA = "WikiPulse/0.1 (WikiPulse; wikipulse-WikiPulse@example.com)"
B = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user"
targets = json.load(open("targets.json", encoding="utf-8"))
views = json.load(open("views.json", encoding="utf-8"))
todo = [t for t in targets if not views.get(t)]
print("재시도 대상", len(todo), file=sys.stderr)
stats = {"ok": 0, "404": 0, "fail": 0}

def one(t):
    title = targets[t][0]
    u = f"{B}/{urllib.parse.quote(title.replace(' ', '_'), safe='')}/daily/20260619/20260917"
    for attempt in range(5):
        try:
            r = json.load(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": UA}), timeout=60))
            stats["ok"] += 1
            return t, {i["timestamp"][:8]: i["views"] for i in r["items"]}
        except urllib.error.HTTPError as e:
            if e.code == 404:
                stats["404"] += 1
                return t, {}
            time.sleep(1.5 * (attempt + 1) + random.random())
        except Exception:
            time.sleep(1.5 * (attempt + 1))
    stats["fail"] += 1
    return t, None

with ThreadPoolExecutor(max_workers=3) as ex:
    for i, (t, d) in enumerate(ex.map(one, todo), 1):
        if d is not None:
            views[t] = d
        if i % 300 == 0:
            json.dump(views, open("views.json", "w", encoding="utf-8")); print("…", i, stats, file=sys.stderr)
json.dump(views, open("views.json", "w", encoding="utf-8"))
print("ok", stats["ok"], "404", stats["404"], "fail", stats["fail"])
print("최종 데이터 보유", sum(1 for t in views if views[t]))
