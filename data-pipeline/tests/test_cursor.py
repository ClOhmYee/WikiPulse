import json

import pytest

from producer.config import Config
from producer.cursor import CursorStore


def test_missing_cursor_returns_none(tmp_path):
    assert CursorStore(tmp_path / "cursor.json").load() is None


def test_cursor_round_trip_uses_versioned_json(tmp_path):
    path = tmp_path / "cursor.json"
    store = CursorStore(path)
    store.save('[{"topic":"eqiad","offset":7}]')
    assert store.load() == '[{"topic":"eqiad","offset":7}]'
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "version": 1,
        "event_id": '[{"topic":"eqiad","offset":7}]',
    }


def test_invalid_cursor_fails_closed(tmp_path):
    path = tmp_path / "cursor.json"
    path.write_text('{"version":2,"event_id":"x"}', encoding="utf-8")
    with pytest.raises(ValueError, match="cursor"):
        CursorStore(path).load()


def test_disabled_cursor_is_a_noop():
    store = CursorStore(None)
    store.save("event-1")
    assert store.load() is None


def test_config_trims_cursor_file(monkeypatch):
    monkeypatch.setenv("CONTACT_EMAIL", "test@example.com")
    monkeypatch.setenv("SSE_CURSOR_FILE", "  state/cursor.json  ")

    assert Config.from_env().cursor_file == "state/cursor.json"


def test_config_disables_empty_cursor_file(monkeypatch):
    monkeypatch.setenv("CONTACT_EMAIL", "test@example.com")
    monkeypatch.setenv("SSE_CURSOR_FILE", "   ")

    assert Config.from_env().cursor_file is None
