"""§11 "위키 링크 그래프 → 상장기업" 행 재현. 이슈 문서의 1-hop 이웃(아웃링크+
백링크)을 Wikidata NYSE·NASDAQ 상장기업과 조인해 몇 개가 걸리는지 본다.
CLAUDE.md 폐기 절 "이슈-종목 매핑을 Equi-Join 단독으로" 근거 스크립트.

실행: 네트워크만 필요(Wikipedia API + Wikidata Query Service).
    py -3 wiki_link_graph_join.py [문서 제목...]   # 기본: 4개 사건/대조군 문서
"""

import sys

import requests

UA = "WikiPulse/0.1 (WikiPulse research; https://github.com/ClOhmYee/WikiPulse)"
WIKI_API = "https://en.wikipedia.org/w/api.php"
SPARQL = "https://query.wikidata.org/sparql"

DEFAULT_TITLES = ["Strait of Hormuz", "Hurricane Milton", "Iran", "Nvidia"]

# NYSE·NASDAQ 상장기업 정규화 이름 색인 — wiki_link_graph_join 전용, gkg/match.py 의
# normalize_name 재사용(법인격 접미어 제거 후 정확 일치).
sys.path.insert(0, "../../data-pipeline")
from gkg.match import normalize_name  # noqa: E402


def wiki_links(title: str, direction: str) -> set[str]:
    """direction: 'links'(아웃링크) 또는 'linkshere'(백링크). 500개씩 continue 로 전량."""
    titles: set[str] = set()
    params = {
        "action": "query", "titles": title, "format": "json",
        "prop": direction, f"{'pl' if direction == 'links' else 'lh'}limit": "500",
        f"{'pl' if direction == 'links' else 'lh'}namespace": "0",
    }
    while True:
        r = requests.get(WIKI_API, params=params, headers={"User-Agent": UA}, timeout=30)
        r.raise_for_status()
        data = r.json()
        pages = data.get("query", {}).get("pages", {})
        for page in pages.values():
            for item in page.get(direction, []):
                titles.add(item["title"])
        if "continue" not in data:
            break
        params.update(data["continue"])
    return titles


def listed_companies() -> set[str]:
    """NYSE·NASDAQ 상장기업 정규화 이름 집합(Wikidata, wiki_link_graph_join.py 전용 조회)."""
    query = """
    SELECT DISTINCT ?companyLabel WHERE {
      ?company p:P414 ?stmt .
      ?stmt ps:P414 ?exchange .
      VALUES ?exchange { wd:Q13677 wd:Q82059 }
      SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
    }
    """
    r = requests.get(SPARQL, params={"query": query, "format": "json"},
                      headers={"User-Agent": UA}, timeout=120)
    r.raise_for_status()
    names = {b["companyLabel"]["value"] for b in r.json()["results"]["bindings"]}
    return {normalize_name(n) for n in names if normalize_name(n)}


def main():
    titles = sys.argv[1:] or DEFAULT_TITLES
    print("NYSE/NASDAQ 상장기업 목록 받는 중...", file=sys.stderr)
    companies = listed_companies()
    print(f"  {len(companies)}개\n", file=sys.stderr)

    for title in titles:
        out_links = wiki_links(title, "links")
        in_links = wiki_links(title, "linkshere")
        neighbors = out_links | in_links
        matched = [n for n in neighbors if normalize_name(n) in companies]
        print(f"{title}: 이웃 {len(neighbors)}개(아웃 {len(out_links)}·백 {len(in_links)}) "
              f"중 상장기업 매칭 {len(matched)}개")
        if matched:
            print(f"  매칭: {matched[:20]}")


if __name__ == "__main__":
    main()
