"""Privacy check against git history (see CLAUDE.md).

`leak_check.py` scans the working tree. This runs the same terms against
everything a push of one ref would publish: every blob reachable from it
and every commit message behind it. A working tree scrubbed clean says
nothing about the commits underneath it.

Scoped to a single ref by design. This repository deliberately keeps its
pre-publication history in a local-only branch, so "every object in the
store" is the wrong question — it would report private data that is
never going anywhere and turn this into a check that always fails.
Anything not reachable from the scanned ref is listed as unscanned
rather than ignored silently.

The corollary is a rule this script cannot enforce: push one ref at a
time. `git push --all`, `--mirror`, or pushing the private branch by
name would publish exactly what the scoping assumes stays home.

Run before the first push to a public remote, and after any history
rewrite. Slower than the working-tree check and deliberately not part of
`verify`; the terms are read at runtime, so this file holds no personal
data itself.

Run: .venv/Scripts/python scripts/leak_check_history.py [ref]
     (ref defaults to HEAD)
"""
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from leak_check import NOTHING_TO_CHECK, ROOT, build_terms  # noqa: E402

# Binary or data blobs: never meaningful to grep, and a committed xlsx
# would trip on every term it contains rather than telling us anything
# the filename has not already said.
SKIP_EXT = (".png", ".svg", ".ico", ".jpg", ".xlsx", ".db", ".zip")


def git(*args):
    return subprocess.run(["git", "-C", str(ROOT), *args],
                          capture_output=True, check=True).stdout


def reachable_objects(ref):
    """sha -> a path the object appears under, for everything `ref` reaches.

    One path per object is all this needs: the path is for reporting, and
    the scan reads the object's *content*. (Contrast
    check_no_data_tracked.py, which asks which paths exist and therefore
    cannot use this — git stores one blob per unique content, so
    identical files collapse to a single entry here.)
    """
    paths = {}
    for line in git("rev-list", ref, "--objects").decode("utf-8", "ignore").splitlines():
        sha, _, path = line.partition(" ")
        if sha:
            paths[sha] = path.strip()
    return paths


def unscanned_refs(ref):
    """Local refs holding commits the scanned ref does not reach.

    Reported so that history kept back on purpose stays visible: it is
    fine that it exists, and dangerous only if it is pushed.
    """
    out = git("for-each-ref", "--format=%(refname:short)", "refs/heads").decode(
        "utf-8", "ignore").split()
    target = git("rev-parse", ref).decode().strip()
    extra = []
    for name in out:
        if git("rev-parse", name).decode().strip() == target:
            continue
        if git("rev-list", "--count", f"{name}", f"^{ref}").decode().strip() != "0":
            extra.append(name)
    return extra


def scan_commit_messages(ref, match, hits):
    """Commit messages travel with a push and are not part of any tree,
    so the blob scan below cannot see them."""
    out = git("log", ref, "--format=%H%x00%B%x01").decode("utf-8", "ignore")
    count = 0
    for record in out.split("\x01"):
        if "\x00" not in record:
            continue
        sha, body = record.split("\x00", 1)
        count += 1
        for term in match(body.lower()):
            hits.setdefault(term, set()).add(f"commit-message {sha.strip()[:10]}")
    return count


def scan_blobs(match, hits, paths):
    """Read each reachable object and scan the blobs among them.

    Written one sha at a time rather than dumping the whole list into the
    pipe: cat-file's output would fill the OS buffer while we were still
    writing, and both ends would block. Every record's payload must be
    consumed even when skipped -- trees and commits come down the same
    pipe, and leaving their bytes unread desynchronises the stream, after
    which the next readline waits forever on what it thinks is a header.
    """
    proc = subprocess.Popen(
        ["git", "-C", str(ROOT), "cat-file", "--batch"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    count = 0
    for sha, path in paths.items():
        proc.stdin.write((sha + "\n").encode())
        proc.stdin.flush()
        header = proc.stdout.readline().decode("utf-8", "ignore").split()
        if len(header) < 3:
            continue
        objtype, size = header[1], int(header[2])
        data = proc.stdout.read(size)
        proc.stdout.read(1)                     # trailing newline
        if objtype != "blob":
            continue
        if path and path.lower().endswith(SKIP_EXT):
            continue
        count += 1
        where = path or "no path"
        for term in match(data.decode("utf-8", "ignore").lower()):
            hits.setdefault(term, set()).add(f"blob {sha[:10]} ({where})")
    proc.stdin.close()
    proc.wait()
    return count


def main():
    ref = sys.argv[1] if len(sys.argv) > 1 else "HEAD"
    terms = build_terms()
    if not terms:
        print(NOTHING_TO_CHECK)
        return 0

    # Plain substring tests, as in leak_check. A single regex alternation
    # over every term looks like the faster option but is far slower: re
    # backtracks through each alternative at every position, while `in`
    # uses CPython's optimised substring search.
    lowered = [(t.lower(), t) for t in terms]

    def match(text):
        return {original for low, original in lowered if low in text}

    hits = {}
    ncommits = scan_commit_messages(ref, match, hits)
    nblobs = scan_blobs(match, hits, reachable_objects(ref))

    print(f"checked {len(terms)} terms against {nblobs} blobs "
          f"and {ncommits} commit messages reachable from {ref}")
    held_back = unscanned_refs(ref)
    if held_back:
        print(f"not scanned: {', '.join(held_back)} - local branches "
              f"{ref} does not reach.\nThat is deliberate, but it means "
              "only this ref is safe to push. Never\n`git push --all` or "
              "`--mirror` from here.")
    if hits:
        print(f"LEAK: {len(hits)} term(s) from the private library found in history:")
        for term in sorted(hits):
            where = sorted(hits[term])
            print(f"  {term!r}: {len(where)} location(s)")
            for w in where[:5]:
                print(f"      {w}")
            if len(where) > 5:
                print(f"      ... and {len(where) - 5} more")
        print("A hit here cannot be fixed by editing a file: the term is in "
              "history.\nCheck the context first — most hits are ordinary "
              "prose matching as a\nsubstring, which belongs in ALLOWED in "
              "leak_check.py. A genuine leak\nneeds the history rewritten "
              "(git filter-repo) before any public push.")
        return 1
    print("history clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
