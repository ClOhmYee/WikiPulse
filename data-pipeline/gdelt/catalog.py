"""GDELT 파일 목록·경로·시간 격자 계산.

이 모듈엔 네트워크·HDFS 의존이 없다 — 순수 함수라 테스트가 쉽다.
GDELT 파일 형식은 2026-09-09 실측으로 확인했다.

lastupdate.txt (3줄, 공백 3필드 `<size> <md5> <url>`)
    55367   958a30ae... http://data.gdeltproject.org/gdeltv2/20260909041500.export.CSV.zip
    69899   4f032c00... http://data.gdeltproject.org/gdeltv2/20260909041500.mentions.CSV.zip
    2971040 7ec9e467... http://data.gdeltproject.org/gdeltv2/20260909041500.gkg.csv.zip
    → 우리는 .gkg.csv.zip 줄만 쓴다.

masterfilelist.txt
    2015-02-18 23:00:00 부터 지금까지 export/mentions/gkg 가 섞여 시간순으로 쌓인 전체 목록.
    같은 3필드 형식. gkg 줄만 걸러 쓴다. 놓친 구간을 채울 때(백필) 이걸 본다.

⚠️ URL 은 http:// 인데 실제로는 https 로 301 리다이렉트된다 (2026-09-09 실측).
   다운로드는 리다이렉트를 따라가야 한다 (fetch.py).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

GKG_SUFFIX = ".gkg.csv.zip"
TS_FORMAT = "%Y%m%d%H%M%S"  # 20260909041500
SLOT_MINUTES = 15  # GDELT 2.0 은 15분 간격 (:00 :15 :30 :45)

# GDELT 2.0 GKG 최초 파일 (masterfilelist 첫 gkg 줄, 2026-09-09 실측).
# 백필 범위를 이보다 앞으로 요청하면 결손만 잔뜩 잡히므로 하한으로 쓴다.
GDELT_V2_START = "20150218230000"

# 파일명 앞 14자리가 타임스탬프다: .../20260909041500.gkg.csv.zip
_TS_RE = re.compile(r"(\d{14})\.gkg\.csv\.zip$")


@dataclass(frozen=True)
class GkgFile:
    """GDELT GKG 파일 하나. size·md5 는 목록에 있으면 채우고, 없으면 None."""

    timestamp: str  # 14자리 YYYYMMDDHHMMSS (UTC)
    url: str
    size: int | None = None
    md5: str | None = None

    @property
    def relpath(self) -> str:
        """싱크(HDFS/로컬) 상대경로: YYYY/MM/DD/<ts>.gkg.csv.zip

        날짜로 파티션을 나눠 Spark 배치가 하루치를 통째로 읽기 좋게 한다.
        파일명은 타임스탬프 그대로 — 이슈 요구사항.
        """
        ts = self.timestamp
        return f"{ts[0:4]}/{ts[4:6]}/{ts[6:8]}/{ts}{GKG_SUFFIX}"


@dataclass(frozen=True)
class Gap:
    """연속된 결손 구간 [start, end] (둘 다 15분 격자 슬롯, 포함)."""

    start: str
    end: str


def timestamp_from_url(url: str) -> str:
    """gkg URL 에서 14자리 타임스탬프를 뽑는다."""
    match = _TS_RE.search(url)
    if match is None:
        raise ValueError(f"gkg URL 에서 타임스탬프를 못 찾음: {url}")
    return match.group(1)


def parse_line(line: str) -> tuple[int | None, str | None, str]:
    """목록 한 줄을 (size, md5, url) 로. url 은 항상, size·md5 는 있으면 채운다.

    정상은 3필드다. 혹시 url 만 있는 줄이 와도 그건 살린다(관대하게).
    필드 수가 그 외면 형식이 바뀐 것이므로 조용히 넘기지 않고 예외를 던진다.
    """
    parts = line.split()
    if len(parts) == 3:
        size_str, md5, url = parts
        try:
            size: int | None = int(size_str)
        except ValueError:
            size = None
        return size, md5, url
    if len(parts) == 1:
        return None, None, parts[0]
    raise ValueError(f"목록 줄 형식이 예상과 다름(필드 {len(parts)}개): {line!r}")


def _gkg(size: int | None, md5: str | None, url: str) -> GkgFile:
    return GkgFile(timestamp=timestamp_from_url(url), url=url, size=size, md5=md5)


def parse_lastupdate(text: str) -> GkgFile:
    """lastupdate.txt 에서 gkg 줄 하나를 GkgFile 로. 없으면 ValueError."""
    for raw in text.splitlines():
        line = raw.strip()
        if line and line.endswith(GKG_SUFFIX):
            return _gkg(*parse_line(line))
    raise ValueError("lastupdate.txt 에 .gkg.csv.zip 줄이 없다")


def parse_masterlist(lines: Iterable[str]) -> Iterator[GkgFile]:
    """masterfilelist 에서 gkg 줄만 GkgFile 로 흘려보낸다.

    파일이 수백 MB 라 전체를 문자열로 들지 않고 줄 이터러블(응답 스트림)을 받는다.
    """
    for raw in lines:
        line = raw.strip()
        if line and line.endswith(GKG_SUFFIX):
            yield _gkg(*parse_line(line))


# --- 15분 시간 격자 -------------------------------------------------------

def parse_ts(ts: str) -> datetime:
    """14자리 타임스탬프 -> UTC datetime."""
    return datetime.strptime(ts, TS_FORMAT).replace(tzinfo=timezone.utc)


def format_ts(dt: datetime) -> str:
    return dt.strftime(TS_FORMAT)


def floor_to_slot(dt: datetime) -> datetime:
    """15분 격자 아래로 내림 (:07 -> :00, :22 -> :15)."""
    minute = (dt.minute // SLOT_MINUTES) * SLOT_MINUTES
    return dt.replace(minute=minute, second=0, microsecond=0)


def iter_slots(start: datetime, end: datetime) -> Iterator[str]:
    """[start, end] 구간의 15분 격자 타임스탬프. 양 끝은 슬롯으로 내림해 포함한다.

    "지금까지 나왔어야 할 파일"의 기준 격자다. 이 격자에서 실제 존재를 빼면 결손이다.
    """
    step = timedelta(minutes=SLOT_MINUTES)
    cur = floor_to_slot(start)
    last = floor_to_slot(end)
    while cur <= last:
        yield format_ts(cur)
        cur += step


def coalesce_gaps(missing: Iterable[str]) -> list[Gap]:
    """결손 슬롯들을 연속 구간으로 합친다.

    [.0000, .0015, .0030, .0100] -> [Gap(.0000, .0030), Gap(.0100, .0100)]
    정렬·중복제거는 여기서 한다.
    """
    slots = sorted(set(missing))
    if not slots:
        return []
    step = timedelta(minutes=SLOT_MINUTES)
    gaps: list[Gap] = []
    run_start = prev = slots[0]
    for ts in slots[1:]:
        if parse_ts(ts) - parse_ts(prev) == step:
            prev = ts
            continue
        gaps.append(Gap(run_start, prev))
        run_start = prev = ts
    gaps.append(Gap(run_start, prev))
    return gaps
