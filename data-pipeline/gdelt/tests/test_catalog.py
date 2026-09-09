"""catalog 순수 함수 테스트. 네트워크 없이 돈다.

샘플 줄은 2026-09-09 GDELT 에서 실제로 받은 것이다.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from gdelt import catalog

# 2026-09-09 lastupdate.txt 실제 내용
LASTUPDATE = (
    "55367 958a30ae081859ce7e25625f924652b9 "
    "http://data.gdeltproject.org/gdeltv2/20260909041500.export.CSV.zip\n"
    "69899 4f032c0042ab4dc8737016f59e7bad75 "
    "http://data.gdeltproject.org/gdeltv2/20260909041500.mentions.CSV.zip\n"
    "2971040 7ec9e467dee3c83c00136af03243e027 "
    "http://data.gdeltproject.org/gdeltv2/20260909041500.gkg.csv.zip\n"
)

# masterfilelist 앞부분 실제 내용 (2015-02-18 첫 두 슬롯)
MASTERLIST = (
    "150383 297a16b493de7cf6ca809a7cc31d0b93 "
    "http://data.gdeltproject.org/gdeltv2/20150218230000.export.CSV.zip\n"
    "318084 bb27f78ba45f69a17ea6ed7755e9f8ff "
    "http://data.gdeltproject.org/gdeltv2/20150218230000.mentions.CSV.zip\n"
    "10768507 ea8dde0beb0ba98810a92db068c0ce99 "
    "http://data.gdeltproject.org/gdeltv2/20150218230000.gkg.csv.zip\n"
    "149211 2a91041d7e72b0fc6a629e2ff867b240 "
    "http://data.gdeltproject.org/gdeltv2/20150218231500.export.CSV.zip\n"
    "10269336 2f1a504a3c4558694ade0442e9a5ae6f "
    "http://data.gdeltproject.org/gdeltv2/20150218231500.gkg.csv.zip\n"
)


def test_lastupdate에서_gkg_줄만_고른다():
    gkg = catalog.parse_lastupdate(LASTUPDATE)
    assert gkg.timestamp == "20260909041500"
    assert gkg.url.endswith("20260909041500.gkg.csv.zip")
    assert gkg.size == 2971040
    assert gkg.md5 == "7ec9e467dee3c83c00136af03243e027"


def test_lastupdate에_gkg가_없으면_예외():
    with pytest.raises(ValueError):
        catalog.parse_lastupdate("1 abc http://x/20260909041500.export.CSV.zip\n")


def test_masterlist는_gkg만_흘려보낸다():
    files = list(catalog.parse_masterlist(MASTERLIST.splitlines()))
    # export·mentions 는 빠지고 gkg 2개만
    assert [f.timestamp for f in files] == ["20150218230000", "20150218231500"]
    assert files[0].size == 10768507
    assert files[0].md5 == "ea8dde0beb0ba98810a92db068c0ce99"


def test_relpath는_날짜_파티션_레이아웃():
    gkg = catalog.GkgFile(timestamp="20260909041500", url="http://x")
    assert gkg.relpath == "2026/09/09/20260909041500.gkg.csv.zip"


def test_timestamp_추출_실패는_예외():
    with pytest.raises(ValueError):
        catalog.timestamp_from_url("http://x/notatimestamp.gkg.csv.zip")


def test_parse_line_url만_있는_1필드는_허용():
    # 형식이 관대해야 하는 경우 — size·md5 없이 url 만.
    size, md5, url = catalog.parse_line("http://x/20260909041500.gkg.csv.zip")
    assert (size, md5) == (None, None)
    assert url.endswith(".gkg.csv.zip")


def test_parse_line_두필드_네필드는_예외():
    with pytest.raises(ValueError):
        catalog.parse_line("size md5")  # 2필드 — url 누락
    with pytest.raises(ValueError):
        catalog.parse_line("size md5 url extra")  # 4필드


def test_parse_line_size가_숫자가_아니면_None():
    size, md5, url = catalog.parse_line("NOTINT abc http://x/20260909041500.gkg.csv.zip")
    assert size is None
    assert md5 == "abc"


# --- 15분 격자 ---

def _utc(y, mo, d, h, mi):
    return datetime(y, mo, d, h, mi, tzinfo=timezone.utc)


def test_iter_slots_양_끝을_슬롯으로_내려_포함():
    # 04:07 ~ 04:52 -> 04:00, 04:15, 04:30, 04:45
    slots = list(catalog.iter_slots(_utc(2026, 9, 9, 4, 7), _utc(2026, 9, 9, 4, 52)))
    assert slots == [
        "20260909040000",
        "20260909041500",
        "20260909043000",
        "20260909044500",
    ]


def test_iter_slots_같은_슬롯이면_한개():
    slots = list(catalog.iter_slots(_utc(2026, 9, 9, 4, 1), _utc(2026, 9, 9, 4, 14)))
    assert slots == ["20260909040000"]


def test_floor_to_slot():
    assert catalog.floor_to_slot(_utc(2026, 9, 9, 4, 22)) == _utc(2026, 9, 9, 4, 15)


def test_coalesce_gaps_연속은_한_구간_끊기면_나눔():
    missing = [
        "20260909040000",
        "20260909041500",
        "20260909043000",  # 04:15 다음 04:30 — 연속
        "20260909050000",  # 점프
    ]
    gaps = catalog.coalesce_gaps(missing)
    assert gaps == [
        catalog.Gap("20260909040000", "20260909043000"),
        catalog.Gap("20260909050000", "20260909050000"),
    ]


def test_coalesce_gaps_정렬_중복제거():
    gaps = catalog.coalesce_gaps(["20260909041500", "20260909040000", "20260909040000"])
    assert gaps == [catalog.Gap("20260909040000", "20260909041500")]


def test_coalesce_gaps_빈입력():
    assert catalog.coalesce_gaps([]) == []
