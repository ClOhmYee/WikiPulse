"""Wikipedia Clickstream 월별 덤프 파싱·필터·이웃 조회 (WP-81).

순수 함수라 네트워크·Spark·HDFS 없이 테스트된다. 적재 CLI 는 clickstream_ingest.py,
소비는 cluster/driver.py 가 이 이웃 조회를 호출한다.

덤프 형식 (2026-09-11 기준, dumps.wikimedia.org/other/clickstream)
    파일: clickstream-{wiki}-{YYYY-MM}.tsv.gz
    컬럼: prev  curr  type  n   (탭 구분, 헤더 없음)
      prev/curr : 문서 제목. 공백은 밑줄(_)로 온다.
      type      : link(문서 내 링크 클릭) / external(검색·외부 유입) / other(같은 문서)
      n         : 이동 횟수. 위키미디어가 이미 n>=10 만 공개한다(별도 문턱 없음 — §10).

무엇을 남기나
    type='link' 만 남긴다. external 은 문서 간 이동이 아니라 검색엔진·외부 사이트에서
    들어온 것이고, other 는 같은 문서 내부라 이웃이 아니다. 클러스터링이 원하는 것은
    "문서 A 를 보다 문서 B 로 넘어간" 동시 열람이므로 link 만 신호다.

제목 정규화 (⚠️ WP-79)
    Clickstream 은 밑줄, EventStreams·wiki_page 는 공백을 쓴다. 여기서 밑줄을 공백으로
    바꿔 씨드 제목(wiki_page.title)과 맞춘다. 두 소스의 canonical 규칙 통일은 -79 다 —
    확정되면 이 변환을 그 규칙으로 교체한다.
"""

from __future__ import annotations

import gzip
import json
from collections.abc import Iterable, Iterator
from pathlib import Path
from dataclasses import dataclass

#: 덤프 TSV 의 컬럼 수. 다르면 스냅샷 형식이 바뀐 것이다.
CLICKSTREAM_COLUMNS = 4

#: 문서 간 이동만 신호다. external·other 는 이웃이 아니다.
KEEP_TYPE = "link"


class SchemaMismatch(Exception):
    """행의 컬럼 수가 기대와 다르다. 덤프 형식 변경 신호다."""


@dataclass(frozen=True)
class ClickstreamRow:
    """link 행 하나. prev -> curr 로 n 번 이동."""
    prev: str
    curr: str
    n: int


@dataclass(frozen=True)
class NeighborRef:
    """한 씨드의 Clickstream 이웃. driver 가 cluster.snapshot.Neighbor 로 바꾼다."""
    title: str      # 이웃 문서 제목 (공백 정규화됨)
    n: int          # 이동량 합. cluster_member.weight 로 쓴다
    directed: bool  # 씨드 -> 이웃 방향이면 True(나가는 클릭), 들어오는 클릭이면 False


def canonical_title(raw: str) -> str:
    """Clickstream 밑줄 제목을 wiki_page 공백 제목으로. (WP-79 잠정)"""
    return raw.replace("_", " ")


def parse_row(line: str) -> ClickstreamRow | None:
    """TSV 한 줄을 파싱한다. link 가 아니면 None. 컬럼 수가 틀리면 SchemaMismatch.

    n 이 정수가 아니면(형식 오류) 그 행은 건너뛴다 — 덤프에 드물게 깨진 행이 있다.
    """
    fields = line.rstrip("\n").split("\t")
    if len(fields) != CLICKSTREAM_COLUMNS:
        raise SchemaMismatch(f"{len(fields)} columns, expected {CLICKSTREAM_COLUMNS}")
    prev, curr, kind, n_raw = fields
    if kind != KEEP_TYPE:
        return None
    try:
        n = int(n_raw)
    except ValueError:
        return None
    return ClickstreamRow(canonical_title(prev), canonical_title(curr), n)


def parse_rows(lines: Iterable[str]) -> Iterator[ClickstreamRow]:
    """link 행만 흘려보낸다. 빈 줄은 건너뛴다."""
    for line in lines:
        if not line.strip():
            continue
        row = parse_row(line)
        if row is not None:
            yield row


def read_shards(directory: str | Path) -> Iterator[ClickstreamRow]:
    """적재본(clickstream_ingest 출력) JSONL.gz shard 들을 ClickstreamRow 로 되읽는다.

    적재 때 이미 link 만·정규화 제목으로 저장돼 있으므로 그대로 복원한다.
    """
    directory = Path(directory)
    for shard in sorted(directory.glob("part-*.jsonl.gz")):
        with gzip.open(shard, "rt", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                rec = json.loads(line)
                yield ClickstreamRow(rec["prev"], rec["curr"], int(rec["n"]))


def neighbors_for(
    rows: Iterable[ClickstreamRow], seeds: set[str]
) -> dict[str, list[NeighborRef]]:
    """덤프를 한 번 훑어 각 씨드의 이웃을 모은다.

    씨드가 prev 면 나가는 이웃(directed=True), curr 면 들어오는 이웃(directed=False).
    같은 (씨드, 이웃) 쌍이 양방향으로 있으면 n 을 합치고 방향은 더 큰 쪽을 남긴다
    — 동시 열람 강도를 하나로 본다(§3.2 4번: n 은 weight 로만 쓴다).

    한 번의 순회로 끝낸다(덤프가 수백만 행이라 씨드별 재스캔은 못 한다).
    """
    # (seed, neighbor) -> [outgoing_n, incoming_n]
    acc: dict[tuple[str, str], list[int]] = {}

    for row in rows:
        if row.prev in seeds and row.curr != row.prev:
            key = (row.prev, row.curr)
            acc.setdefault(key, [0, 0])[0] += row.n          # 씨드 -> 이웃 (나감)
        if row.curr in seeds and row.prev != row.curr:
            key = (row.curr, row.prev)
            acc.setdefault(key, [0, 0])[1] += row.n          # 이웃 -> 씨드 (들어옴)

    result: dict[str, list[NeighborRef]] = {s: [] for s in seeds}
    for (seed, neighbor), (out_n, in_n) in acc.items():
        total = out_n + in_n
        result[seed].append(NeighborRef(
            title=neighbor, n=total, directed=out_n >= in_n))
    # 이동량 큰 순으로 — 화면·디버깅이 강한 이웃부터 본다.
    for seed in result:
        result[seed].sort(key=lambda ref: ref.n, reverse=True)
    return result
