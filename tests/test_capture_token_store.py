import json
import os
import stat

import pytest

from src.capture import TokenStore


def test_load_returns_none_when_file_missing(tmp_path):
    store = TokenStore(path=str(tmp_path / "portal.json"))
    assert store.load() is None


def test_save_then_load_round_trips_token(tmp_path):
    store = TokenStore(path=str(tmp_path / "nested" / "portal.json"))
    store.save("abc-123")
    assert store.load() == "abc-123"


def test_save_creates_parent_dir_with_restricted_perms(tmp_path):
    directory = tmp_path / "screen-monitor"
    store = TokenStore(path=str(directory / "portal.json"))
    store.save("t")
    mode = stat.S_IMODE(os.stat(directory).st_mode)
    assert mode == 0o700


def test_save_writes_atomically_via_temp_file(tmp_path, monkeypatch):
    """A crash mid-write must not leave the store corrupted."""
    store = TokenStore(path=str(tmp_path / "portal.json"))
    store.save("first")

    original_replace = os.replace
    call_sites: list[tuple[str, str]] = []

    def tracking_replace(src, dst):
        call_sites.append((src, dst))
        return original_replace(src, dst)

    monkeypatch.setattr(os, "replace", tracking_replace)
    store.save("second")
    assert call_sites and call_sites[0][0].endswith(".tmp")
    assert store.load() == "second"


def test_load_tolerates_corrupt_json(tmp_path):
    path = tmp_path / "portal.json"
    path.write_text("{not json", encoding="utf-8")
    store = TokenStore(path=str(path))
    assert store.load() is None


def test_load_returns_none_for_missing_key(tmp_path):
    path = tmp_path / "portal.json"
    path.write_text(json.dumps({"other": "x"}), encoding="utf-8")
    store = TokenStore(path=str(path))
    assert store.load() is None


def test_clear_removes_file(tmp_path):
    store = TokenStore(path=str(tmp_path / "portal.json"))
    store.save("x")
    store.clear()
    assert store.load() is None


def test_clear_is_idempotent(tmp_path):
    store = TokenStore(path=str(tmp_path / "portal.json"))
    store.clear()  # no file yet — must not raise


def test_default_path_honours_xdg_data_home(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    store = TokenStore()
    assert store.path == str(tmp_path / "screen-monitor" / "portal.json")


def test_default_path_falls_back_to_local_share(monkeypatch):
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    store = TokenStore()
    assert store.path == os.path.expanduser("~/.local/share/screen-monitor/portal.json")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
