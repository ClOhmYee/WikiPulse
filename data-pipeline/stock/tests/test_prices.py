"""일봉 변환 테스트. 네트워크·DB 없이 돈다.

yfinance history() 가 주는 형태(DatetimeIndex + OHLCV 컬럼)를 흉내낸 pandas
DataFrame 으로 rows_from_history 의 결측·형변환 처리를 확인한다.
"""

from __future__ import annotations

import datetime as dt

import pandas as pd

from stock.prices import _clean, rows_from_history, select_targets


def _df(records: list[dict]) -> pd.DataFrame:
    """records: [{'date': 'YYYY-MM-DD', 'Open':..., ...}] → DatetimeIndex DataFrame."""
    index = pd.DatetimeIndex([pd.Timestamp(r["date"]) for r in records])
    data = {k: [r.get(k) for r in records] for k in ("Open", "High", "Low", "Close", "Volume")}
    return pd.DataFrame(data, index=index)


def test_normal_rows():
    df = _df(
        [
            {"date": "2026-09-04", "Open": 178.2, "High": 181.0, "Low": 177.4, "Close": 180.6, "Volume": 41203300},
            {"date": "2026-09-05", "Open": 180.0, "High": 182.5, "Low": 179.1, "Close": 181.9, "Volume": 39001200},
        ]
    )
    rows = rows_from_history("NVDA", df)
    assert rows == [
        ("NVDA", dt.date(2026, 9, 4), 178.2, 181.0, 177.4, 180.6, 41203300),
        ("NVDA", dt.date(2026, 9, 5), 180.0, 182.5, 179.1, 181.9, 39001200),
    ]


def test_index_becomes_date():
    df = _df([{"date": "2026-01-02", "Open": 1, "High": 1, "Low": 1, "Close": 1, "Volume": 10}])
    (row,) = rows_from_history("AAPL", df)
    assert row[1] == dt.date(2026, 1, 2)
    assert isinstance(row[1], dt.date)


def test_nan_close_row_dropped():
    # close 는 스키마 NOT NULL — 결측 날은 통째로 버린다.
    df = _df(
        [
            {"date": "2026-09-04", "Open": 10, "High": 11, "Low": 9, "Close": float("nan"), "Volume": 100},
            {"date": "2026-09-05", "Open": 10, "High": 11, "Low": 9, "Close": 10.5, "Volume": 100},
        ]
    )
    rows = rows_from_history("T", df)
    assert len(rows) == 1
    assert rows[0][1] == dt.date(2026, 9, 5)


def test_nan_ohlc_becomes_none_but_keeps_row():
    # open/high/low 는 nullable — 결측이어도 close 만 있으면 행은 남긴다.
    df = _df([{"date": "2026-09-05", "Open": float("nan"), "High": float("nan"), "Low": 9.0, "Close": 10.5, "Volume": 100}])
    (row,) = rows_from_history("T", df)
    assert row[2] is None  # open
    assert row[3] is None  # high
    assert row[4] == 9.0   # low
    assert row[5] == 10.5  # close


def test_nan_volume_becomes_none():
    df = _df([{"date": "2026-09-05", "Open": 10, "High": 11, "Low": 9, "Close": 10.5, "Volume": float("nan")}])
    (row,) = rows_from_history("T", df)
    assert row[6] is None


def test_volume_is_int():
    df = _df([{"date": "2026-09-05", "Open": 10, "High": 11, "Low": 9, "Close": 10.5, "Volume": 100.0}])
    (row,) = rows_from_history("T", df)
    assert row[6] == 100
    assert isinstance(row[6], int)


def test_empty_dataframe():
    df = _df([])
    assert rows_from_history("T", df) == []


def test_clean_filters_nan_and_inf():
    assert _clean(None) is None
    assert _clean(float("nan")) is None
    assert _clean(float("inf")) is None
    assert _clean(3) == 3.0
    assert isinstance(_clean(3), float)


def test_volume_inf_becomes_none():
    # int(inf) 는 OverflowError 라 그 종목 처리가 죽는다 — _clean 으로 막았는지 확인.
    df = _df([{"date": "2026-09-05", "Open": 10, "High": 11, "Low": 9, "Close": 10.5, "Volume": float("inf")}])
    (row,) = rows_from_history("T", df)
    assert row[6] is None


# --- select_targets (P2-D: --tickers FK 가드) ---

MASTER = ["AAPL", "MSFT", "NVDA"]


def test_select_targets_none_is_full_master():
    targets, unknown = select_targets(MASTER, None, None)
    assert targets == MASTER
    assert unknown == []


def test_select_targets_filters_unknown():
    targets, unknown = select_targets(MASTER, ["AAPL", "FAKE", "NVDA"], None)
    assert targets == ["AAPL", "NVDA"]  # 마스터에 있는 것만, 순서 보존
    assert unknown == ["FAKE"]


def test_select_targets_all_unknown_gives_empty():
    targets, unknown = select_targets(MASTER, ["FAKE", "NOPE"], None)
    assert targets == []
    assert unknown == ["FAKE", "NOPE"]


def test_select_targets_limit_applies():
    targets, _ = select_targets(MASTER, None, 2)
    assert targets == ["AAPL", "MSFT"]
