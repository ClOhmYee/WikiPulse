"""드라이버의 순수 부분 — 슬롯 계획(결손 내성)·zip 파싱(손상 내성)·파일 회계·ticker.

Spark 배선(spark_aggregate)은 클러스터가 필요해 여기서 안 돈다. 대신 executor 가
파일마다 실제로 부르는 fold_file(predicate) 을 in-process 로 접어 driver 의 그 코드
경로 자체(파일별 부분합 + files/empty_files 회계 + merge)를 검증한다.
"""

from __future__ import annotations

import functools
import io
import zipfile

from gkg.driver import (
    attach_tickers,
    fold_file,
    from_zip_bytes,
    local_uri,
    plan_slots,
    spark_aggregate,
)
from gkg.lift import IssuePredicate, aggregate, rank
from gkg.match import build_ticker_index
from gkg.parse import MIN_COLUMNS, Record


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


def test_슬롯계획은_존재와_결손을_가른다():
    # 20241010 00:00~01:00 = 5 슬롯. 그중 2개만 존재한다고 하자.
    present_set = {"2024/10/10/20241010001500.gkg.csv.zip",
                   "2024/10/10/20241010004500.gkg.csv.zip"}
    present, missing = plan_slots(
        "20241010000000", "20241010010000", lambda rp: rp in present_set
    )
    assert set(present) == present_set
    assert len(present) == 2 and len(missing) == 3


def test_전부_결손이어도_에러가_아니다():
    present, missing = plan_slots("20250613000000", "20250613003000", lambda rp: False)
    assert present == []
    assert len(missing) == 3  # 결손 구간이어도 예외 없이 목록만 돌려준다


# --- zip 파싱 (손상 내성) --------------------------------------------------


def test_zip에서_레코드를_파싱한다():
    data = _zip_of([
        _gkg_row("Duke Energy", "NATURAL_DISASTER_HURRICANE", "1#Florida#US#USFL#28#-81#FL"),
        _gkg_row("Nvidia", "ECON_STOCKMARKET", "1#California#US#USCA#37#-122#CA"),
    ])
    recs = list(from_zip_bytes(data))
    assert len(recs) == 2
    assert recs[0].orgs == frozenset({"duke energy"})


def test_손상_zip은_빈_결과():
    assert list(from_zip_bytes(b"<html>404 not found</html>")) == []
    assert list(from_zip_bytes(b"")) == []


def test_빈_아카이브는_빈_결과():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w"):
        pass
    assert list(from_zip_bytes(buf.getvalue())) == []


# --- fold_file: 파일 단위 회계 (손상 가시성) -------------------------------


def test_fold는_파일을_세고_손상을_표시한다():
    p = IssuePredicate(themes=("HURRICANE",))
    fold = fold_file(p)
    good = fold(("f1", _zip_of([
        _gkg_row("FPL", "NATURAL_DISASTER_HURRICANE", "1#Florida#US#USFL#28#-81#FL")])))
    bad = fold(("f2", b"<html>404</html>"))
    assert (good.files, good.empty_files) == (1, 0)
    assert (bad.files, bad.empty_files) == (1, 1)   # 손상 파일이 empty_files 로 잡힘
    merged = good.merge(bad)
    assert merged.files == 2 and merged.empty_files == 1
    # 손상 파일은 코퍼스에 0 기여 — good 만 집계된다.
    assert merged.n_corpus == 1


def test_executor_경로를_in_process로_접는다():
    """spark_aggregate 가 하는 일(map(fold_file)→reduce merge)을 그대로 재현."""
    p = IssuePredicate(themes=("HURRICANE",), locations=("florida",))
    files = [
        ("a", _zip_of([
            _gkg_row("FPL", "NATURAL_DISASTER_HURRICANE", "1#Florida#US#USFL#28#-81#FL"),
            _gkg_row("FPL;Nvidia", "NATURAL_DISASTER_HURRICANE", "1#Florida#US#USFL#28#-81#FL")])),
        ("b", _zip_of([
            _gkg_row("Nvidia", "ECON_STOCKMARKET", "1#California#US#USCA#37#-122#CA"),
            _gkg_row("Nvidia", "ECON_TECH", "1#Taiwan#TW#TW#23#121#TW")])),
    ]
    fold = fold_file(p)
    agg = functools.reduce(lambda x, y: x.merge(y), map(fold, files))
    assert agg.files == 2 and agg.empty_files == 0
    assert agg.n_issue == 2 and agg.n_corpus == 4

    lifts = rank(agg, min_issue_count=1)
    top = lifts[0]
    assert top.org_name == "fpl"      # 이슈 기사에 몰림 → lift 최상
    assert top.lift > 1.0
    fpl = {o.org_name: o for o in lifts}["fpl"]
    assert (fpl.issue_count, fpl.corpus_count) == (2, 2)


def test_ticker_부착은_매칭과_NULL을_구분한다():
    p = IssuePredicate(themes=("HURRICANE",))
    agg = aggregate([_r("duke energy"), _r("national hurricane center")], p)
    lifts = rank(agg, min_issue_count=1)
    index = build_ticker_index([("DUK", "Duke Energy Corporation")])
    tagged = dict((l.org_name, t) for l, t in attach_tickers(lifts, index))
    assert tagged["duke energy"] == "DUK"
    assert tagged["national hurricane center"] is None


def test_local_uri는_file_스킴을_붙인다():
    uri = local_uri("gdelt-data", "2024/10/10/20241010000000.gkg.csv.zip")
    assert uri.startswith("file:///")
    assert uri.endswith("2024/10/10/20241010000000.gkg.csv.zip")


# spark_aggregate 는 import 만 확인한다(호출은 클러스터 필요).
def test_spark_aggregate는_import된다():
    assert callable(spark_aggregate)


def _r(org: str):
    return Record(doc_id="d", orgs=frozenset({org}),
                  themes=("NATURAL_DISASTER_HURRICANE",), locations=())
