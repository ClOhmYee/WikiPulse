"""RecentChanges 시간별 수집기 (WP-164).

네트워크 없이 돈다 — `_fetch` 를 가짜로 갈아끼운다. 여기서 지키려는 건 두 가지다.

1. **끝 경계 배타.** `rcend` 포함 여부를 API 쪽 계약으로 믿지 않고 직접 자른다.
   안 그러면 한 행이 두 시간 파일에 들어가 이음매에서 중복이 난다.
2. **`.part` 가 완료로 보이지 않는 것.** 중간에 죽은 파일이 정상 산출물로 집계되면
   결손을 조용히 놓친다 — 덤프 429 함정(169 B HTML 이 gzip 인 척)과 같은 형태다.

⚠️ CLI 가 실제로 기동하는지도 본다. `gkg/driver.py` 가 상대 임포트라
`spark-submit` 으로 안 도는데 CLI 테스트가 없어 아무도 몰랐던 전례가 있다.
"""

from __future__ import annotations

import gzip
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from batch import recentchanges
from batch.recentchanges import (
    HourFailed,
    collect,
    fetch_hour,
    hour_path,
    hours,
    verify,
    write_hour,
)

UTC = timezone.utc
HOUR = datetime(2026, 9, 1, 2, 0, tzinfo=UTC)


def _row(minute: int, rcid: int, *, bot: bool = False, second: int = 0) -> dict:
    stamp = HOUR + timedelta(minutes=minute, seconds=second)
    row = {
        "type": "edit", "ns": 0, "title": f"Page {rcid}", "pageid": 1000 + rcid,
        "revid": 2000 + rcid, "rcid": rcid,
        "timestamp": stamp.strftime(recentchanges.TS),
    }
    if bot:
        row["bot"] = True
    return row


def _fake_fetch(pages):
    """`pages` 를 순서대로 돌려주는 `_fetch` 대역. 마지막 장에는 continue 가 없다."""
    calls = []

    def fetch(params):
        calls.append(params)
        index = len(calls) - 1
        rows = pages[index]
        body = {"query": {"recentchanges": rows}}
        if index + 1 < len(pages):
            body["continue"] = {"rccontinue": f"page{index + 1}", "continue": "-||"}
        return body, 0

    fetch.calls = calls
    return fetch


def test_hours_는_끝을_포함하지_않는다():
    start, end = HOUR, HOUR + timedelta(hours=3)
    assert list(hours(start, end)) == [
        HOUR, HOUR + timedelta(hours=1), HOUR + timedelta(hours=2)]


def test_hour_path_는_UTC_경로로_나뉜다(tmp_path):
    assert hour_path(tmp_path, HOUR) == (
        tmp_path / "enwiki" / "2026" / "09" / "01" / "02.ndjson.gz")


def test_끝_경계의_행은_버린다(monkeypatch):
    """`rcend` 가 포함으로 오더라도 다음 시간 것은 이 파일에 넣지 않는다."""
    next_hour = _row(60, 99)                     # 03:00:00 — 다음 시간 소유
    monkeypatch.setattr(recentchanges, "_fetch",
                        _fake_fetch([[_row(0, 1), _row(59, 2, second=59), next_hour]]))

    rows, calls, throttled = fetch_hour(HOUR, delay=0)

    assert [r["rcid"] for r in rows] == [1, 2]
    assert calls == 1 and throttled == 0


def test_continue_가_겹쳐도_rcid_로_중복이_제거된다(monkeypatch):
    monkeypatch.setattr(recentchanges, "_fetch",
                        _fake_fetch([[_row(0, 1), _row(1, 2)],
                                     [_row(1, 2), _row(2, 3)]]))

    rows, calls, _ = fetch_hour(HOUR, delay=0)

    assert [r["rcid"] for r in rows] == [1, 2, 3]
    assert calls == 2


def test_행은_시각순으로_정렬된다(monkeypatch):
    monkeypatch.setattr(recentchanges, "_fetch",
                        _fake_fetch([[_row(30, 3), _row(0, 1), _row(10, 2)]]))

    rows, _, _ = fetch_hour(HOUR, delay=0)

    assert [r["rcid"] for r in rows] == [1, 2, 3]


def test_API_오류는_그_시간만_실패시킨다(monkeypatch):
    def fetch(params):
        return {"error": {"code": "readapidenied"}}, 0

    monkeypatch.setattr(recentchanges, "_fetch", fetch)

    with pytest.raises(HourFailed):
        fetch_hour(HOUR, delay=0)


def test_write_hour_는_part_를_남기지_않는다(tmp_path):
    path = hour_path(tmp_path, HOUR)

    size = write_hour(path, [_row(0, 1), _row(1, 2, bot=True)])

    assert size > 0
    assert not list(tmp_path.rglob("*.part"))
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        rows = [json.loads(line) for line in fh]
    assert [r["rcid"] for r in rows] == [1, 2]
    assert rows[1]["bot"] is True


def test_이미_받은_시간은_다시_받지_않는다(tmp_path, monkeypatch, capsys):
    write_hour(hour_path(tmp_path, HOUR), [_row(0, 1)])
    called = []

    def fetch(params):
        called.append(params)
        return {"query": {"recentchanges": [_row(0, 7)]}}, 0

    monkeypatch.setattr(recentchanges, "_fetch", fetch)

    code = collect(HOUR, HOUR + timedelta(hours=2), tmp_path, delay=0)

    assert code == 0
    assert len(called) == 1, "두 번째 시간만 받아야 한다"
    assert "건너뜀 1" in capsys.readouterr().out


def test_실패한_시간이_있으면_manifest_와_종료코드에_남는다(tmp_path, monkeypatch):
    def fetch(params):
        raise HourFailed("HTTP 500")

    monkeypatch.setattr(recentchanges, "_fetch", fetch)

    code = collect(HOUR, HOUR + timedelta(hours=1), tmp_path, delay=0)

    assert code == 1
    records = [json.loads(line) for line
               in (tmp_path / "manifest.jsonl").read_text(encoding="utf-8").splitlines()]
    assert records[0]["status"] == "failed"
    assert records[0]["error"] == "HTTP 500"


def test_manifest_는_제목_기준을_현재로_적는다(tmp_path, monkeypatch):
    """⚠️ 덤프는 historical 이다. 이 표시가 없으면 나중에 구분이 안 된다."""
    monkeypatch.setattr(recentchanges, "_fetch",
                        _fake_fetch([[_row(0, 1), _row(2, 2, bot=True)]]))

    collect(HOUR, HOUR + timedelta(hours=1), tmp_path, delay=0)

    record = json.loads((tmp_path / "manifest.jsonl").read_text(encoding="utf-8"))
    assert record["title_basis"] == "current"
    assert record["rows"] == 2 and record["bots"] == 1
    assert record["first_ts"] == "2026-09-01T02:00:00Z"


def test_verify_는_결손을_찾는다(tmp_path, capsys):
    write_hour(hour_path(tmp_path, HOUR), [_row(0, 1)])

    code = verify(HOUR, HOUR + timedelta(hours=2), tmp_path)

    assert code == 1
    assert "결손 1시간" in capsys.readouterr().out


def test_verify_는_0행_시간을_정상으로_보지_않는다(tmp_path, capsys):
    """파일 존재만 보면 빈 시간이 통과한다. enwiki ns0 는 시간당 1만 행대다."""
    write_hour(hour_path(tmp_path, HOUR), [])

    code = verify(HOUR, HOUR + timedelta(hours=1), tmp_path)

    assert code == 1
    assert "0행 시간 1개" in capsys.readouterr().out


def test_verify_는_남은_part_를_경고한다(tmp_path, capsys):
    path = hour_path(tmp_path, HOUR)
    write_hour(path, [_row(0, 1)])
    path.with_suffix(path.suffix + ".part").write_bytes(b"deadbeef")

    code = verify(HOUR, HOUR + timedelta(hours=1), tmp_path)

    assert code == 1
    assert "`.part` 1개" in capsys.readouterr().out


def test_verify_는_다_받았으면_0_을_돌려준다(tmp_path, capsys):
    write_hour(hour_path(tmp_path, HOUR), [_row(0, 1)])

    code = verify(HOUR, HOUR + timedelta(hours=1), tmp_path)

    assert code == 0
    assert "결손 없음" in capsys.readouterr().out


def test_start_가_end_보다_뒤면_거부한다(tmp_path):
    result = _run_cli("--start", "2026-09-02T00:00:00Z",
                      "--end", "2026-09-01T00:00:00Z", "--out", str(tmp_path))
    assert result.returncode == 2


def test_CLI_가_모듈로_기동한다(tmp_path):
    """⚠️ `python -m batch.recentchanges` 로 실제로 도는지 본다."""
    result = _run_cli("--verify", "--start", "2026-09-01T02:00:00Z",
                      "--end", "2026-09-01T03:00:00Z", "--out", str(tmp_path))
    assert result.returncode == 1
    assert "결손" in result.stdout


def _run_cli(*args) -> subprocess.CompletedProcess:
    root = Path(__file__).resolve().parents[2]
    return subprocess.run(
        [sys.executable, "-m", "batch.recentchanges", *args],
        cwd=root, capture_output=True, text=True, encoding="utf-8",
        env={**_env(), "PYTHONIOENCODING": "utf-8", "PYTHONPATH": str(root)},
    )


def _env() -> dict:
    import os

    return dict(os.environ)
