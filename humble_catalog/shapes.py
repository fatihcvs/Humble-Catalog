"""Shape-safe accessors for third-party JSON.

The Operating envelope classes both the HumbleBundle order payloads and
the metadata API responses adversarial, and names "a merely changed
upstream shape" as the case that reaches the parsers. Reading a field
with plain indexing has two failure modes, and the quiet one is worse:
`categories[0]` on a string field returns its first CHARACTER, which
becomes a one-letter genre in the catalog with nothing logged, while a
dict field raises an opaque TypeError from deep inside a parser.

These are the single boundary the envelope's binding rule calls for.
They were introduced in `sources/base.py` for the metadata parsers and
moved here when the acquisition path needed them too; `sources.base`
re-exports every one, so its imports and the settled class that owns
them are unchanged.

Tolerating a shape is not always the right answer. `parse_order` fails
loudly on a missing REQUIRED field on purpose - see the note there and
the matching one in `keys.py` - and these accessors are used there only
to reach a field safely enough to raise a message that names it.
"""


def as_text(value):
    """`value` if it is a non-blank string, else None.

    A number is deliberately not text: coercing it would turn an upstream
    type change into a plausible-looking value instead of an absent one.
    Surrounding space is preserved, because trimming belongs to the
    caller that stores the value - `db.normalize_tags` does it - and an
    accessor that trimmed would quietly differ from the raw payload.
    """
    return value if isinstance(value, str) and value.strip() else None


def as_mapping(value):
    """`value` if it is a dict, else an empty dict, so `.get` is always safe."""
    return value if isinstance(value, dict) else {}


def as_list(value):
    """`value` if it is a list or tuple, else an empty list.

    A string is not a list here. Iterating one yields characters, which is
    how a changed field shape becomes a sequence of one-letter records.
    """
    return list(value) if isinstance(value, (list, tuple)) else []


def first_mapping(value):
    """The first dict in a list field, or the field itself when it arrived
    unwrapped as a single dict. Empty dict when neither."""
    if isinstance(value, dict):
        return value
    for item in as_list(value):
        if isinstance(item, dict):
            return item
    return {}


def first_text(value):
    """The first string in a list field, or the field itself when it
    arrived unwrapped as a bare string. None when neither.

    The unwrapped case is the one that matters: an upstream serving
    `"Fantasy"` where it used to serve `["Fantasy"]` must yield the whole
    word, never its first letter.
    """
    if isinstance(value, str):
        return as_text(value)
    for item in as_list(value):
        text = as_text(item)
        if text is not None:
            return text
    return None


def text_list(value, key="name"):
    """A list of names from a contributor field, or None when there are none.

    Accepts a list of strings, a list of dicts carrying `key`, or a single
    bare string; entries of any other shape, and dicts missing `key`, are
    skipped rather than raising. Returns None rather than [] so a caller
    can pass the result straight to `candidate`, whose absent value is None.
    """
    if isinstance(value, str):
        value = [value]
    out = []
    for item in as_list(value):
        text = as_text(item) if isinstance(item, str) \
            else as_text(as_mapping(item).get(key))
        if text is not None:
            out.append(text)
    return out or None


def as_number(value, allow_text=False):
    """`value` as a float, or None when it is not a number.

    `bool` is excluded because it is a subclass of `int` in Python, so a
    JSON `true` would otherwise arrive as 1.0.

    `allow_text=True` also accepts a numeric string, for the fields an
    upstream documents as strings - Audible's series `sequence` is one.
    It is off by default so that a string arriving in a field documented
    as a number reads as the type change it is, rather than being quietly
    coerced into a value.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if allow_text and isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None
