"""2026-07-17~09-17 일별 AQS top-1000 을 받아 '그날만 뜬 문서'를 찾는다."""
import json, os, sys, time, urllib.request, datetime as dt
from collections import defaultdict

UA = "WikiPulse/0.1 (WikiPulse; wikipulse-WikiPulse@example.com)"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "top")
os.makedirs(OUT, exist_ok=True)

start = dt.date(2026, 7, 17)
end = dt.date(2026, 9, 17)

def fetch(d):
    p = os.path.join(OUT, d.isoformat() + ".json")
    if os.path.exists(p):
        return json.load(open(p, encoding="utf-8"))
    url = ("https://wikimedia.org/api/rest_v1/metrics/pageviews/top/"
           f"en.wikipedia/all-access/{d.year}/{d.month:02d}/{d.day:02d}")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.load(r)
    json.dump(data, open(p, "w", encoding="utf-8"))
    time.sleep(0.2)
    return data

days = {}
d = start
while d <= end:
    try:
        data = fetch(d)
        days[d] = {a["article"]: a["views"] for a in data["items"][0]["articles"]}
    except Exception as e:
        print("FAIL", d, e, file=sys.stderr)
    d += dt.timedelta(days=1)

print(f"받은 날 {len(days)}일", file=sys.stderr)
json.dump({k.isoformat(): v for k, v in days.items()},
          open(os.path.join(OUT, "_all.json"), "w", encoding="utf-8"))
