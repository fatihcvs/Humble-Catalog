import re

_COMIC_BUNDLE_HINTS = ("comic", "manga", "graphic novel")
_COMIC_FORMATS = {"cbz", "cbr"}
# A trailing "(audio)" is a format label on a book, not a subject. It is
# matched only at the END of the name: a bare "audio" substring would
# sweep in every soundtrack and ambience pack, which is exactly what the
# audio branch below exists to keep out. Measured blast radius on the
# catalog: 2 items, both genuine audio editions of owned ebooks, and no
# item anywhere carries a type override to be stomped.
_TRAILING_AUDIO = re.compile(r"\(\s*audio\s*\)\s*$", re.IGNORECASE)

def classify(bundle_name, platforms, formats, item_name=""):
    """Classify a HumbleBundle item as android / ebook / audiobook / comic / music.

    Android wins outright: a game shipping an APK plus soundtrack is a game,
    not music, and a game bundled with a PDF manual is a game, not an ebook.
    Audio counts as an audiobook only when the bundle or item name says
    so -- the literal word "audiobook", or a trailing "(audio)" label;
    game bundles and music bundles also deliver audio (soundtracks, albums,
    TTRPG ambience) and those must not pollute the audiobook list."""
    if "android" in platforms:
        return "android"
    lowered_bundle = bundle_name.lower()
    lowered_item = item_name.lower()
    if "audio" in platforms:
        if "audiobook" in lowered_bundle or "audiobook" in lowered_item \
                or _TRAILING_AUDIO.search(item_name):
            return "audiobook"
        return "music"
    if any(h in lowered_bundle for h in _COMIC_BUNDLE_HINTS) or (formats & _COMIC_FORMATS):
        return "comic"
    return "ebook"
