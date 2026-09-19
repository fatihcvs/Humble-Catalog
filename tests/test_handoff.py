import sys

import pytest

from humble_catalog import handoff


def _snap(d, stamp, covers=False):
    d.mkdir(exist_ok=True)
    p = d / f"catalog-{stamp}.db"
    p.write_bytes(b"x" * 10)
    if covers:
        (d / f"covers-{stamp}.zip").write_bytes(b"z")
    return p


def test_argv_for_login_and_reset_is_the_bare_command():
    assert handoff.argv("login") == [
        sys.executable, "-m", "humble_catalog", "login"]
    assert handoff.argv("reset", {}) == [
        sys.executable, "-m", "humble_catalog", "reset"]


def test_argv_refuses_an_in_page_command():
    # harvest is the job runner's; the handoff table knows only three.
    with pytest.raises(ValueError, match="unknown command"):
        handoff.argv("harvest")


def test_argv_refuses_a_non_boolean_option(tmp_path):
    d = tmp_path / "backups"
    _snap(d, "20260101-120000")
    with pytest.raises(ValueError, match="must be true or false"):
        handoff.argv("restore", {"covers": "yes"},
                     snapshot="catalog-20260101-120000.db", backups_dir=d)


def test_restore_needs_a_snapshot(tmp_path):
    with pytest.raises(ValueError, match="snapshot"):
        handoff.argv("restore", {}, backups_dir=tmp_path)


def test_restore_takes_only_a_listed_snapshot(tmp_path):
    d = tmp_path / "backups"
    _snap(d, "20260101-120000")
    for bad in ("../catalog.db", "catalog-20991231-000000.db",
                str(d / "catalog-20260101-120000.db"), 7):
        with pytest.raises(ValueError, match="snapshot"):
            handoff.argv("restore", {}, snapshot=bad, backups_dir=d)


def test_restore_argv_names_the_listed_file_and_the_covers_flag(tmp_path):
    d = tmp_path / "backups"
    _snap(d, "20260101-120000", covers=True)
    line = handoff.argv("restore", {"covers": True},
                        snapshot="catalog-20260101-120000.db", backups_dir=d)
    assert line == [sys.executable, "-m", "humble_catalog", "restore",
                    str(d / "catalog-20260101-120000.db"), "--covers"]


def test_only_restore_takes_a_snapshot(tmp_path):
    d = tmp_path / "backups"
    _snap(d, "20260101-120000")
    with pytest.raises(ValueError, match="snapshot"):
        handoff.argv("reset", {}, snapshot="catalog-20260101-120000.db",
                     backups_dir=d)


def test_list_backups_is_newest_first_and_pairs_covers(tmp_path):
    d = tmp_path / "backups"
    _snap(d, "20260101-120000", covers=True)
    _snap(d, "20260301-090000")
    rows = handoff.list_backups(d)
    assert [r["name"] for r in rows] == [
        "catalog-20260301-090000.db", "catalog-20260101-120000.db"]
    assert [r["covers"] for r in rows] == [False, True]
    assert rows[0]["size"] == 10
    assert len(rows[0]["modified"]) == len("2026-03-01 09:00")


def test_list_backups_leaves_out_raw_copies_of_a_damaged_catalog(tmp_path):
    # restore's own safety copy of an unreadable catalog. Nobody means to
    # put a damaged file back from a picker.
    d = tmp_path / "backups"
    _snap(d, "20260101-120000")
    (d / "catalog-20260102-120000.unreadable.db").write_bytes(b"?")
    assert [r["name"] for r in handoff.list_backups(d)] == [
        "catalog-20260101-120000.db"]


def test_list_backups_of_a_missing_directory_is_empty(tmp_path):
    assert handoff.list_backups(tmp_path / "nope") == []
