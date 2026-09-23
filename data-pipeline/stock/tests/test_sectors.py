"""산업(sector) 추출 테스트. 네트워크·DB 없이 돈다 (WP-204)."""

from __future__ import annotations

import pytest

from stock.sectors import sector_from_info


def test_sector_를_꺼낸다():
    assert sector_from_info({"sector": "Industrials", "industry": "Airlines"}) == "Industrials"


def test_앞뒤_공백은_지운다():
    assert sector_from_info({"sector": "  Technology "}) == "Technology"


@pytest.mark.parametrize(
    "info",
    [
        {},                    # SPAC·ADR·소형주는 sector 키 자체가 없다
        {"sector": None},
        {"sector": ""},
        {"sector": "   "},
        {"sector": 123},       # 비정상 타입을 그대로 저장하지 않는다
        None,                  # info 가 dict 가 아닌 경우
    ],
)
def test_없거나_비면_None(info):
    """None 이면 저장하지 않는다 — 빈 문자열이 들어가면 화면이 "산업 미제공" 대신 빈칸이 된다."""
    assert sector_from_info(info) is None
