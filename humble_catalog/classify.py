_COMIC_BUNDLE_HINTS = ("comic", "manga", "graphic novel")
_COMIC_FORMATS = {"cbz", "cbr"}

def classify(bundle_name, platforms, formats, item_name=""):
    """Classify a HumbleBundle item as android / ebook / audiobook / comic / music.

    Android wins outright: a game shipping an APK plus soundtrack is a game,
    not music, and a game bundled with a PDF manual is a game, not an ebook.
    Audio counts as an audiobook only when the bundle or item name says so;
    game bundles and music bundles also deliver audio (soundtracks, albums,
    TTRPG ambience) and those must not pollute the audiobook list."""
    if "android" in platforms:
        return "android"
    lowered_bundle = bundle_name.lower()
    lowered_item = item_name.lower()
    if "audio" in platforms:
        if "audiobook" in lowered_bundle or "audiobook" in lowered_item:
            return "audiobook"
        return "music"
    if any(h in lowered_bundle for h in _COMIC_BUNDLE_HINTS) or (formats & _COMIC_FORMATS):
        return "comic"
    return "ebook"
