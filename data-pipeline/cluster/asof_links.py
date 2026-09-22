"""as-of revision 의 direct Wikipedia link 수집·캐시 (WP-161).

CORE 클러스터링(`rootgraph.py`)의 유일한 입력 신호다.

앵커는 `spike.max_rev_id` — 그 윈도우 판정에 들어간 마지막 revision 이다(V9).
replay 면 과거 판정 시점의 판, LIVE 면 관측 시점의 판이라 **두 출처가 같은 계약**을
쓴다. 코드에 replay/live 분기가 없는 이유다.

🔴 **`prop=wikitext` 의 리터럴 `[[...]]` 만 쓴다. `parse.links` 를 쓰지 않는다.**
   MediaWiki 는 옛 revision 을 렌더할 때도 **템플릿은 현재 판**을 쓴다. 그래서
   `parse.links` 에는 스냅샷 이후 navbox 에 추가된 링크가 섞여 들어온다 — 미래 정보
   누수이고, 에러 없이 조용히 틀린다. wikitext 리터럴은 템플릿 전개가 없어 누수가 0 이다.

🔴 **`max_rev_id` 가 없으면 현재 판으로 폴백하지 않는다.** 링크 없음으로 두어 그 root 를
   singleton 으로 만든다. 폴백은 그 자체가 누수다.
"""

from __future__ import annotations

import json
import re
import threading
import time
from collections.abc import Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor

API = "https://en.wikipedia.org/w/api.php"

#: ns0 이 아닌 링크 접두(소문자 비교). 인터위키 언어코드는 `_LANG` 이 따로 거른다.
_NON_NS0 = frozenset({
    "file", "image", "category", "wikipedia", "wp", "help", "template", "portal",
    "talk", "special", "module", "mos", "draft", "user", "media", "mediawiki",
    "book", "timedtext", "gadget", "topic", "s", "wikt", "commons", "c", "d",
    "meta", "m", "q", "b", "n", "v", "voy", "arxiv", "doi", "isbn", "oclc",
    "pmid", "rfc", "simple",
})
_LANG = re.compile(r"^[a-z]{2,3}(-[a-z]{2,8})?$")
_LINK = re.compile(r"\[\[([^\[\]\|]+)(?:\|[^\[\]]*)?\]\]")


def link_key(title: str) -> str:
    """링크 비교 전용 정규화. 밑줄→공백·연속 축약·trim **+ 첫 글자 대문자**.

    🔴 **`producer/normalize.canonical_title` 과 다르다. 섞어 쓰면 안 된다.**

    `canonical_title` 은 첫 글자 대문자를 **일부러 적용하지 않는다** — 그쪽 입력은 이미
    MediaWiki 저장 제목이라 no-op 이기 때문이다(`eBay` 를 조회하면 저장 제목이 `EBay`).
    반면 여기 입력은 `[[...]]` 안에 **사람이 손으로 쓴 문자열**이고, MediaWiki 는 링크
    타깃의 첫 글자를 대문자로 해석한다. 그래서 `[[eBay]]` 는 `EBay` 문서를 가리킨다.

    ⚠️ 두 쪽(저장 제목 / 링크 타깃)에 **같은 함수**를 걸어야 맞물린다. 한쪽만 걸면
    `eBay` 와 `EBay` 가 어긋나 간선이 **에러 없이 사라진다**.

    ⚠️ 저장용 제목을 이 함수로 만들지 않는다. `wiki_page.title` 은 계속
    `canonical_title` 계약이다 — 여기 값은 비교 키일 뿐이다.
    """
    normalized = " ".join(title.replace("_", " ").split())
    return normalized[:1].upper() + normalized[1:] if normalized else normalized


def is_ns0(target: str) -> bool:
    """주 문서 네임스페이스 링크인가. 섹션 앵커·인터위키·파일 등을 거른다."""
    if not target or target.startswith(":") or target.startswith("#"):
        return False
    if ":" in target:
        prefix = target.split(":", 1)[0].strip().lower()
        if prefix in _NON_NS0 or _LANG.match(prefix):
            return False
    return True


def wikitext_links(wikitext: str) -> list[str]:
    """revision 본문의 리터럴 위키링크(ns0, 정규화·정렬). 템플릿 전개 없음 → 누수 0."""
    out: set[str] = set()
    for match in _LINK.finditer(wikitext):
        target = match.group(1).split("#", 1)[0].strip()
        if is_ns0(target):
            key = link_key(target)
            if key:
                out.add(key)
    return sorted(out)


# --- 캐시 (V12 page_asof_links) ----------------------------------------------

SELECT_LINKS_SQL = """
SELECT rev_id, links, error FROM page_asof_links WHERE rev_id = ANY(%s)
"""

UPSERT_LINKS_SQL = """
INSERT INTO page_asof_links (rev_id, wiki, title, links, link_count, error)
VALUES (%s, %s, %s, %s, %s, %s)
ON CONFLICT (rev_id) DO UPDATE SET
    wiki = EXCLUDED.wiki, title = EXCLUDED.title, links = EXCLUDED.links,
    link_count = EXCLUDED.link_count, fetched_at = now(), error = EXCLUDED.error
"""


def load_cached(conn, rev_ids: Sequence[int]) -> dict[int, set[str]]:
    """캐시에 있는 링크 집합. 실패로 기록된 행은 **돌려주지 않는다**.

    없는 rev_id 는 키가 없다 — 호출자가 "아직 안 해 봄" 과 "링크가 0개" 를 구분할 수
    있어야 한다. 전자는 수집 대상이고 후자는 정상 결과다.
    """
    if not rev_ids:
        return {}
    unique = list(dict.fromkeys(int(r) for r in rev_ids))
    out: dict[int, set[str]] = {}
    with conn.cursor() as cur:
        cur.execute(SELECT_LINKS_SQL, (unique,))
        for rev_id, links, error in cur.fetchall():
            if error:
                continue
            out[int(rev_id)] = set(links if isinstance(links, list) else json.loads(links))
    return out


def store(conn, rows: Iterable[tuple[int, str, str, list[str], str | None]]) -> int:
    """수집 결과를 캐시에 넣는다. `rows` = (rev_id, wiki, title, links, error)."""
    payload = [(rev_id, wiki, title, json.dumps(links), len(links), error)
               for rev_id, wiki, title, links, error in rows]
    if not payload:
        return 0
    with conn.cursor() as cur:
        cur.executemany(UPSERT_LINKS_SQL, payload)
    return len(payload)


# --- 수집 --------------------------------------------------------------------

class WikipediaLinkFetcher:
    """`action=parse&oldid=…&prop=wikitext` 로 as-of 링크를 받는다.

    HTTP 는 주입 가능하다(`session_factory`) — 테스트가 네트워크를 타지 않게 하려고
    이렇게 뒀다. User-Agent 는 `batch.ingest.user_agent()` 규칙을 그대로 쓴다
    (Wikimedia 는 연락처 없는 UA 를 차단한다).
    """

    def __init__(self, *, user_agent: str, session_factory=None, workers: int = 4,
                 max_attempts: int = 6, sleep=time.sleep):
        self.user_agent = user_agent
        self.workers = workers
        self.max_attempts = max_attempts
        self._sleep = sleep
        self._local = threading.local()
        if session_factory is None:
            import requests                       # 지연 import — 캐시만 쓸 때는 불필요
            session_factory = requests.Session
        self._session_factory = session_factory

    def _session(self):
        session = getattr(self._local, "session", None)
        if session is None:
            session = self._local.session = self._session_factory()
        return session

    def fetch_one(self, rev_id: int) -> tuple[str, list[str], str | None]:
        """returns (title, links, error). 재시도는 전이성 실패에만 건다."""
        params = {"action": "parse", "oldid": rev_id, "prop": "wikitext",
                  "format": "json", "formatversion": "2", "maxlag": "5"}
        last = ""
        for attempt in range(self.max_attempts):
            try:
                response = self._session().get(
                    API, params=params, headers={"User-Agent": self.user_agent},
                    timeout=90)
            except Exception as exc:             # noqa: BLE001 — 전송 계층 전부 전이성 취급
                last = str(exc)
                self._sleep(2 * (attempt + 1))
                continue
            if response.status_code in (429, 503):
                last = f"http {response.status_code}"
                self._sleep(float(response.headers.get("Retry-After", 5)) + attempt)
                continue
            if response.status_code != 200:
                return "", [], f"http {response.status_code}"
            payload = response.json()
            if "error" in payload:
                code = payload["error"].get("code", "")
                if code == "maxlag":             # 서버가 밀렸다 — 기다렸다 다시
                    last = "maxlag"
                    self._sleep(5 + attempt)
                    continue
                return "", [], f"api {code}"
            parsed = payload["parse"]
            return parsed.get("title", ""), wikitext_links(parsed.get("wikitext", "")), None
        return "", [], f"retries exhausted ({last})"

    def fetch_many(self, rev_ids: Sequence[int], log=None) -> dict[int, tuple[str, list[str], str | None]]:
        todo = list(dict.fromkeys(int(r) for r in rev_ids))
        if not todo:
            return {}
        if log:
            log(f"as-of link fetch: {len(todo)} revisions")
        results: dict[int, tuple[str, list[str], str | None]] = {}
        lock = threading.Lock()

        def work(rev_id: int):
            got = self.fetch_one(rev_id)
            with lock:
                results[rev_id] = got
                if log and len(results) % 200 == 0:
                    log(f"  {len(results)}/{len(todo)}")

        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            list(pool.map(work, todo))
        if log:
            failed = sum(1 for _t, _l, e in results.values() if e)
            log(f"  {len(results)}/{len(todo)} done (실패 {failed})")
        return results
