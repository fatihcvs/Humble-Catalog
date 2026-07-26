import pytest
from humble_catalog.classify import classify

@pytest.mark.parametrize("bundle,platforms,formats,item,expected", [
    ("Humble Audiobook Bundle: Epic Tales 2020 by Example Audio",
     {"audio"}, {"mp3"}, "Axebearer", "audiobook"),
    ("Sample Authors and More Audiobooks from Example Press",
     {"audio"}, {"mp3"}, "All Systems Red", "audiobook"),
    ("Humble Weekly Bundle: Fiction", {"audio"}, {"mp3"},
     "Dune (Audiobook)", "audiobook"),
    ("Shield Squad", {"audio"}, {"mp3", "flac"},
     "Shield Squad Original Soundtrack", "music"),
    ("Humble Music Bundle", {"audio"}, {"mp3"}, "Some Album", "music"),
    ("Humble Game Bundle: Samples", {"audio"}, {"flac"}, "Sample Game OST", "music"),
    ("Sample Studios: TTRPG Audio Compendium", {"audio"}, {"mp3"},
     "Sample Ambience Pack", "music"),
    ("Humble Comics Bundle: Shadow Hound", {"ebook"}, {"pdf", "cbz"},
     "Shadow Hound Vol 1", "comic"),
    ("2000 AD Presents Judge Dredd", {"ebook"}, {"cbz"}, "Judge Dredd", "comic"),
    ("The World of Examplia", {"ebook"}, {"epub", "pdf"},
     "Wings of Autumn Dusk", "ebook"),
    ("Software Architecture 2025 by O'Reilly", {"ebook"}, {"epub", "pdf"},
     "Building Widget Services 2e", "ebook"),
    ("Humble Mobile Bundle: Indie Games", {"android"}, {"apk"},
     "Cool Tower Defense", "android"),
    # APK + soundtrack is a game, not music: android beats the audio branch
    ("Humble Mobile Bundle: Indie Games", {"android", "audio"}, {"apk", "mp3"},
     "Cool Tower Defense + OST", "android"),
    # APK + PDF manual is a game, not an ebook/comic
    ("Humble Comics Bundle: Games Edition", {"android", "ebook"}, {"apk", "pdf"},
     "Cool Tower Defense", "android"),
])
def test_classify(bundle, platforms, formats, item, expected):
    assert classify(bundle, platforms, formats, item) == expected
