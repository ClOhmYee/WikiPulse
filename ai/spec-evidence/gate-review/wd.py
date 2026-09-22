# -*- coding: utf-8 -*-
"""NYSE/NASDAQ 상장사의 ticker → enwiki 문서 제목 (CLAUDE.md 의 P414/P249 한정어 규칙)."""
import json, sys, urllib.request, urllib.parse
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
Q = """
SELECT ?ticker ?article WHERE {
  VALUES ?ex { wd:Q13677 wd:Q82059 }
  ?c p:P414 ?st .
  ?st ps:P414 ?ex ; pq:P249 ?ticker .
  ?article schema:about ?c ; schema:isPartOf <https://en.wikipedia.org/> .
}
"""
url = "https://query.wikidata.org/sparql?format=json&query=" + urllib.parse.quote(Q)
req = urllib.request.Request(url, headers={"User-Agent": "WikiPulse/0.1 (WikiPulse; wikipulse-WikiPulse@example.com)"})
d = json.load(urllib.request.urlopen(req, timeout=180))
out = {}
for b in d["results"]["bindings"]:
    t = b["ticker"]["value"].strip().upper()
    title = urllib.parse.unquote(b["article"]["value"].rsplit("/", 1)[-1])
    out.setdefault(t, title)
json.dump(out, open("ticker2wiki.json", "w", encoding="utf-8"))
print("wikidata ticker->enwiki:", len(out))
