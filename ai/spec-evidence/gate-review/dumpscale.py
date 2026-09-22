# -*- coding: utf-8 -*-
import gzip, io, os, sys, urllib.request
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
UA = "WikiPulse/0.1 (WikiPulse; wikipulse-WikiPulse@example.com)"
url = "https://dumps.wikimedia.org/other/pageviews/2026/2026-09/pageviews-20260921-150000.gz"
p = "hour.gz"
if not os.path.exists(p):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=300) as r, open(p, "wb") as f:
        while True:
            b = r.read(1 << 20)
            if not b: break
            f.write(b)
print("파일", os.path.getsize(p) // 1024 // 1024, "MB", file=sys.stderr)

NS = ("User:", "User_talk:", "Wikipedia:", "Wikipedia_talk:", "File:", "File_talk:",
      "MediaWiki:", "MediaWiki_talk:", "Template:", "Template_talk:", "Help:", "Help_talk:",
      "Category:", "Category_talk:", "Portal:", "Portal_talk:", "Draft:", "Draft_talk:",
      "Talk:", "Special:", "Module:", "Module_talk:", "TimedText:")
buckets = [1, 10, 50, 100, 500, 1000]
cnt = {b: 0 for b in buckets}
rows = views = 0
with gzip.open(p, "rt", encoding="utf-8", errors="replace") as f:
    for line in f:
        fs = line.split(" ")
        if len(fs) < 3 or fs[0] not in ("en", "en.m"):
            continue
        t = fs[1]
        if t == "Main_Page" or any(t.startswith(n) for n in NS):
            continue
        try: v = int(fs[2])
        except ValueError: continue
        rows += 1; views += v
        for b in buckets:
            if v >= b: cnt[b] += 1
print(f"\n2026-09-21 15:00Z 한 시간 · enwiki ns0 (en + en.m)")
print(f"  행 {rows:,} · 조회수 {views:,}")
for b in buckets:
    print(f"  시간당 {b:>4}회 이상 문서: {cnt[b]:>9,}")
