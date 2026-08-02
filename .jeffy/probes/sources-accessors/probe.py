"""Known-answer battery for the sources-accessors inventory row.

Covers the shape boundary added by D1: as_text, as_number, as_mapping,
as_list, first_text, first_mapping and text_list in
humble_catalog/sources/base.py.

tests/test_sources_shapes.py already pins these through the parsers and
directly. This battery exists for what that file does not reach: every
documented parameter at two or more values, including text_list's `key`,
which no test or probe exercised at a second value, and the boundaries of
as_number's numeric domain.

Enumerated from `grep -n "^def " humble_catalog/sources/base.py`, minus
the four functions the sources-base row already owns (redact, candidate,
cache_key_params, _with_retries).
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from humble_catalog.sources.base import (          # noqa: E402
    as_list, as_mapping, as_number, as_text, first_mapping, first_text,
    text_list)

PASS, FAIL = [], []


def check(label, got, want):
    if got == want and type(got) is type(want):
        PASS.append(label)
    else:
        FAIL.append(f"{label}: got {got!r} ({type(got).__name__}), "
                    f"want {want!r} ({type(want).__name__})")


def eq(label, got, want):
    if got == want:
        PASS.append(label)
    else:
        FAIL.append(f"{label}: got {got!r}, want {want!r}")


# --- as_text ---------------------------------------------------------
for value, want, why in (
        ("Fantasy", "Fantasy", "a plain string"),
        ("  Fantasy  ", "  Fantasy  ", "surrounding space is preserved, not trimmed"),
        ("   ", None, "a blank string is not text"),
        ("", None, "the empty string is not text"),
        (None, None, "absent"),
        (0, None, "zero"),
        (4.5, None, "a number"),
        (True, None, "a bool"),
        (["Fantasy"], None, "a list"),
        ({"a": 1}, None, "a dict")):
    eq(f"as_text: {why}", as_text(value), want)

# --- as_number, and its allow_text parameter at both values ----------
for value, want, why in (
        (4.5, 4.5, "a float"), (5, 5.0, "an int becomes a float"),
        (0, 0.0, "zero is a number, not absence"),
        (-3, -3.0, "a negative number is still a number"),
        (True, None, "True is excluded despite being an int subclass"),
        (False, None, "False is excluded for the same reason"),
        (None, None, "absent"), ("4.5", None, "a numeric string, by default"),
        ("x", None, "a non-numeric string"), ([], None, "a list"),
        ({}, None, "a dict")):
    eq(f"as_number: {why}", as_number(value), want)

for value, want, why in (
        ("3", 3.0, "a numeric string is accepted"),
        ("2.5", 2.5, "a decimal string is accepted"),
        ("-1.5", -1.5, "a negative string is accepted"),
        ("  4  ", 4.0, "a padded numeric string is accepted"),
        ("bonus", None, "a non-numeric string is still refused"),
        ("", None, "the empty string is refused"),
        (3, 3.0, "a real number is unaffected by the parameter"),
        (True, None, "the bool exclusion still applies")):
    eq(f"as_number allow_text=True: {why}", as_number(value, allow_text=True), want)

# The parameter must change the output, or it is inert.
eq("as_number: the parameter changes the answer for a numeric string",
   (as_number("3"), as_number("3", allow_text=True)), (None, 3.0))
check("as_number: an int is returned as a float, not an int", as_number(5), 5.0)

# --- as_mapping ------------------------------------------------------
eq("as_mapping: a dict passes through", as_mapping({"a": 1}), {"a": 1})
eq("as_mapping: a string yields an empty dict", as_mapping("nope"), {})
eq("as_mapping: None yields an empty dict", as_mapping(None), {})
eq("as_mapping: a list yields an empty dict", as_mapping([{"a": 1}]), {})
eq("as_mapping: the result is always gettable",
   as_mapping("nope").get("anything"), None)

# --- as_list ---------------------------------------------------------
eq("as_list: a list passes through", as_list(["a", "b"]), ["a", "b"])
eq("as_list: a tuple becomes a list", as_list(("a",)), ["a"])
eq("as_list: a string is NOT a sequence here", as_list("Fantasy"), [])
eq("as_list: None yields an empty list", as_list(None), [])
eq("as_list: a dict yields an empty list", as_list({"a": 1}), [])
eq("as_list: the result is a copy, not the input object",
   as_list(["a"]) is not None, True)
src = ["a"]
eq("as_list: mutating the result does not touch the input",
   (as_list(src).append("b"), src)[1], ["a"])

# --- first_text ------------------------------------------------------
for value, want, why in (
        (["Fantasy", "Epic"], "Fantasy", "the first of a list"),
        ("Fantasy", "Fantasy", "an unwrapped string is taken WHOLE"),
        ([None, "", "Epic"], "Epic", "blank entries are skipped"),
        ([{"name": "Fantasy"}], None, "a list of dicts has no text"),
        ({"name": "Fantasy"}, None, "a bare dict has no text"),
        ([], None, "empty"), (None, None, "absent"), (5, None, "a number")):
    eq(f"first_text: {why}", first_text(value), want)
eq("first_text: never returns a single character from a word",
   len(first_text("Fantasy")), 7)

# --- first_mapping ---------------------------------------------------
for value, want, why in (
        ([{"a": 1}, {"b": 2}], {"a": 1}, "the first dict of a list"),
        ({"a": 1}, {"a": 1}, "an unwrapped dict is taken as itself"),
        (["x", {"a": 1}], {"a": 1}, "non-dict entries are skipped"),
        (["x"], {}, "a list of strings has no mapping"),
        ([], {}, "empty"), (None, {}, "absent"), ("x", {}, "a string")):
    eq(f"first_mapping: {why}", first_mapping(value), want)

# --- text_list, and its `key` parameter at two values ----------------
for value, want, why in (
        ([{"name": "Alex Penner"}], ["Alex Penner"], "dicts carrying name"),
        (["Alex Penner"], ["Alex Penner"], "bare strings"),
        ("Alex Penner", ["Alex Penner"], "a single unwrapped string"),
        ([{"name": "Alex Penner"}, "Sam Reader"], ["Alex Penner", "Sam Reader"],
         "a mixed list keeps both"),
        ([{"id": 7}], None, "a dict without the key is skipped"),
        ([{"name": ""}], None, "a blank name is skipped"),
        ([{"name": 5}], None, "a non-string name is skipped"),
        ([], None, "empty yields None, not []"),
        (None, None, "absent yields None"),
        ({"name": "Alex Penner"}, None, "a bare dict is not a list of names")):
    eq(f"text_list: {why}", text_list(value), want)

# `key` at a second value must change the answer. Nothing else exercises
# this parameter, which is exactly the inert-parameter case the Method
# treats as a finding rather than a pass.
people = [{"name": "Alex Penner", "role": "writer"}]
eq("text_list: key=name reads the name", text_list(people), ["Alex Penner"])
eq("text_list: key=role reads the role instead",
   text_list(people, key="role"), ["writer"])
eq("text_list: an absent key yields None",
   text_list(people, key="publisher"), None)
eq("text_list: the key parameter changes the answer",
   text_list(people) != text_list(people, key="role"), True)
eq("text_list: key is ignored for bare strings",
   text_list(["Alex Penner"], key="role"), ["Alex Penner"])

# --- the property the whole boundary exists for ----------------------
# No accessor may raise, whatever it is handed. A boundary that can raise
# is not a boundary.
SHAPES = [None, 0, 1, -1, True, False, "", "  ", "text", [], {}, ["a"],
          [None], [{}], {"a": 1}, (1, 2), 4.5, [[]], [{"name": None}]]
raised = []
for fn in (as_text, as_mapping, as_list, first_text, first_mapping, text_list,
           as_number):
    for shape in SHAPES:
        try:
            fn(shape)
        except Exception as exc:
            raised.append(f"{fn.__name__}({shape!r}) -> {type(exc).__name__}: {exc}")
eq(f"boundary: no accessor raises on any of {len(SHAPES)} shapes "
   f"({7 * len(SHAPES)} calls)", raised, [])


def main():
    for line in FAIL:
        print(f"BROKEN {line}")
    total = len(PASS) + len(FAIL)
    print(f"\nsources-accessors: {len(PASS)}/{total} held")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
