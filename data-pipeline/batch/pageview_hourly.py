"""`other/pageviews` **시간별** 덤프 파싱·필터 (WP-127).

순수 함수라 네트워크·Spark·DB 없이 테스트된다. 적재 CLI 는 `pageview_hourly_ingest.py`.

🔴 **이 소스가 2단계 최종 관문이다** (명세 §3.2 3번). `batch/pageview.py` 의
`pageview_complete` **일별** 덤프는 하루가 끝나야 나와서 LIVE 판정에 못 쓴다 — 그건
품질 검증용으로 함께 보존하는 소스다. AQS 일별 API 도 LIVE 관문이 아니다.

🔴 **파일명의 시각은 윈도우 끝이다. 시작이 아니다.** `pageviews-20250612-090000.gz` 는
09시가 아니라 **08:00~09:00** 을 담는다 (2026-09-18 실측, 아래 근거). 이걸 시작으로 읽으면
모든 조회수가 한 시간 늦게 붙는데, 값이 그럴듯해서 화면만 봐서는 모른다.

    근거 — `Air India Flight 171` (2025-06-12, 문서 생성 08:58:02 UTC, 사고 08:09 UTC)
      일별 pageview_complete 의 시간 프로파일:  08시 3회 · 09시 24,669회 · 10시 36,434회
      시간별 `-090000` = 3       -> 일별 08시(생성 후 2분치)와 **정확히 같다**
      시간별 `-100000` = 24,669  -> 일별 09시와 정확히 같다
      시간별 `-110000` = 36,434  -> 일별 10시와 정확히 같다
    2026-09-21 재현 — `ai/spec-evidence/pageview_hourly_offset.py align` (3구간 차이 0).
    Main Page·Vijay Rupani 로도 같은 방향을 확인했다(한 시간 밀면 전부 어긋난다).

    ⚠️ 위 대조에서 agent 없는 이 덤프와 일별 `agent=user` 값이 **비트 단위로 같았다.**
       문서 1개·3구간 표본이라 "차이가 없다"로 일반화하지 않는다 — 아래 agent 절 참고.

덤프 형식 (2026-09-18 실측, dumps.wikimedia.org/other/pageviews)
    경로 : /{YYYY}/{YYYY}-{MM}/pageviews-{YYYYMMDD}-{HH}0000.gz   (HH = 윈도우 **끝**)
    컬럼 : project title count bytes   (공백 4개, 헤더 없음)
      project : 도메인 약어. `en`=en.wikipedia 데스크톱, `en.m`=모바일웹.
                ⚠️ 일별 덤프의 `en.wikipedia` 와 **코드 체계가 다르다.**
      title   : 문서 제목(공백은 밑줄). `-` 는 제목 없음(제외)
                ⚠️ **percent-encoding 을 풀지 않는다.** `%` 가 든 제목은 한 시간 파일에
                85행(조회수 264, 전체의 0.00%)뿐이고 전부 `1%_rule`·`%s` 처럼 **문자 그대로의
                퍼센트**였다(2026-09-18 실측). 디코드하면 그런 제목이 오히려 깨진다.
      count   : 그 시간의 조회수
      bytes   : 응답 바이트 합. 요즘은 전부 0 이라 안 쓴다

    2026-09-18 04:00Z 파일 실측: 45.7 MB(gz) · 5,144,442 행 · 압축 해제 1.0s.
    `en`+`en.m` 은 2,025,414 행 · 조회수 8,140,767, 그중 ns0 은 1,915,570 행 · 7,923,840 회.

지연 (실측. ⚠️ 윈도우 끝 기준이다)
    2026-09-18 08:49Z 기준
      [01:00~02:00) 공개 04:12Z (+132분) · [02:00~03:00) 05:05Z (+125분)
      [03:00~04:00) 06:06Z (+126분) · [04:00~05:00) 07:13Z (+134분)
      [05:00~06:00) 이후는 아직 404.
    2026-09-21 00:36Z 재측정 (`ai/spec-evidence/pageview_hourly_offset.py delay`)
      +127 · +152 · +138 · +150 · +153분 (09-20 16시~21시 구간), 그 뒤 3구간은 404.
    합치면 **125~153분**이다. 한 시점의 표본으로 상한을 확정하지 않는다 — 09-18 만
    보면 134분이 상한 같았는데 사흘 뒤 153분이 나왔다.

    🔴 **약 2시간이다.** ~~명세 §3.2 3번의 "약 1시간 지연"~~ 은 이 실측으로 정정됐다
       (2026-09-21 — §3.2·§11·기술 명세 §4 모두 약 2시간).
    처음엔 1시간으로 쟀는데 그건 파일명을 윈도우 시작으로 잘못 읽었기 때문이다(위 🔴).
    사건 발생부터 최종 노출까지의 목표도 1~2시간에서 **2~3시간**으로 옮겼다 — 원본이
    없는 시점을 목표로 두면 내부 처리를 0으로 만들어도 못 지킨다.

⚠️ **agent 필드가 없다.** 위키미디어가 감지한 봇·스파이더는 upstream 에서 이미
   걸러 내지만(명세 §3.2 3번), 어느 agent 였는지는 노출하지 않는다. 그래서
   `PageviewHourly` 에 agent 가 없다 — 일별 덤프의 `agent=user` 와 값이 다를 수 있고,
   그 차이를 재는 것이 `pageview_complete` 를 계속 보존하는 이유다.

제목 정규화 (WP-79)
    `canonical_title` 로 공백형에 맞춘다. ⚠️ **적용 시점이 ns0 필터 뒤, 합산 키 앞**이다 —
    `batch/pageview.py` 와 같은 이유이고, 순서가 뒤집히면 둘 다 조용히 틀린다.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from producer.normalize import canonical_title

from .pageview import NO_TITLE, SchemaMismatch, UnsupportedWiki, is_content_title

#: 공백 구분 컬럼 수. 다르면 덤프 형식이 바뀐 것이다.
HOURLY_COLUMNS = 4

#: wiki DB 이름 → 이 덤프의 project 코드들. 데스크톱과 모바일이 **다른 행**으로 오므로
#: 둘 다 받아 합친다 — 일별 덤프에서 access_method 를 가로질러 합치는 것과 같은 규칙이다.
#: 🔴 `en.d`(wiktionary)·`en.b`(wikibooks) 등 자매 프로젝트를 넣지 않는다. 같은 `en` 으로
#:    시작하지만 다른 위키다 — 넣으면 조회수가 부풀고 에러는 안 난다.
#:    2026-09-18 한 시간 파일에 en 계열 16종이 있었다(en.d 92,769행 등).
WIKI_TO_PROJECTS = {
    "enwiki": frozenset({"en", "en.m"}),
}

#: 파일명에서 시각을 뽑는다: pageviews-20260918-040000.gz
_FILENAME_TS = re.compile(r"pageviews-(\d{8})-(\d{2})0000")

#: 파일명 시각과 윈도우 시작의 차이. 파일명은 윈도우 **끝**이다 (모듈 독스트링 🔴).
FILENAME_IS_WINDOW_END = True


@dataclass(frozen=True)
class PageviewHourly:
    """한 문서·한 시간의 조회수. ingest 가 JSONL.gz 로 쓰고 DB 는 `page_view_hourly` 로 받는다.

    ⚠️ agent 가 없다 — 이 덤프가 안 준다(모듈 독스트링). `batch/pageview.py` 의
    `PageviewRecord` 와 일부러 다른 타입인 이유다. 한 타입으로 합치면 agent 를
    지어내야 한다.
    """
    wiki: str
    title: str      # canonical 공백형. 덤프 원형(밑줄)이 아니다 — WP-79
    ts_hour: str    # ISO "YYYY-MM-DDTHH:00:00" (UTC)
    views: int


def projects_for(wiki: str) -> frozenset[str]:
    """wiki DB 이름 → 이 덤프의 project 코드 집합. 미등록이면 UnsupportedWiki."""
    try:
        return WIKI_TO_PROJECTS[wiki]
    except KeyError:
        raise UnsupportedWiki(
            f"{wiki!r} project 코드 미등록. WIKI_TO_PROJECTS 에 추가한다. "
            "⚠️ 일별 덤프의 WIKI_TO_PROJECT 와 코드 체계가 다르다."
        ) from None


def ts_hour_from_filename(name: str) -> str:
    """`pageviews-20260918-040000.gz` → **`2026-09-18T03:00:00`** (윈도우 시작).

    🔴 파일명 시각은 윈도우 **끝**이라 한 시간을 뺀다 (모듈 독스트링 🔴의 근거).
       ~~파일명 시각을 그대로 썼다~~ → 그러면 모든 조회수가 한 시간 늦게 붙는다.
    🔴 시각은 **파일명에서만** 온다. 행에는 시각 컬럼이 아예 없다 — 그래서 파일과
       시각을 잘못 짝지으면 조회수 전체가 통째로 밀리고 아무 에러도 안 난다.

    ⚠️ `-000000` 파일은 **전날 23시**다. 날짜가 넘어간다.
    """
    match = _FILENAME_TS.search(name)
    if match is None:
        raise SchemaMismatch(f"파일명에서 시각을 못 읽었다: {name!r}")
    date, hour = match.groups()
    end = datetime(int(date[:4]), int(date[4:6]), int(date[6:]), int(hour), tzinfo=timezone.utc)
    start = end - timedelta(hours=1)
    return start.strftime("%Y-%m-%dT%H:00:00")


def filename_hour(ts_hour: str) -> tuple[str, str]:
    """윈도우 시작 `2026-09-18T03:00:00` → 파일 날짜·시각 `("20260918", "04")`.

    `ts_hour_from_filename` 의 역이다. 둘을 한 파일에 두는 이유는 한쪽만 고치면
    조용히 어긋나기 때문이다.
    """
    start = datetime.strptime(ts_hour[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
    end = start + timedelta(hours=1)
    return end.strftime("%Y%m%d"), end.strftime("%H")


def parse_row(line: str, projects: frozenset[str]) -> tuple[str, int] | None:
    """공백 4컬럼 한 줄 → (canonical title, views). 대상 project·ns0 가 아니면 None.

    컬럼 수가 4가 아니거나 조회수가 정수가 아니면 SchemaMismatch.

    ⚠️ 제목에 공백이 들어간 행은 없다 — 이 덤프는 제목의 공백을 밑줄로 쓴다. 그래도
    컬럼 수를 세는 이유는 형식이 바뀌면 **조용히 다른 값을 읽기** 때문이다.
    """
    fields = line.rstrip("\n").split(" ")
    if len(fields) != HOURLY_COLUMNS:
        raise SchemaMismatch(f"{len(fields)} columns, expected {HOURLY_COLUMNS}")
    project, title, count_raw, _bytes = fields
    if project not in projects:
        return None
    if title == NO_TITLE or not is_content_title(title):
        return None
    try:
        views = int(count_raw)
    except ValueError:
        raise SchemaMismatch(f"{title!r} 조회수가 정수가 아니다: {count_raw!r}") from None
    # ns0 판정이 끝난 뒤, 합산 키가 되기 전에 canonical 로 맞춘다 (WP-79).
    canonical = canonical_title(title)
    if not canonical:
        # `_` · `__` 같은 행이 실제로 있다(2026-09-18 04:00Z 파일에 5회). canonical 을
        # 거치면 빈 문자열이 되는데, 그대로 두면 제목이 빈 wiki_page 행이 생긴다.
        return None
    return canonical, views


def aggregate(
    lines: Iterable[str],
    wiki: str,
    ts_hour: str,
    *,
    titles: frozenset[str] | None = None,
) -> Iterator[PageviewHourly]:
    """한 시간 파일을 (wiki, title, ts_hour, views) 로 합산한다.

    데스크톱(`en`)과 모바일(`en.m`)이 한 문서당 각각 한 행이라 합쳐진다.

    `titles` 를 주면 그 문서만 남긴다(canonical 공백형으로 비교). ⚠️ **전체를 그대로
    적재하지 않는 이유**: enwiki ns0 만 시간당 약 190만 행이라 하루 4,500만 행이고,
    고정 2개월이면 28억 행이다. 2단계 계약에서 조회수를 봐야 하는 건 1단계(사람 편집
    1건 이상)를 통과한 문서뿐이므로, 그 후보 집합으로 거르는 게 정상 경로다.
    필터 없이 부르면 전부 나온다 — 품질 측정·전수 비교용이다.
    """
    projects = projects_for(wiki)
    acc: dict[str, int] = {}
    for line in lines:
        if not line.strip():
            continue
        parsed = parse_row(line, projects)
        if parsed is None:
            continue
        title, views = parsed
        if titles is not None and title not in titles:
            continue
        acc[title] = acc.get(title, 0) + views

    for title, views in acc.items():
        yield PageviewHourly(wiki=wiki, title=title, ts_hour=ts_hour, views=views)
