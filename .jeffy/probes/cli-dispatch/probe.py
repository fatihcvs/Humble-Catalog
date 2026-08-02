"""Known-answer battery for the cli-dispatch inventory row.

Covers `humble_catalog/__main__.py`: `missing_dependencies`,
`check_dependencies`, the argparse wiring, and the explicit `parser.error`
validation paths.

The envelope classes CLI arguments user-error: a wrong value earns a clear
failure message, and that message IS the contract here. So the cases
assert the exit status and the text the owner is shown, not just that
something was refused - a command that exits 2 with an unhelpful message
has met the letter of the contract and none of its point.

Every command is invoked through `python -m humble_catalog` in a real
subprocess, because argparse's behaviour on `--help`, on an unknown
command and on a missing argument is what is being pinned, and importing
main() would exercise a different path than the one the owner meets.

The commands that would touch the network or the catalog are only ever
invoked with arguments that fail validation FIRST, so nothing here runs a
harvest or writes a database.
"""
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from humble_catalog import __main__ as cli  # noqa: E402

PY = str(ROOT / ".venv" / "Scripts" / "python.exe")
PASS, FAIL = [], []


def check(label, got, want):
    (PASS if got == want else FAIL).append(label)
    if got != want:
        print(f"  FAIL {label}\n       got  {got!r}\n       want {want!r}")


def run(*args):
    """Invoke the CLI as the owner does. Returns (code, stdout, stderr)."""
    proc = subprocess.run([PY, "-m", "humble_catalog", *args],
                          cwd=str(ROOT), capture_output=True, text=True,
                          encoding="utf-8", timeout=120)
    return proc.returncode, proc.stdout or "", proc.stderr or ""


# ------------------------------------------------------- dependency check

def case_a_healthy_interpreter_reports_no_missing_dependencies():
    # This interpreter is the project's own venv, so the list must be
    # empty; a non-empty answer here would mean the venv is broken.
    check("nothing is missing in the project venv",
          cli.missing_dependencies(), [])


def case_check_dependencies_is_silent_when_nothing_is_missing():
    check("a healthy interpreter passes through",
          cli.check_dependencies(), None)


def case_missing_dependencies_reads_the_declared_map():
    # The function answers from RUNTIME_DEPENDENCIES rather than from a
    # hardcoded list, so the map is asserted to be non-empty and to name
    # module/package pairs.
    check("the dependency map is populated",
          len(cli.RUNTIME_DEPENDENCIES) > 0, True)
    check("and maps module names to package names",
          all(isinstance(m, str) and isinstance(p, str)
              for m, p in cli.RUNTIME_DEPENDENCIES.items()), True)


def case_a_missing_dependency_names_the_interpreter():
    """The whole point of the check, driven by pretending one is absent.

    A forgotten activation does not announce itself on Windows: bare
    `python` resolves to the Store stub, imports humble_catalog out of the
    source tree, and fails four imports deep. Naming the interpreter is
    what makes the real cause visible, so the message is asserted to
    carry it.
    """
    original = dict(cli.RUNTIME_DEPENDENCIES)
    cli.RUNTIME_DEPENDENCIES["no_such_module_xyz"] = "no-such-package"
    try:
        check("the absent module is reported",
              "no-such-package" in cli.missing_dependencies(), True)
        try:
            cli.check_dependencies()
            FAIL.append("check_dependencies exits")
            print("  FAIL check_dependencies exits: nothing raised")
        except SystemExit as exc:
            check("it exits non-zero", exc.code, 1)
    finally:
        cli.RUNTIME_DEPENDENCIES.clear()
        cli.RUNTIME_DEPENDENCIES.update(original)
    check("and the map is restored", cli.missing_dependencies(), [])


# ------------------------------------------------------------ the parser

def case_help_lists_every_command():
    code, out, _err = run("--help")
    check("--help exits cleanly", code, 0)
    for command in ["extract", "reparse", "harvest", "enrich", "reset",
                    "check", "stats", "serve", "export", "backup", "restore",
                    "bundle", "keys"]:
        check(f"{command} is offered", command in out, True)


def case_no_command_is_refused():
    code, _out, _err = run()
    check("running with no subcommand is an error", code != 0, True)


def case_an_unknown_command_is_refused():
    code, _out, err = run("nosuchcommand")
    check("an unknown subcommand exits 2", code, 2)
    check("and argparse says it is invalid",
          "invalid choice" in err, True)


def case_each_command_has_help_of_its_own():
    for command in ["harvest", "enrich", "export", "keys", "bundle"]:
        code, out, _err = run(command, "--help")
        check(f"{command} --help exits cleanly", code, 0)
        check(f"{command} --help says something", len(out) > 20, True)


# ------------------------------------------------- explicit parser.error

def case_override_edited_cannot_be_combined_with_reset():
    # The refusal exists because --reset would wipe the very hand edits
    # --override-edited exists to carry through, so the message is
    # asserted to say that rather than merely refusing.
    for flag in ["--reset", "--reset-reviews"]:
        code, _out, err = run("enrich", "--override-edited", flag)
        check(f"enrich --override-edited {flag} exits 2", code, 2)
        check(f"and explains why for {flag}",
              "cannot be combined" in err, True)
        check(f"naming the hand edits for {flag}",
              "hand edits" in err, True)


def case_an_export_path_with_no_known_suffix_is_refused():
    # The suffix is the only format signal: guessing for an unknown one
    # would write a mislabelled file.
    for path in ["catalog.txt", "catalog", "catalog.xls"]:
        code, _out, err = run("export", path)
        check(f"export {path} exits 2", code, 2)
        check(f"and names the accepted suffixes for {path}",
              ".csv" in err and ".xlsx" in err, True)


def case_an_unknown_export_column_is_fatal():
    # Deliberately stricter than the web route, which drops unknown names:
    # a typo on a command line is a mistake being made right now.
    code, _out, err = run("export", "out.csv", "--columns", "title,nosuchcol")
    check("an unknown column exits 2", code, 2)
    check("and the message names the offending column",
          "nosuchcol" in err, True)


def case_an_empty_column_list_is_refused():
    code, _out, err = run("export", "out.csv", "--columns", " , ")
    check("a column list that reduces to nothing exits 2", code, 2)
    check("and says at least one name is needed",
          "at least one column" in err, True)


def case_the_valid_column_names_used_above_are_real():
    """The control for the two refusals above, checked IN-PROCESS.

    It deliberately does not invoke `export` with a valid path: that
    command's `path` is optional and defaults to catalog.csv, and a
    successful run writes a real export of the owner's catalog into the
    repo. This battery wrote catalog.csv and out.csv exactly once, before
    that was understood; both were deleted and the cases rewritten. A CLI
    battery must never invoke a subcommand whose success has a side
    effect on the owner's data.
    """
    from humble_catalog import export
    for name in ["title", "type"]:
        check(f"{name} is a real export column", name in export.COLUMNS, True)
    check("and the name used in the refusal case is not",
          "nosuchcol" in export.COLUMNS, False)


def case_export_documents_its_default_path():
    # Asserted from --help rather than by running it, for the reason
    # above: `export` with no argument SUCCEEDS and writes a file.
    _code, out, _err = run("export", "--help")
    check("the default destination is documented",
          "catalog.csv" in out, True)


def case_a_command_needing_a_path_refuses_without_one():
    # `export` is deliberately absent: its path is optional and
    # running it with none WRITES a real export.
    for command in ["restore", "bundle"]:
        code, _out, err = run(command)
        check(f"{command} with no argument exits 2", code, 2)
        check(f"and argparse says what is missing for {command}",
              "required" in err or "arguments" in err, True)



def case_this_battery_wrote_no_export_into_the_repo():
    """A standing guard, not a behaviour check.

    An earlier version of this file invoked `export` with a valid path and
    with none at all, and both wrote a real export of the catalog into the
    repo root - untracked, where the loop's `git add -A` checkpoint would
    have swept them in. The files are named here so the guard fails loudly
    if any case ever writes one again.
    """
    for name in ["catalog.csv", "catalog.xlsx", "out.csv", "out.xlsx"]:
        check(f"no {name} was left in the repo root",
              (ROOT / name).exists(), False)


CASES = [v for k, v in sorted(globals().items()) if k.startswith("case_")]

if __name__ == "__main__":
    for fn in CASES:
        try:
            fn()
        except Exception as exc:                            # noqa: BLE001
            FAIL.append(fn.__name__)
            print(f"  FAIL {fn.__name__} raised: "
                  f"{type(exc).__name__}: {exc}")
    total = len(PASS) + len(FAIL)
    print(f"cli-dispatch: {len(PASS)}/{total}")
    sys.exit(1 if FAIL else 0)
