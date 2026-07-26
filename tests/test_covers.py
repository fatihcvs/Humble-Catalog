from humble_catalog import covers, db
from humble_catalog.covers import cover_filename


def test_cover_filename_is_slug_plus_12_hex_and_jpg():
    name = cover_filename("cooltower_android")
    assert name.startswith("cooltower_android-") and name.endswith(".jpg")
    suffix = name[len("cooltower_android-"):-len(".jpg")]
    assert len(suffix) == 12
    assert all(c in "0123456789abcdef" for c in suffix)


def test_cover_filename_is_deterministic():
    assert cover_filename("cooltower_android") == cover_filename("cooltower_android")


def test_cover_filename_case_variants_do_not_collide():
    # slugs are both lowercased, so only the hash (over the raw name) differs
    assert cover_filename("Foo_ebook") != cover_filename("foo_ebook")
    assert cover_filename("Foo_ebook").rsplit("-", 1)[0] \
        == cover_filename("foo_ebook").rsplit("-", 1)[0] == "foo_ebook"


def test_cover_filename_sanitizes_unsafe_characters():
    name = cover_filename("weird/name ebook")
    assert "/" not in name and " " not in name
    assert name.startswith("weird_name_ebook-")


def test_cover_filename_reserved_name_is_never_bare():
    # 'con' is an illegal Windows filename; the suffix keeps it from being bare
    assert cover_filename("con").startswith("con-")
    assert cover_filename("con") != "con.jpg"


def test_relink_links_existing_file(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    conn.execute("INSERT INTO items (machine_name, name, cover_url) "
                 "VALUES ('cooltower_android','Cool Tower Defense','http://x')")
    conn.commit()
    covers_dir = tmp_path / "covers"
    covers_dir.mkdir()
    fname = covers.cover_filename("cooltower_android")
    (covers_dir / fname).write_bytes(b"\xff\xd8jpg")
    assert covers.relink(conn, covers_dir) == 1
    assert conn.execute("SELECT cover_path FROM items").fetchone()["cover_path"] \
        == f"covers/{fname}"


def test_relink_skips_items_with_no_file(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    conn.execute("INSERT INTO items (machine_name, name) VALUES ('m','N')")
    conn.commit()
    assert covers.relink(conn, tmp_path / "covers") == 0
    assert conn.execute("SELECT cover_path FROM items").fetchone()["cover_path"] is None


def test_relink_leaves_already_linked_rows_alone(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    conn.execute("INSERT INTO items (machine_name, name, cover_path) "
                 "VALUES ('m','N','covers/old.jpg')")
    conn.commit()
    assert covers.relink(conn, tmp_path / "covers") == 0
    assert conn.execute("SELECT cover_path FROM items").fetchone()["cover_path"] \
        == "covers/old.jpg"
