"""GKG 2.1 CSV 파싱 — 조직명·테마·지역 추출. 순수 파이썬(Spark 의존 없음).

컬럼 배치는 2026-09-14 에 실물(20241010120000.gkg.csv, 27컬럼)로 확인했다. 이
저장소가 반복해서 데인 "컬럼 인덱스를 문서만 보고 박았다가 조용히 틀린 값"
(Wikidata P249 함정, CLAUDE.md)을 피하려고 실제 파일로 검증한 값이다:

    idx  필드                         예
    0    GKGRECORDID                  20241010120000-0
    1    V2.1DATE                     20241010120000
    3    SourceCommonName             oldham-chronicle.co.uk
    4    DocumentIdentifier(URL)      https://...
    7    V1THEMES  (';' 코드)          NATURAL_DISASTER;NATURAL_DISASTER_HURRICANE;...
    9    V1LOCATIONS (';' · '#' 필드)  1#France#FR#FR#46#2#FR;1#Portugal#...
    13   V1ORGANIZATIONS (';' 이름)    (그 슬롯 1462행 중 1062행 채워짐)
    14   V2ENHANCEDORGANIZATIONS       name,charoffset;...  (1026행)

조직명은 V1(13)·V2(14) 를 합쳐 쓴다. V2 는 `이름,오프셋` 이라 오프셋을 뗀다.
V1 이 없고 V2 만 있는 행이 있어(그리고 반대도) 합집합이 회수율이 가장 높다.

⚠️ GKG 는 탭 구분이고, 필드 안에는 콤마·세미콜론·#가 들어간다. csv 모듈이 아니라
   탭 split 로 연다 — 필드 내부에 탭이 없다는 GDELT 계약에 기댄다.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass

# 실물 검증한 0-기준 컬럼 인덱스 (위 docstring).
COL_RECORD_ID = 0
COL_DATE = 1
COL_SOURCE = 3
COL_DOCUMENT = 4
COL_THEMES = 7
COL_LOCATIONS = 9
COL_ORGS_V1 = 13
COL_ORGS_V2 = 14

#: GKG 2.1 은 27 컬럼이다. 이보다 적으면 잘린 줄이니 버린다.
MIN_COLUMNS = 27


@dataclass(frozen=True)
class Record:
    """GKG 기사 한 건에서 lift 집계에 필요한 것만.

    orgs 는 소문자·중복제거된 기관명 집합이다 — 한 기사에서 같은 기관이 V1·V2
    양쪽에 나와도 한 번만 센다(문서 빈도지 언급 횟수가 아니다).
    themes 는 대문자 코드, locations 는 소문자 풀네임. 이슈 술어(lift.py)가 쓴다.
    """

    doc_id: str
    orgs: frozenset[str]
    themes: tuple[str, ...]
    locations: tuple[str, ...]


def _clean(name: str) -> str:
    """조직명 토큰을 소문자·트림. 빈 문자열이면 버려질 값."""
    return name.strip().lower()


def _orgs(v1: str, v2: str) -> frozenset[str]:
    """V1(이름) + V2(이름,오프셋) 를 합쳐 소문자 기관명 집합으로."""
    names: set[str] = set()
    for tok in v1.split(";"):
        n = _clean(tok)
        if n:
            names.add(n)
    for tok in v2.split(";"):
        # V2 는 "name,charoffset" — 첫 콤마 앞이 이름이다.
        n = _clean(tok.split(",")[0])
        if n:
            names.add(n)
    return frozenset(names)


def _themes(raw: str) -> tuple[str, ...]:
    """V1THEMES 를 대문자 코드 튜플로. 코드 자체가 대문자지만 방어적으로 upper()."""
    return tuple(t.strip().upper() for t in raw.split(";") if t.strip())


def _locations(raw: str) -> tuple[str, ...]:
    """V1LOCATIONS 각 항목의 풀네임(#-필드 index 1)만 소문자로 모은다.

    항목 형식: type#fullname#countrycode#adm1#lat#long#featureid
    풀네임이 이슈 술어의 지역 매칭 대상이다("florida" 부분일치).
    """
    out: list[str] = []
    for item in raw.split(";"):
        if not item.strip():
            continue
        fields = item.split("#")
        if len(fields) >= 2 and fields[1].strip():
            out.append(fields[1].strip().lower())
    return tuple(out)


def parse_row(row: list[str]) -> Record | None:
    """탭 split 된 필드 리스트 → Record. 컬럼이 모자라면(잘린 줄) None."""
    if len(row) < MIN_COLUMNS:
        return None
    return Record(
        doc_id=row[COL_DOCUMENT] or row[COL_RECORD_ID],
        orgs=_orgs(row[COL_ORGS_V1], row[COL_ORGS_V2]),
        themes=_themes(row[COL_THEMES]),
        locations=_locations(row[COL_LOCATIONS]),
    )


def parse_lines(lines: Iterable[str]) -> Iterator[Record]:
    """GKG CSV 줄들을 Record 로 흘려보낸다. 빈 줄·잘린 줄은 건너뛴다.

    줄 이터러블을 받아 파일 전체를 메모리에 올리지 않는다(하루치가 1.9 GB).
    """
    for line in lines:
        line = line.rstrip("\n")
        if not line:
            continue
        record = parse_row(line.split("\t"))
        if record is not None:
            yield record


def parse_text(text: str) -> Iterator[Record]:
    """GKG CSV 한 파일(문자열) → Record 이터레이터."""
    return parse_lines(text.split("\n"))
