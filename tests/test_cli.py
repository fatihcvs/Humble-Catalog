import sys
from pathlib import Path
import pytest
from unittest.mock import patch
from humble_catalog import __main__ as cli
from humble_catalog import db

def test_harvest_command_dispatches(monkeypatch):
    called = {}
    monkeypatch.setattr(sys, "argv", ["humble_catalog", "harvest"])
    with patch("humble_catalog.harvest.run",
               side_effect=lambda *a, **k: called.setdefault("run", True)):
        cli.main()
    assert called.get("run")

def test_enrich_credits_flag_dispatches(monkeypatch):
    called = {}
    monkeypatch.setattr(sys, "argv", ["humble_catalog", "enrich", "--credits"])
    with patch("humble_catalog.enrich.credits",
               side_effect=lambda *a, **k: called.setdefault("credits", True)), \
         patch("humble_catalog.enrich.run",
               side_effect=lambda *a, **k: called.setdefault("run", True)):
        cli.main()
    assert called.get("credits") and "run" not in called

def test_enrich_bare_runs_match(monkeypatch):
    called = {}
    monkeypatch.setattr(sys, "argv", ["humble_catalog", "enrich"])
    with patch("humble_catalog.enrich.run",
               side_effect=lambda *a, **k: called.setdefault("run", True)):
        cli.main()
    assert called.get("run")

def test_enrich_override_edited_dispatches(monkeypatch):
    called = {}
    monkeypatch.setattr(sys, "argv",
                        ["humble_catalog", "enrich", "--override-edited"])
    with patch("humble_catalog.enrich.override_edited",
               side_effect=lambda *a, **k: called.setdefault("override", True)), \
         patch("humble_catalog.enrich.run",
               side_effect=lambda *a, **k: called.setdefault("run", True)):
        cli.main()
    assert called.get("override") and "run" not in called

def test_override_edited_cannot_be_combined_with_reset(monkeypatch):
    # --reset would wipe the very hand edits the override exists to carry
    # through, so the combination can only ever be a mistake
    monkeypatch.setattr(sys, "argv",
                        ["humble_catalog", "enrich", "--override-edited", "--reset"])
    with patch("humble_catalog.enrich.reset") as reset, \
         patch("humble_catalog.enrich.override_edited") as override:
        with pytest.raises(SystemExit):
            cli.main()
    assert not reset.called and not override.called

def test_stats_command_dispatches(monkeypatch):
    called = {}
    monkeypatch.setattr(sys, "argv", ["humble_catalog", "stats"])
    with patch("humble_catalog.stats.run",
               side_effect=lambda *a, **k: called.setdefault("run", True)), \
         patch("humble_catalog.db.connect"):
        cli.main()
    assert called.get("run")

def test_gaps_subcommand_is_gone(monkeypatch):
    # renamed rather than aliased: it shipped the same day and has one user
    monkeypatch.setattr(sys, "argv", ["humble_catalog", "gaps"])
    with pytest.raises(SystemExit):
        cli.main()

def test_backup_command_writes_a_snapshot(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    db.connect("catalog.db").close()
    monkeypatch.setattr(sys, "argv", ["humble_catalog", "backup"])
    cli.main()
    assert len(list(Path("backups").glob("catalog-*.db"))) == 1

def test_backup_command_takes_a_destination_and_covers_flag(monkeypatch):
    called = {}
    monkeypatch.setattr(sys, "argv",
                        ["humble_catalog", "backup", "D:/snap", "--covers"])
    with patch("humble_catalog.backup.run",
               side_effect=lambda *a, **k: called.setdefault("kw", k)):
        cli.main()
    assert called["kw"]["dest"] == "D:/snap"
    assert called["kw"]["with_covers"] is True

def test_restore_command_dispatches(monkeypatch):
    called = {}
    monkeypatch.setattr(sys, "argv", ["humble_catalog", "restore",
                                      "backups/catalog-20260725-143012.db",
                                      "--covers"])
    with patch("humble_catalog.backup.restore",
               side_effect=lambda *a, **k: called.setdefault("call", (a, k))):
        cli.main()
    args, kwargs = called["call"]
    assert args[0] == "backups/catalog-20260725-143012.db"
    assert kwargs["with_covers"] is True
