"""결손 로그 테스트."""

from __future__ import annotations

from gdelt import gaps
from gdelt.catalog import Gap


def test_없는_파일은_빈_리스트(tmp_path):
    assert gaps.load(str(tmp_path / "nope.json")) == []


def test_기록_후_읽힌다(tmp_path):
    path = str(tmp_path / "gaps.json")
    added = gaps.record(
        path,
        [Gap("20250613000000", "20250704234500")],
        reason="404",
        now="2026-09-09T00:00:00Z",
    )
    assert added == 1
    loaded = gaps.load(path)
    assert loaded == [
        {
            "from": "20250613000000",
            "to": "20250704234500",
            "reason": "404",
            "recorded_at": "2026-09-09T00:00:00Z",
        }
    ]


def test_같은_구간_reason은_중복_안됨(tmp_path):
    path = str(tmp_path / "gaps.json")
    gaps.record(path, [Gap("20250613000000", "20250704234500")], reason="404")
    added = gaps.record(path, [Gap("20250613000000", "20250704234500")], reason="404")
    assert added == 0
    assert len(gaps.load(path)) == 1


def test_같은_구간이라도_reason이_다르면_추가(tmp_path):
    path = str(tmp_path / "gaps.json")
    gaps.record(path, [Gap("20250613000000", "20250613001500")], reason="missing")
    added = gaps.record(path, [Gap("20250613000000", "20250613001500")], reason="404")
    assert added == 1
    assert len(gaps.load(path)) == 2


def test_여러_구간_한번에(tmp_path):
    path = str(tmp_path / "sub" / "gaps.json")  # 부모 디렉터리 자동 생성 확인
    added = gaps.record(
        path,
        [Gap("20250613000000", "20250613001500"), Gap("20250704000000", "20250704234500")],
        reason="404",
    )
    assert added == 2
    assert len(gaps.load(path)) == 2
