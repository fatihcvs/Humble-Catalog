import importlib.util
import subprocess
from pathlib import Path

import pytest

from humble_catalog import lan

ROOT = Path(__file__).resolve().parents[1]


def test_the_token_is_created_once_and_then_reused(tmp_path):
    first = lan.load_or_create_token(tmp_path / "lan")
    assert len(first) >= 43                       # 32 random bytes, base64url
    assert lan.load_or_create_token(tmp_path / "lan") == first


def test_rotating_the_token_replaces_it(tmp_path):
    old = lan.load_or_create_token(tmp_path / "lan")
    new = lan.rotate_token(tmp_path / "lan")
    assert new != old
    assert lan.load_or_create_token(tmp_path / "lan") == new


def test_an_unreadable_token_is_an_error_not_a_new_token(tmp_path):
    # A silently regenerated token would unpair every phone with no
    # explanation. Refusing names the file instead.
    d = tmp_path / "lan"
    d.mkdir()
    (d / "token").write_bytes(b"\xff\xfe\x00")
    with pytest.raises(lan.LanStateError, match="token"):
        lan.load_or_create_token(d)


def test_the_lan_folder_sits_beside_the_catalog(tmp_path):
    assert lan.lan_dir_for(tmp_path / "catalog.db") == (tmp_path / "lan").resolve()


def test_git_ignores_the_lan_folder():
    out = subprocess.run(["git", "-C", str(ROOT), "check-ignore", "lan/token"],
                         capture_output=True, text=True)
    assert out.returncode == 0, "lan/ must be gitignored"


def test_the_data_check_refuses_the_lan_folder():
    spec = importlib.util.spec_from_file_location(
        "check_no_data_tracked", ROOT / "scripts" / "check_no_data_tracked.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.offenders(["lan/token", "lan/ca.key", "README.md"]) == [
        "lan/ca.key", "lan/token"]
