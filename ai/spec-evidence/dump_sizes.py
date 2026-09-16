"""§11 "Wikimedia 덤프" 행 재현. HEAD 요청만으로 mediawiki_history·pageview_complete·
clickstream 덤프 크기를 잰다(다운로드 안 함).

실행: 네트워크만 필요.
    py -3 dump_sizes.py
"""

import re
import sys

import requests

UA = "WikiPulse/0.1 (WikiPulse research; https://github.com/ClOhmYee/WikiPulse)"

# 실측하려는 콘텐츠 월(§11 과 같은 대상) — 스냅샷 디렉터리가 아니라 파일 안에
# 든 "역사가 담긴 월"이다. mediawiki_history 는 아래 함정 때문에 분리해 둔다.
MW_HISTORY_CONTENT_MONTHS = ["2025-06", "2024-10"]

OTHER_TARGETS = [
    ("clickstream enwiki 2024-10",
     "https://dumps.wikimedia.org/other/clickstream/2024-10/"
     "clickstream-enwiki-2024-10.tsv.gz"),
    ("pageview_complete 2024-10-10",
     "https://dumps.wikimedia.org/other/pageview_complete/2024/2024-10/"
     "pageviews-20241010-user.bz2"),
]


def head_size(url: str) -> int | None:
    r = requests.head(url, headers={"User-Agent": UA}, timeout=60, allow_redirects=True)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    cl = r.headers.get("Content-Length")
    return int(cl) if cl else None


def latest_mw_history_snapshot() -> str:
    """mediawiki_history 는 매달 스냅샷 디렉터리를 통째로 새로 깎고 옛것을 지운다.

    ⚠️ 실측 중 발견 — 2026-09-16 기준 살아있는 스냅샷은 `2026-07`·`2026-08` 뿐이었다
    (2025 년치 디렉터리는 없어졌다). 각 스냅샷 안에는 2001년부터 그 시점까지 전체
    콘텐츠 월이 다 들어있다(`{스냅샷}.enwiki.{콘텐츠월}.tsv.bz2`) — 옛 콘텐츠가
    사라진 게 아니라 **최신 스냅샷 디렉터리 밑으로 옮겨 다닐 뿐이다.** 그래서 항상
    최신 스냅샷을 먼저 찾아야 한다. 이 함정을 모르면 "2024-10 이후 디렉터리"를
    찾다가 존재 자체가 사라졌다고 오판하기 좋다.
    """
    r = requests.get("https://dumps.wikimedia.org/other/mediawiki_history/",
                      headers={"User-Agent": UA}, timeout=30)
    r.raise_for_status()
    dirs = re.findall(r'href="(\d{4}-\d{2})/"', r.text)
    if not dirs:
        raise RuntimeError("mediawiki_history 스냅샷 디렉터리를 못 찾음 — 사이트 구조가 바뀌었나")
    return sorted(dirs)[-1]


def main():
    snapshot = latest_mw_history_snapshot()
    print(f"mediawiki_history 최신 스냅샷: {snapshot} (이 밑에서 콘텐츠 월을 찾는다)\n")
    for content_month in MW_HISTORY_CONTENT_MONTHS:
        url = (f"https://dumps.wikimedia.org/other/mediawiki_history/{snapshot}/enwiki/"
               f"{snapshot}.enwiki.{content_month}.tsv.bz2")
        size = head_size(url)
        label = f"mediawiki_history enwiki {content_month} (스냅샷 {snapshot})"
        print(f"{label}: {'404 — 이 스냅샷엔 없음, latest_mw_history_snapshot 재확인' if size is None else f'{size:,} bytes ({size / 1_000_000:.0f} MB)'}")

    for label, url in OTHER_TARGETS:
        size = head_size(url)
        if size is None:
            print(f"{label}: 404 (URL·연월 확인 필요 — 덤프 발행 주기가 바뀌었을 수 있다)")
        else:
            print(f"{label}: {size:,} bytes ({size / 1_000_000:.0f} MB)")


if __name__ == "__main__":
    main()
