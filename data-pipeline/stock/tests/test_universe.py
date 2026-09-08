"""종목 유니버스 파싱·필터 테스트. 네트워크 없이 돈다.

표본은 2026-09-08 에 받은 실제 파일 형식이다.
"""

from __future__ import annotations

from stock.universe import (
    build_universe,
    load_sec_index,
    parse_nasdaq,
    parse_other,
    _is_common,
)

# 실제 nasdaqlisted.txt 헤더 + 골라낸 행들
NASDAQ_SAMPLE = "\n".join(
    [
        "Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares",
        "AAPL|Apple Inc. - Common Stock|Q|N|N|100|N|N",
        "NVDA|NVIDIA Corporation - Common Stock|Q|N|N|100|N|N",
        "QQQ|Invesco QQQ Trust|Q|N|N|100|Y|N",  # ETF — 빠져야 함
        "ZTEST|NASDAQ TEST STOCK|Q|Y|N|100|N|N",  # Test Issue — 빠져야 함
        "ABCDpA|Some Preferred - Preferred Stock|Q|N|N|100|N|N",  # 우선주 — 이름으로 빠짐
        "File Creation Time: 0908202609:00|||||||",
    ]
)

# 실제 otherlisted.txt 헤더 + 행
OTHER_SAMPLE = "\n".join(
    [
        "ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol",
        "XOM|Exxon Mobil Corporation Common Stock|N|XOM|N|100|N|XOM",
        "AA|Alcoa Corporation Common Stock |N|AA|N|100|N|AA",  # 뒤 공백
        "SPY|SPDR S&P 500 ETF Trust|P|SPY|Y|100|N|SPY",  # ETF + Arca — 빠짐
        "AGM.A|Federal Agricultural Mortgage - Class A|N|AGM.A|N|100|N|",  # 클래스 표기
        "File Creation Time: 0908202609:00|||||||",
    ]
)

SEC_SAMPLE = (
    '{"0":{"cik_str":320193,"ticker":"AAPL","title":"Apple Inc."},'
    '"1":{"cik_str":1045810,"ticker":"NVDA","title":"NVIDIA CORP"},'
    '"2":{"cik_str":34088,"ticker":"XOM","title":"EXXON MOBIL CORP"}}'
)


def test_나스닥은_보통주만_남긴다():
    stocks = parse_nasdaq(NASDAQ_SAMPLE)
    tickers = {s.ticker for s in stocks}
    assert tickers == {"AAPL", "NVDA"}
    assert all(s.exchange == "NASDAQ" for s in stocks)


def test_etf_와_test_이슈는_빠진다():
    tickers = {s.ticker for s in parse_nasdaq(NASDAQ_SAMPLE)}
    assert "QQQ" not in tickers  # ETF
    assert "ZTEST" not in tickers  # Test Issue
    assert "ABCDpA" not in tickers  # 우선주 (이름으로)


def test_otherlisted는_거래소를_매핑한다():
    stocks = {s.ticker: s for s in parse_other(OTHER_SAMPLE)}
    assert stocks["XOM"].exchange == "NYSE"
    assert "SPY" not in stocks  # ETF + Arca


def test_otherlisted_이름_공백을_다듬는다():
    stocks = {s.ticker: s for s in parse_other(OTHER_SAMPLE)}
    assert stocks["AA"].name == "Alcoa Corporation Common Stock"  # 뒤 공백 제거


def test_sec_인덱스는_cik를_10자리로_채운다():
    index = load_sec_index(SEC_SAMPLE)
    cik, name = index["XOM"]
    assert cik == "0000034088"  # 34088 -> 10자리
    assert name == "EXXON MOBIL CORP"


def test_common_판별():
    assert _is_common("Apple Inc. - Common Stock")
    assert _is_common("Alibaba Group - Ordinary Shares")
    assert _is_common("Alphabet Inc. Class A Common Stock")
    assert not _is_common("Some Fund - Preferred Stock")
    assert not _is_common("Acme - Warrant")
    assert not _is_common("Acme - Unit")


def test_티커_충돌은_먼저_온_것을_쓴다(monkeypatch):
    """같은 티커가 나스닥·NYSE 양쪽에 있으면 나스닥(먼저 합침)이 이긴다."""
    import stock.universe as u

    monkeypatch.setattr(u, "_fetch", lambda url: {
        u.NASDAQ_LISTED: NASDAQ_SAMPLE,
        u.OTHER_LISTED: OTHER_SAMPLE,
        u.SEC_TICKERS: SEC_SAMPLE,
    }[url])

    universe = build_universe()
    tickers = {s.ticker for s in universe}
    # AAPL·NVDA(나스닥) + XOM·AA(NYSE). AGM.A 는 SEC 에 없어도 들어온다.
    assert {"AAPL", "NVDA", "XOM", "AA"} <= tickers


def test_sec_이름이_거래소_이름을_이긴다(monkeypatch):
    """거래소 파일 이름은 '- Common Stock' 접미가 붙어 지저분하다."""
    import stock.universe as u

    monkeypatch.setattr(u, "_fetch", lambda url: {
        u.NASDAQ_LISTED: NASDAQ_SAMPLE,
        u.OTHER_LISTED: OTHER_SAMPLE,
        u.SEC_TICKERS: SEC_SAMPLE,
    }[url])

    by_ticker = {s.ticker: s for s in build_universe()}
    assert by_ticker["AAPL"].name == "Apple Inc."  # SEC 이름
    assert by_ticker["XOM"].cik == "0000034088"
    # SEC 에 없는 종목은 거래소 이름을 그대로 쓴다
    assert by_ticker["AA"].name == "Alcoa Corporation Common Stock"
    assert by_ticker["AA"].cik is None
