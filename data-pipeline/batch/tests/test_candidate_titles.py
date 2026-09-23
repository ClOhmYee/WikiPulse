"""후보 제목 추출 회귀 (WP-137)."""

from datetime import date
from pathlib import Path

from batch.candidate_titles import candidates_by_hour, main, write_hours


def ev(title, ts, *, is_bot=False, wiki="enwiki"):
    return {"wiki": wiki, "title": title, "event_ts": ts, "is_bot": is_bot}


def test_시간별로_집합이_갈린다():
    by_hour, read, bots = candidates_by_hour([
        ev("Hurricane Milton", "2026-07-17T04:12:00"),
        ev("Iran", "2026-07-17T04:59:59"),
        ev("Iran", "2026-07-17T05:00:00"),
    ])
    assert read == 3 and bots == 0
    assert by_hour["2026-07-17T04:00:00"] == {"Hurricane Milton", "Iran"}
    assert by_hour["2026-07-17T05:00:00"] == {"Iran"}


def test_봇_편집은_후보가_아니다():
    by_hour, read, bots = candidates_by_hour([
        ev("Cydebot page", "2026-07-17T04:00:00", is_bot=True),
        ev("Iran", "2026-07-17T04:00:00"),
    ])
    assert (read, bots) == (2, 1)
    assert by_hour["2026-07-17T04:00:00"] == {"Iran"}


def test_밑줄_제목이_canonical_공백형으로_나온다():
    """`--titles` 는 공백형만 맞는다 — 밑줄이 새면 조회수가 통째로 0이 된다."""
    by_hour, _, _ = candidates_by_hour([
        ev("Hurricane_Milton", "2026-07-17T04:00:00"),
        ev("Hurricane__Milton", "2026-07-17T04:00:00"),
    ])
    assert by_hour["2026-07-17T04:00:00"] == {"Hurricane Milton"}


def test_구간_밖은_제외된다():
    by_hour, _, _ = candidates_by_hour(
        [ev("A", "2026-07-16T23:00:00"), ev("B", "2026-07-17T00:00:00"),
         ev("C", "2026-08-01T00:00:00")],
        since=date(2026, 7, 17), until=date(2026, 7, 31))
    assert set(by_hour) == {"2026-07-17T00:00:00"}


def test_출력이_pageview_ingest_가_읽는_형식이다(tmp_path: Path):
    write_hours({"2026-07-17T04:00:00": {"Iran", "Hurricane Milton"}},
                tmp_path, "enwiki")
    f = tmp_path / "enwiki" / "2026-07-17" / "04.txt"
    assert f.read_text(encoding="utf-8").splitlines() == [
        "Hurricane Milton", "Iran"]

    from batch.pageview_hourly_ingest import load_titles
    assert load_titles(f) == frozenset({"Iran", "Hurricane Milton"})


def test_dry_run_은_파일을_안_만든다(tmp_path: Path, capsys, monkeypatch):
    import batch.candidate_titles as mod
    monkeypatch.setattr(mod, "read_jsonl_shards",
                        lambda *_a, **_k: iter([ev("Iran", "2026-07-17T04:00:00")]))
    edits = tmp_path / "edits"; edits.mkdir()
    out = tmp_path / "out"
    assert mod.main(["--edits", str(edits), "--out", str(out), "--dry-run"]) == 0
    assert not out.exists()
    assert "고유 문서 1" in capsys.readouterr().out
