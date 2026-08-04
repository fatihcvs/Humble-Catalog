import sys
import time
import pytest
from humble_catalog import db, jobs


def test_argv_builds_from_the_whitelist():
    assert jobs.argv("harvest", {"ignore_quota": True}) == [
        sys.executable, "-m", "humble_catalog", "harvest", "--ignore-quota"]


def test_argv_always_passes_no_login_to_extract():
    # Non-negotiable: without it a background extract can block forever on
    # a browser window the page cannot show.
    assert "--no-login" in jobs.argv("extract", {})


def test_argv_renames_underscored_commands():
    assert jobs.argv("import_games", {})[3] == "import-games"


def test_argv_refuses_an_unknown_command():
    with pytest.raises(ValueError, match="unknown command"):
        jobs.argv("rm", {})


def test_argv_refuses_an_option_the_command_does_not_have():
    with pytest.raises(ValueError, match="does not accept"):
        jobs.argv("reparse", {"ignore_quota": True})


def test_argv_refuses_a_non_boolean_option():
    # The guard that keeps request strings out of argv entirely.
    with pytest.raises(ValueError, match="must be true or false"):
        jobs.argv("harvest", {"ignore_quota": "; rm -rf /"})


def test_argv_omits_options_set_to_false():
    assert jobs.argv("harvest", {"ignore_quota": False}) == [
        sys.executable, "-m", "humble_catalog", "harvest"]


def _fake_runner(monkeypatch, tmp_path, script):
    """A JobRunner whose 'reparse' command is `script` instead of the CLI.

    Spawning the real CLI in a unit test would be slow and would touch a
    real catalog; only the plumbing is under test here.
    """
    monkeypatch.chdir(tmp_path)
    db.connect("catalog.db").close()
    runner = jobs.JobRunner(db_path="catalog.db")
    monkeypatch.setattr(jobs, "argv",
                        lambda command, options=None: [sys.executable, "-c",
                                                       script])
    return runner


def test_start_captures_the_child_s_output(monkeypatch, tmp_path):
    runner = _fake_runner(monkeypatch, tmp_path,
                          "print('Bundle 1/2: The Hollow Crypt')")
    runner.start("reparse")
    assert runner.wait(timeout=30) == 0
    assert "Bundle 1/2: The Hollow Crypt" in runner.state()["log"]


def test_state_reports_the_running_job_then_the_finished_one(monkeypatch,
                                                             tmp_path):
    runner = _fake_runner(monkeypatch, tmp_path, "import time; time.sleep(1)")
    runner.start("reparse")
    assert runner.state()["running"]["command"] == "reparse"
    runner.wait(timeout=30)
    assert runner.state()["running"] is None
    assert runner.state()["last"] == {
        "command": "reparse", "state": "done", "exit_code": 0,
        "finished_at": runner.state()["last"]["finished_at"]}


def test_a_failing_child_is_reported_as_failed(monkeypatch, tmp_path):
    runner = _fake_runner(monkeypatch, tmp_path, "raise SystemExit(3)")
    runner.start("reparse")
    runner.wait(timeout=30)
    assert runner.state()["last"]["state"] == "failed"
    assert runner.state()["last"]["exit_code"] == 3


def test_a_second_start_while_one_runs_is_refused(monkeypatch, tmp_path):
    runner = _fake_runner(monkeypatch, tmp_path, "import time; time.sleep(2)")
    runner.start("reparse")
    with pytest.raises(jobs.Busy):
        runner.start("reparse")
    runner.wait(timeout=30)


def test_the_log_is_bounded(monkeypatch, tmp_path):
    runner = _fake_runner(
        monkeypatch, tmp_path,
        f"[print(i) for i in range({jobs.LOG_LINES + 50})]")
    runner.start("reparse")
    runner.wait(timeout=60)
    assert len(runner.state()["log"]) == jobs.LOG_LINES


def test_cleanup_runs_after_the_child_exits(monkeypatch, tmp_path):
    runner = _fake_runner(monkeypatch, tmp_path, "print('done')")
    called = []
    runner.start("reparse", cleanup=lambda: called.append(True))
    runner.wait(timeout=30)
    assert called == [True]


def test_cancel_stops_a_running_job(monkeypatch, tmp_path):
    # The child ignores nothing and simply sleeps; the interrupt ends it.
    runner = _fake_runner(monkeypatch, tmp_path,
                          "import time; time.sleep(60)")
    runner.start("reparse")
    time.sleep(0.5)          # let the interpreter reach the sleep
    assert runner.cancel() is True
    runner.wait(timeout=30)
    assert runner.state()["running"] is None
    assert runner.state()["last"]["state"] == "cancelled"


def test_cancel_with_nothing_running_is_false(monkeypatch, tmp_path):
    runner = _fake_runner(monkeypatch, tmp_path, "print('x')")
    assert runner.cancel() is False
