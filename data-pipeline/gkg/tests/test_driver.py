"""드라이버의 순수 부분 — 슬롯 계획(결손 내성)·zip 파싱(손상 내성)·ticker 부착.

Spark 배선(spark_aggregate)은 pyspark 클러스터가 필요해 여기서 안 돈다. 대신
executor 가 실제로 하는 일(from_zip_bytes → aggregate)을 in-process 로 재현해
파이프라인이 이어지는지 본다.
"""

from __future__ import annotations

import io
import zipfile

from gkg.driver import (
    attach_tickers,
    from_zip_bytes,
    local_uri,
    plan_slots,
    spark_aggregate,
)
from gkg.lift import IssuePredicate, aggregate, rank
from gkg.match import build_ticker_index
from gkg.parse import MIN_COLUMNS


def _gkg_row(orgs_v1: str, themes: str, locations: str) -> str:
    cols = [""] * MIN_COLUMNS
    cols[4] = "https://example.com/a"
    cols[7] = themes
    cols[9] = locations
    cols[13] = orgs_v1
    return "\t".join(cols)


def _zip_of(rows: list[str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("20241010120000.gkg.csv", "\n".join(rows))
    return buf.getvalue()


# --- 슬롯 계획 (인수 조건 4: 결손이 있어도 멈추지 않는다) ------------------


def test_plan_slots_separates_present_and_missing():
    # 20241010 00:00~01:00 = 5 슬롯. 그중 2개만 존재한다고 하자.
    present_set = {"2024/10/10/20241010001500.gkg.csv.zip",
                   "2024/10/10/20241010004500.gkg.csv.zip"}
    present, missing = plan_slots(
        "20241010000000", "20241010010000", lambda rp: rp in present_set
    )
    assert set(present) == present_set
    assert len(present) == 2 and len(missing) == 3


def test_plan_slots_all_missing_is_not_an_error():
    present, missing = plan_slots("20250613000000", "20250613003000", lambda rp: False)
    assert present == []
    assert len(missing) == 3  # 결손 구간이어도 예외 없이 목록만 돌려준다


# --- zip 파싱 (손상 내성) --------------------------------------------------


def test_from_zip_bytes_parses_records():
    data = _zip_of([
        _gkg_row("Duke Energy", "NATURAL_DISASTER_HURRICANE", "1#Florida#US#USFL#28#-81#FL"),
        _gkg_row("Nvidia", "ECON_STOCKMARKET", "1#California#US#USCA#37#-122#CA"),
    ])
    recs = list(from_zip_bytes(data))
    assert len(recs) == 2
    assert recs[0].orgs == frozenset({"duke energy"})


def test_from_zip_bytes_bad_zip_returns_empty():
    assert list(from_zip_bytes(b"<html>404 not found</html>")) == []
    assert list(from_zip_bytes(b"")) == []


def test_from_zip_bytes_empty_archive_returns_empty():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w"):
        pass
    assert list(from_zip_bytes(buf.getvalue())) == []


# --- executor 재현: zip → aggregate → rank --------------------------------


def test_end_to_end_in_process():
    """binaryFiles 파티션이 하는 일을 in-process 로: 파일별 파싱·집계·병합."""
    p = IssuePredicate(themes=("HURRICANE",), locations=("florida",))
    file_a = _zip_of([
        _gkg_row("FPL", "NATURAL_DISASTER_HURRICANE", "1#Florida#US#USFL#28#-81#FL"),
        _gkg_row("FPL;Nvidia", "NATURAL_DISASTER_HURRICANE", "1#Florida#US#USFL#28#-81#FL"),
    ])
    file_b = _zip_of([
        _gkg_row("Nvidia", "ECON_STOCKMARKET", "1#California#US#USCA#37#-122#CA"),
        _gkg_row("Nvidia", "ECON_TECH", "1#Taiwan#TW#TW#23#121#TW"),
    ])
    # 파일별 부분합 → 병합 (Spark reduce 와 동형)
    agg = aggregate(from_zip_bytes(file_a), p).merge(aggregate(from_zip_bytes(file_b), p))
    assert agg.n_issue == 2 and agg.n_corpus == 4

    lifts = rank(agg, min_issue_count=1)
    top = lifts[0]
    assert top.org_name == "fpl"      # 이슈 기사에 몰림 → lift 최상
    assert top.lift > 1.0
    fpl = {o.org_name: o for o in lifts}["fpl"]
    assert (fpl.issue_count, fpl.corpus_count) == (2, 2)


def test_attach_tickers_labels_matched_and_null():
    p = IssuePredicate(themes=("HURRICANE",))
    agg = aggregate(
        [_r("duke energy"), _r("national hurricane center")], p
    )
    lifts = rank(agg, min_issue_count=1)
    index = build_ticker_index([("DUK", "Duke Energy Corporation")])
    tagged = dict((l.org_name, t) for l, t in attach_tickers(lifts, index))
    assert tagged["duke energy"] == "DUK"
    assert tagged["national hurricane center"] is None


def test_local_uri_has_file_scheme():
    uri = local_uri("gdelt-data", "2024/10/10/20241010000000.gkg.csv.zip")
    assert uri.startswith("file:///")
    assert uri.endswith("2024/10/10/20241010000000.gkg.csv.zip")


# spark_aggregate 는 import 만 확인한다(호출은 클러스터 필요).
def test_spark_aggregate_is_importable():
    assert callable(spark_aggregate)


def _r(org: str):
    from gkg.parse import Record
    return Record(doc_id="d", orgs=frozenset({org}),
                  themes=("NATURAL_DISASTER_HURRICANE",), locations=())
