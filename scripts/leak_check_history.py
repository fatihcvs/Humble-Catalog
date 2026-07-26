"""Privacy check against git history (see CLAUDE.md).

`leak_check.py` scans the working tree. This runs the same terms against
every object in the repository and every commit message — which is what
a push actually publishes. A working tree scrubbed clean says nothing
about the commits underneath it.

Run before the first push to a public remote, and after any history
rewrite. It is slower than the working-tree check and is deliberately
not part of `verify`; the terms are read at runtime, so this file holds
no personal data itself.

Run: .venv/Scripts/python scripts/leak_check_history.py
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


def object_paths():
    """sha -> every path that object has ever been committed under.

    Only for reporting: an object reachable under no path (left behind by
    a rewrite) still gets scanned.
    """
    paths = {}
    for line in git("rev-list", "--all", "--objects").decode("utf-8", "ignore").splitlines():
        parts = line.split(" ", 1)
        if len(parts) == 2 and parts[1].strip():
            paths.setdefault(parts[0], set()).add(parts[1].strip())
    return paths


def scan_commit_messages(match, hits):
    """Commit messages travel with a push and are not part of any tree,
    so the blob scan below cannot see them."""
    out = git("log", "--all", "--format=%H%x00%B%x01").decode("utf-8", "ignore")
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
    """--batch-all-objects covers unreachable objects too, which is the
    point: a botched rewrite can leave the old blobs dangling in the
    object store, and a plain `git push` of a branch will not carry them
    but a mirror push or a GC-less clone can.

    Every record's payload must be consumed even when skipped. Trees and
    commits come down the same pipe as blobs, and leaving their bytes
    unread desynchronises the stream — the next readline then blocks
    forever on what it thinks is a header.
    """
    proc = subprocess.Popen(
        ["git", "-C", str(ROOT), "cat-file", "--batch-all-objects", "--batch", "--buffer"],
        stdout=subprocess.PIPE)
    count = 0
    while True:
        line = proc.stdout.readline()
        if not line:
            break
        header = line.decode("utf-8", "ignore").split()
        if len(header) < 3:
            continue
        sha, objtype, size = header[0], header[1], int(header[2])
        data = proc.stdout.read(size)
        proc.stdout.read(1)                     # trailing newline
        if objtype != "blob":
            continue
        known = sorted(paths.get(sha, []))
        if known and all(p.lower().endswith(SKIP_EXT) for p in known):
            continue
        count += 1
        where = known[0] if known else "unreachable, no path"
        for term in match(data.decode("utf-8", "ignore").lower()):
            hits.setdefault(term, set()).add(f"blob {sha[:10]} ({where})")
    proc.wait()
    return count


def main():
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
    ncommits = scan_commit_messages(match, hits)
    nblobs = scan_blobs(match, hits, object_paths())

    print(f"checked {len(terms)} terms against {nblobs} blobs "
          f"and {ncommits} commit messages")
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
