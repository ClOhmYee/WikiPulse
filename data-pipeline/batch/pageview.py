"""Wikipedia pageview_complete 일별 덤프 파싱·필터·시간 디코드 (WP-57).

순수 함수라 네트워크·Spark·HDFS 없이 테스트된다. 적재 CLI 는 pageview_ingest.py.
소비: baseline `view_ewma`(WP-58/-60)·급증 2차 판정(조회수) 입력.

덤프 형식 (2026-09-09 실측, dumps.wikimedia.org/other/pageview_complete)
    경로 : /{YYYY}/{YYYY}-{MM}/pageviews-{YYYYMMDD}-{agent}.bz2
      agent 는 파일명에 있다(user/automated/spider). 시기마다 구성이 다르다 —
      2019 user·spider / 2020 +automated / 2025 user·automated(spider 404).
      🔴 하드코딩하지 않는다. ingest 가 그날 실제 존재하는 파일을 발견해 넘긴다.
    컬럼: project title page_id access_method daily_total hourly_counts  (공백 6개, 헤더 없음)
      project      : 위키 코드. 이 덤프는 `en.wikipedia` (mediawiki_history 는 `enwiki`)
      title        : 문서 제목(공백은 밑줄). `-` 는 제목 없음(제외)
      page_id      : dump 내부 id. null 10.56%, 같은 문서가 여러 id 로 갈린다 — 키로 쓰지 않는다
      access_method : desktop/mobile-web/mobile-app. (wiki,title,ts_hour,agent) 로 합산할 때 가로지른다
      daily_total  : 그 행의 하루 합. 시간별 합과 다르면 형식 오류다
      hourly_counts : 희소 인코딩. `A=0시 … X=23시`, 0인 시간은 생략. 예: "C2G1" = 2시 2회·6시 1회

무엇을 남기나
    대상 위키(project) 행만, `-` 와 알려진 namespace prefix 를 뺀 ns0 문서만.
    시간별 카운트를 (wiki, title, ts_hour, agent, views) 로 펼쳐 같은 키끼리 합산한다.

제목 정규화 (WP-79)
    ~~여기서는 덤프 원형(밑줄)을 그대로 둔다~~ → `canonical_title` 로 공백형에 맞춘다.
    편집 덤프(mediawiki_history)·실시간(EventStreams)과 같은 함수 한 곳을 쓴다 —
    규칙과 근거는 `producer/normalize.py:canonical_title`, 명세 §5.1.

    ⚠️ **적용 시점이 `is_content_title` 뒤, 합산 앞이다.** 순서가 뒤집히면 조용히 틀린다.
      - 앞으로 옮기면: namespace prefix 가 `User_talk` 라 밑줄 기준으로 비교하는데
        `User talk` 가 되어 일치하지 않는다 — namespace 문서가 ns0 로 새어 들어온다.
      - 뒤로 옮기면: `acc` 가 이미 원형 title 로 그룹을 갈라 놓은 뒤라
        `Hurricane_Milton` 과 `Hurricane Milton` 이 별개 키로 집계된다.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass

from producer.normalize import canonical_title

#: 공백 구분 컬럼 수. 다르면 덤프 형식이 바뀐 것이다.
PAGEVIEW_COLUMNS = 6

#: 제목 없음 행. page_id 가 제각각인 무관 문서 33만 개가 뭉친 값이라 버린다.
NO_TITLE = "-"

#: 시간 인코딩 문자당 시(hour). A=0 … X=23.
_HOUR_TOKEN = re.compile(r"([A-X])(\d+)")


class SchemaMismatch(Exception):
    """컬럼 수가 다르거나 시간별 합이 daily_total 과 어긋난다. 형식 변경·손상 신호다."""


class UnsupportedWiki(Exception):
    """project 코드 역매핑이 없다. 조용히 틀린 위키를 만드는 것보다 멈춘다."""


#: wiki DB 이름 → 덤프 project 코드. 필요할 때 늘린다. mediawiki_history 와 코드 체계가 다르다.
WIKI_TO_PROJECT = {
    "enwiki": "en.wikipedia",
}

#: enwiki namespace prefix (ns0 만 남기려 제외). localize 된 다른 위키는 현재 범위 밖이다.
#: 🔴 단순 `:` 포함으로 거르지 않는다 — 정상 문서 제목에 콜론이 들어간다(예: "Bang: The Story").
ENWIKI_NAMESPACE_PREFIXES = frozenset({
    "Media", "Special", "Talk", "User", "User_talk", "Wikipedia", "Wikipedia_talk",
    "File", "File_talk", "MediaWiki", "MediaWiki_talk", "Template", "Template_talk",
    "Help", "Help_talk", "Category", "Category_talk", "Portal", "Portal_talk",
    "Draft", "Draft_talk", "TimedText", "TimedText_talk", "Module", "Module_talk",
    # prefix 별칭
    "WP", "WT", "Image", "Image_talk",
})


@dataclass(frozen=True)
class PageviewRecord:
    """한 문서·한 시간·한 agent 의 조회수. ingest 가 JSONL.gz 로 쓴다."""
    wiki: str
    title: str      # canonical 공백형. 덤프 원형(밑줄)이 아니다 — WP-79
    ts_hour: str    # ISO "YYYY-MM-DDTHH:00:00" (UTC)
    agent: str
    views: int


def project_for(wiki: str) -> str:
    """wiki DB 이름을 덤프 project 코드로. 미등록이면 UnsupportedWiki."""
    try:
        return WIKI_TO_PROJECT[wiki]
    except KeyError:
        raise UnsupportedWiki(
            f"{wiki!r} project 코드 미등록. WIKI_TO_PROJECT 에 추가한다."
        ) from None


def decode_hourly(encoded: str) -> dict[int, int]:
    """희소 시간 인코딩을 {hour: views} 로. 빈 문자열은 {}.

    "C2G1" -> {2: 2, 6: 1}. 형식이 깨져 남는 문자가 있으면 SchemaMismatch.
    """
    if not encoded:
        return {}
    hours: dict[int, int] = {}
    consumed = 0
    for match in _HOUR_TOKEN.finditer(encoded):
        hour = ord(match.group(1)) - ord("A")   # A->0 … X->23
        hours[hour] = hours.get(hour, 0) + int(match.group(2))
        consumed += len(match.group(0))
    if consumed != len(encoded):
        raise SchemaMismatch(f"hourly_counts 파싱 잔여: {encoded!r}")
    return hours


def is_content_title(title: str, prefixes: frozenset[str] = ENWIKI_NAMESPACE_PREFIXES) -> bool:
    """ns0 문서면 True. `-`·알려진 namespace prefix 는 False.

    ⚠️ **덤프 원형(밑줄) title 을 받는다.** prefix 목록이 `User_talk` 처럼 밑줄형이라
    canonical(공백형)을 넣으면 `User talk` 가 되어 아무것도 안 걸린다 — WP-79.
    """
    if title == NO_TITLE:
        return False
    head, sep, _ = title.partition(":")
    if sep and head in prefixes:
        return False
    return True


def parse_row(line: str, project: str) -> tuple[str, dict[int, int]] | None:
    """공백 6컬럼 한 줄 → (canonical title, {hour: views}). 대상 project·ns0 가 아니면 None.

    컬럼 수가 6이 아니거나 시간별 합 != daily_total 이면 SchemaMismatch.
    같은 title 이 access_method·page_id 로 여러 행이면 각각 나오고, 합산은 aggregate 가 한다.

    돌려주는 title 은 canonical 공백형이다 (WP-79). ns0 판정은 원형으로 끝낸 뒤
    변환한다 — 합산 키가 되기 전이라 표기만 다른 같은 문서가 한 그룹으로 모인다.
    """
    fields = line.rstrip("\n").split(" ")
    if len(fields) != PAGEVIEW_COLUMNS:
        raise SchemaMismatch(f"{len(fields)} columns, expected {PAGEVIEW_COLUMNS}")
    row_project, title, _page_id, _access, daily_total_raw, hourly_raw = fields
    if row_project != project:
        return None
    if not is_content_title(title):
        return None
    hours = decode_hourly(hourly_raw)
    daily_total = int(daily_total_raw)
    if sum(hours.values()) != daily_total:
        raise SchemaMismatch(
            f"{title!r} 시간합 {sum(hours.values())} != daily_total {daily_total}"
        )
    # ns0 판정이 끝난 뒤, 합산 키가 되기 전에 canonical 로 맞춘다 (WP-79).
    return canonical_title(title), hours


def aggregate(
    lines: Iterable[str], project: str, wiki: str, agent: str, date: str
) -> Iterator[PageviewRecord]:
    """한 agent-일 파일을 (wiki, title, ts_hour, agent, views) 로 펼쳐 합산한다.

    access_method·page_id 를 가로질러 (title, hour) 로 합친다. date 는 "YYYY-MM-DD".
    title 은 parse_row 가 이미 canonical 로 맞춘 값이라, 표기만 다른 같은 문서
    (`Hurricane_Milton` · `Hurricane Milton`)가 한 키로 합쳐진다 — WP-79.
    한 파일을 dict 로 누적한다 — 전체 enwiki 는 Spark 경로가 맡고, 이 CLI 는 검증
    슬라이스(Hormuz·Milton 등)용이다(§7 메모리 근거).
    """
    acc: dict[tuple[str, int], int] = {}
    for line in lines:
        if not line.strip():
            continue
        parsed = parse_row(line, project)
        if parsed is None:
            continue
        title, hours = parsed
        for hour, views in hours.items():
            acc[(title, hour)] = acc.get((title, hour), 0) + views

    for (title, hour), views in acc.items():
        yield PageviewRecord(
            wiki=wiki,
            title=title,
            ts_hour=f"{date}T{hour:02d}:00:00",
            agent=agent,
            views=views,
        )
