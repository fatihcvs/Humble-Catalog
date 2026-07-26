import json
from unittest.mock import Mock
from humble_catalog import db, enrich
from humble_catalog.sources.base import candidate

def _seed(conn, name="All Systems Red", typ="ebook"):
    cur = conn.execute(
        "INSERT INTO items (machine_name, name, type) VALUES (?,?,?)",
        (name.lower().replace(" ", ""), name, typ))
    conn.execute("INSERT INTO enrichment (item_id) VALUES (?)", (cur.lastrowid,))
    conn.commit()
    return cur.lastrowid

def _source(cands):
    src = Mock()
    src.lookup.return_value = cands
    return src

def test_confident_match_written(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    item_id = _seed(conn)
    good = candidate(source="hardcover", title="All Systems Red",
                     authors=["Martha Wells"], genre="Science Fiction",
                     series="The Murderbot Diaries", series_number=1.0, rating=4.3,
                     url="https://hardcover.app/books/all-systems-red")
    enrich.run(db_path=tmp_path / "t.db",
               sources={"hardcover": _source([good])},
               _conn=conn)
    row = conn.execute("SELECT * FROM enrichment WHERE item_id=?", (item_id,)).fetchone()
    assert row["status"] == "matched"
    assert json.loads(row["authors"]) == ["Martha Wells"]
    assert json.loads(row["genre"]) == ["Science Fiction"]
    assert row["series"] == "The Murderbot Diaries"
    assert row["rating_source"] == "hardcover"
    assert row["source_url"] == "https://hardcover.app/books/all-systems-red"
    assert json.loads(row["candidates"])  # candidates stored for review UI

def test_poor_match_flagged_not_applied(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    item_id = _seed(conn, name="Extremely Obscure RPG Supplement")
    bad = candidate(source="google_books", title="Cooking for Two", rating=3.0)
    enrich.run(db_path=tmp_path / "t.db",
               sources={"hardcover": _source([]), "google_books": _source([bad]),
                        "open_library": _source([])},
               _conn=conn)
    row = conn.execute("SELECT * FROM enrichment WHERE item_id=?", (item_id,)).fetchone()
    assert row["status"] == "unmatched"
    assert row["genre"] is None

def test_progress_printed_before_slow_lookup(tmp_path, capsys):
    # The item line must appear BEFORE sources run, so slow lookups
    # (e.g. Comic Vine's 20s throttle) never leave the console silent.
    conn = db.connect(tmp_path / "t.db")
    _seed(conn)
    printed_before_lookup = []

    def lookup(title):
        printed_before_lookup.append("Item 1/1" in capsys.readouterr().out)
        return []

    src = Mock()
    src.lookup.side_effect = lookup
    enrich.run(db_path=tmp_path / "t.db",
               sources={"hardcover": src, "google_books": src,
                        "open_library": src},
               _conn=conn)
    assert printed_before_lookup[0] is True

def test_music_items_are_skipped_not_looked_up(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    _seed(conn, name="BioShock OST", typ="music")
    src = _source([candidate(source="hardcover", title="BioShock OST")])
    enrich.run(db_path=tmp_path / "t.db",
               sources={"hardcover": src, "google_books": src,
                        "open_library": src},
               _conn=conn)
    src.lookup.assert_not_called()
    assert conn.execute("SELECT status FROM enrichment").fetchone()["status"] == "skipped"

def test_android_items_are_skipped_not_looked_up(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    _seed(conn, name="Cool Tower Defense", typ="android")
    src = _source([candidate(source="hardcover", title="Cool Tower Defense")])
    enrich.run(db_path=tmp_path / "t.db",
               sources={"hardcover": src, "google_books": src,
                        "open_library": src},
               _conn=conn)
    src.lookup.assert_not_called()
    assert conn.execute("SELECT status FROM enrichment").fetchone()["status"] == "skipped"

def test_match_consults_all_sources_no_early_break(tmp_path):
    # Even after a confident hit from the first source, later sources are
    # still scored -- harvest fetched them, matching should use them.
    conn = db.connect(tmp_path / "t.db")
    _seed(conn)  # "All Systems Red", ebook
    strong = _source([candidate(source="hardcover", title="All Systems Red")])
    second = _source([candidate(source="google_books", title="All Systems Red")])
    enrich.run(db_path=tmp_path / "t.db",
               sources={"hardcover": strong, "google_books": second,
                        "open_library": _source([])}, _conn=conn)
    strong.lookup.assert_called_once()
    second.lookup.assert_called_once()  # NOT skipped by an early break

def test_match_skips_source_on_cachemiss(tmp_path):
    from humble_catalog.sources.base import CacheMiss
    conn = db.connect(tmp_path / "t.db")
    item_id = _seed(conn)
    missing = Mock()
    missing.lookup.side_effect = CacheMiss("not harvested")
    good = _source([candidate(source="google_books", title="All Systems Red",
                              genre="Science Fiction")])
    enrich.run(db_path=tmp_path / "t.db",
               sources={"hardcover": missing, "google_books": good,
                        "open_library": _source([])}, _conn=conn)
    row = conn.execute("SELECT status FROM enrichment WHERE item_id=?",
                       (item_id,)).fetchone()
    assert row["status"] == "matched"  # CacheMiss did not abort the item

def test_default_sources_are_offline(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    srcs = enrich._default_sources(conn, offline=True)
    assert all(s.offline for s in srcs.values())
    assert set(srcs) >= {"hardcover", "google_books", "open_library",
                         "oreilly", "audible", "comicvine"}

def test_retry_reprocesses_unmatched(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    _seed(conn)
    conn.execute("UPDATE enrichment SET status='unmatched'")
    conn.commit()
    good = candidate(source="hardcover", title="All Systems Red", genre="SF")
    src = _source([good])
    enrich.run(db_path=tmp_path / "t.db", sources={"hardcover": src}, _conn=conn)
    src.lookup.assert_not_called()  # without --retry: untouched
    enrich.run(db_path=tmp_path / "t.db", sources={"hardcover": src},
               _conn=conn, retry=True)
    assert conn.execute("SELECT status FROM enrichment").fetchone()["status"] == "matched"

def _seed_enriched(conn, name, status):
    item_id = _seed(conn, name=name)
    conn.execute(
        "UPDATE enrichment SET status=?, genre='G', authors='A', "
        "external_rating=4.0, rating_source='s', match_confidence=0.9, "
        "source_url='https://x/', candidates='[{\"title\":\"T\"}]' "
        "WHERE item_id=?", (status, item_id))
    conn.execute("UPDATE items SET my_rating=5, type='comic', type_overridden=1 "
                 "WHERE id=?", (item_id,))
    conn.commit()
    return item_id

def test_reset_clears_all_enrichment_keeps_overrides(tmp_path, capsys):
    conn = db.connect(tmp_path / "t.db")
    matched = _seed_enriched(conn, "Book One", "matched")
    fixed = _seed_enriched(conn, "Book Two", "manually_fixed")
    n = enrich.reset(db_path=tmp_path / "t.db", _conn=conn)
    assert n == 2
    for item_id in (matched, fixed):
        row = conn.execute("SELECT * FROM enrichment WHERE item_id=?",
                           (item_id,)).fetchone()
        assert row["status"] == "pending"
        assert row["genre"] is None and row["candidates"] is None
        assert row["source_url"] is None and row["match_confidence"] is None
        item = conn.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
        assert item["my_rating"] == 5          # user data survives
        assert item["type"] == "comic" and item["type_overridden"] == 1
    assert "2" in capsys.readouterr().out

def test_reset_reviews_only_touches_manually_fixed(tmp_path, capsys):
    conn = db.connect(tmp_path / "t.db")
    matched = _seed_enriched(conn, "Book One", "matched")
    fixed = _seed_enriched(conn, "Book Two", "manually_fixed")
    n = enrich.reset(db_path=tmp_path / "t.db", reviews_only=True, _conn=conn)
    assert n == 1
    assert conn.execute("SELECT status FROM enrichment WHERE item_id=?",
                        (matched,)).fetchone()["status"] == "matched"
    row = conn.execute("SELECT * FROM enrichment WHERE item_id=?",
                       (fixed,)).fetchone()
    assert row["status"] == "pending" and row["genre"] is None

def test_full_reset_clears_hand_edits(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    item_id = _seed_enriched(conn, "Book One", "matched")
    conn.execute("UPDATE enrichment SET pre_edit='{\"genre\":\"G\"}' "
                 "WHERE item_id=?", (item_id,))
    conn.commit()
    enrich.reset(db_path=tmp_path / "t.db", _conn=conn)
    row = conn.execute("SELECT status, pre_edit FROM enrichment "
                       "WHERE item_id=?", (item_id,)).fetchone()
    assert row["status"] == "pending" and row["pre_edit"] is None

def test_reset_reviews_skips_hand_edited_rows(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    edited = _seed_enriched(conn, "Book One", "manually_fixed")
    plain = _seed_enriched(conn, "Book Two", "manually_fixed")
    # hand_edited is what spares the row now; a snapshot alone marks a
    # re-enriched row, which --reset-reviews is meant to sweep
    conn.execute("UPDATE enrichment SET pre_edit='{\"genre\":null}', "
                 "hand_edited=1 WHERE item_id=?", (edited,))
    conn.commit()
    n = enrich.reset(db_path=tmp_path / "t.db", reviews_only=True, _conn=conn)
    assert n == 1
    row = conn.execute("SELECT status, genre FROM enrichment WHERE item_id=?",
                       (edited,)).fetchone()
    assert row["status"] == "manually_fixed" and row["genre"] == "G"
    assert conn.execute("SELECT status FROM enrichment WHERE item_id=?",
                        (plain,)).fetchone()["status"] == "pending"

def test_manually_fixed_untouched(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    item_id = _seed(conn)
    conn.execute("UPDATE enrichment SET status='manually_fixed', genre='Keep Me'")
    conn.commit()
    src = _source([candidate(source="hardcover", title="All Systems Red")])
    enrich.run(db_path=tmp_path / "t.db", sources={"hardcover": src}, _conn=conn)
    src.lookup.assert_not_called()
    assert conn.execute("SELECT genre FROM enrichment WHERE item_id=?",
                        (item_id,)).fetchone()["genre"] == "Keep Me"

def test_apply_candidate_normalizes_genre_case(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    conn.execute("INSERT INTO items (machine_name, name) VALUES ('a','A')")
    conn.execute("INSERT INTO enrichment (item_id, genre) VALUES (1, ?)",
                 (db.tags_to_json(["Science Fiction"]),))
    conn.execute("INSERT INTO items (machine_name, name) VALUES ('b','B')")
    conn.execute("INSERT INTO enrichment (item_id, status) VALUES (2, 'pending')")
    conn.commit()
    cand = {"source": "hardcover", "title": "B", "genre": "science fiction",
            "authors": ["ann author"], "url": None}
    enrich.apply_candidate(conn, 2, cand, 0.9, "matched")
    row = conn.execute("SELECT genre, authors FROM enrichment "
                       "WHERE item_id=2").fetchone()
    assert db.tags_from_json(row["genre"]) == ["Science Fiction"]  # snapped
    assert db.tags_from_json(row["authors"]) == ["ann author"]     # untouched

def test_credits_topup_fills_matched_comic(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    item_id = _seed(conn, name="Shadow Hound", typ="comic")
    winning = {"source": "comicvine", "title": "Shadow Hound", "confidence": 0.95,
               "extra": {"first_issue_api_url":
                         "https://comicvine.gamespot.com/api/issue/4000-9/"}}
    conn.execute("UPDATE enrichment SET status='matched', candidates=? "
                 "WHERE item_id=?", (json.dumps([winning]), item_id))
    conn.commit()
    cv = Mock()
    cv.credits.return_value = ("Bo Writer", "Ann Inker")
    n = enrich.credits(db_path=tmp_path / "t.db", comicvine=cv, _conn=conn)
    cv.credits.assert_called_once_with(
        "https://comicvine.gamespot.com/api/issue/4000-9/")
    row = conn.execute("SELECT authors, illustrator FROM enrichment "
                       "WHERE item_id=?", (item_id,)).fetchone()
    assert json.loads(row["authors"]) == ["Bo Writer"]
    assert json.loads(row["illustrator"]) == ["Ann Inker"]
    assert n == 1

def test_credits_skips_comic_without_issue_url(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    item_id = _seed(conn, name="No Issue Comic", typ="comic")
    cand = {"source": "google_books", "title": "No Issue Comic",
            "confidence": 0.9, "extra": {}}
    conn.execute("UPDATE enrichment SET status='matched', candidates=? "
                 "WHERE item_id=?", (json.dumps([cand]), item_id))
    conn.commit()
    cv = Mock()
    n = enrich.credits(db_path=tmp_path / "t.db", comicvine=cv, _conn=conn)
    cv.credits.assert_not_called()
    assert n == 0

def test_reset_preserves_user_columns(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    conn.execute("INSERT INTO items (machine_name, name, user_tags, "
                 "user_comment) VALUES ('m','N',?,?)",
                 (db.tags_to_json(["to reread"]), "My note."))
    conn.execute("INSERT INTO enrichment (item_id, status) "
                 "VALUES (1,'matched')")
    conn.commit()
    enrich.reset(db_path=tmp_path / "t.db", _conn=conn)
    row = conn.execute("SELECT user_tags, user_comment FROM items").fetchone()
    assert json.loads(row["user_tags"]) == ["to reread"]
    assert row["user_comment"] == "My note."
    # and the row is genuinely back in the enrichment queue
    assert conn.execute(
        "SELECT status FROM enrichment").fetchone()["status"] == "pending"

def test_apply_candidate_resnapshots_a_hand_edited_row(tmp_path):
    # Without this, an override would overwrite the typed values while
    # pre_edit still pointed at the OLD enriched state - Revert would then
    # restore stale machine data and the hand edit would be gone for good.
    conn = db.connect(tmp_path / "t.db")
    item_id = _seed(conn)
    db.apply_hand_edit(conn, item_id, {"series": "Harbor Tales"})
    cand = candidate(source="hardcover", title="All Systems Red",
                     series="The Murderbot Diaries")
    enrich.apply_candidate(conn, item_id, cand, 0.95, "matched")
    row = conn.execute("SELECT * FROM enrichment WHERE item_id=?",
                       (item_id,)).fetchone()
    assert row["series"] == "The Murderbot Diaries"
    assert row["hand_edited"] == 0
    assert row["enrich_override"] == 0
    assert json.loads(row["pre_edit"])["series"] == "Harbor Tales"

def test_apply_candidate_leaves_a_plain_row_without_a_revert_target(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    item_id = _seed(conn)
    cand = candidate(source="hardcover", title="All Systems Red")
    enrich.apply_candidate(conn, item_id, cand, 0.95, "matched")
    row = conn.execute("SELECT pre_edit, hand_edited FROM enrichment "
                       "WHERE item_id=?", (item_id,)).fetchone()
    assert row["pre_edit"] is None and row["hand_edited"] == 0

def _hand_edited(conn, item_id, **fields):
    """A row typed in by hand, as apply_hand_edit leaves it."""
    db.apply_hand_edit(conn, item_id, fields)
    conn.execute("UPDATE enrichment SET status='manually_fixed' WHERE item_id=?",
                 (item_id,))
    conn.commit()

def test_override_lets_a_confident_match_through(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    item_id = _seed(conn)
    _hand_edited(conn, item_id, series="Harbor Tales")
    conn.execute("UPDATE enrichment SET enrich_override=1 WHERE item_id=?",
                 (item_id,))
    conn.commit()
    good = candidate(source="hardcover", title="All Systems Red",
                     authors=["Martha Wells"], series="The Murderbot Diaries")
    enrich.run(db_path=tmp_path / "t.db",
               sources={"hardcover": _source([good])}, _conn=conn)
    row = conn.execute("SELECT * FROM enrichment WHERE item_id=?",
                       (item_id,)).fetchone()
    assert row["status"] == "matched"
    assert row["series"] == "The Murderbot Diaries"
    assert row["hand_edited"] == 0 and row["enrich_override"] == 0
    assert json.loads(row["pre_edit"])["series"] == "Harbor Tales"

def test_override_without_a_match_changes_nothing_but_the_flag(tmp_path):
    # THE load-bearing test. If a future edit lets an overridden row fall
    # through to the ordinary unmatched path, a hand edit is silently
    # stripped and nothing is gained. This must fail loudly if that happens.
    conn = db.connect(tmp_path / "t.db")
    item_id = _seed(conn, name="Extremely Obscure RPG Supplement")
    _hand_edited(conn, item_id, series="Harbor Tales")
    conn.execute("UPDATE enrichment SET enrich_override=1 WHERE item_id=?",
                 (item_id,))
    conn.commit()
    before = dict(conn.execute("SELECT * FROM enrichment WHERE item_id=?",
                               (item_id,)).fetchone())
    bad = candidate(source="google_books", title="Cooking for Two")
    enrich.run(db_path=tmp_path / "t.db",
               sources={"hardcover": _source([]), "google_books": _source([bad]),
                        "open_library": _source([])}, _conn=conn)
    after = dict(conn.execute("SELECT * FROM enrichment WHERE item_id=?",
                              (item_id,)).fetchone())
    assert after.pop("enrich_override") == 0
    before.pop("enrich_override")
    assert after == before  # status, series, pre_edit, candidates: all intact

def test_override_is_one_shot(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    item_id = _seed(conn)
    _hand_edited(conn, item_id, series="Harbor Tales")
    conn.execute("UPDATE enrichment SET enrich_override=1 WHERE item_id=?",
                 (item_id,))
    conn.commit()
    good = candidate(source="hardcover", title="All Systems Red",
                     series="The Murderbot Diaries")
    enrich.run(db_path=tmp_path / "t.db",
               sources={"hardcover": _source([good])}, _conn=conn)
    # a hand edit made AFTER the override must survive the next run
    db.apply_hand_edit(conn, item_id, {"series": "Second Thoughts"})
    enrich.run(db_path=tmp_path / "t.db",
               sources={"hardcover": _source([good])}, _conn=conn)
    row = conn.execute("SELECT series, hand_edited FROM enrichment "
                       "WHERE item_id=?", (item_id,)).fetchone()
    assert row["series"] == "Second Thoughts" and row["hand_edited"] == 1

def test_reset_reviews_spares_hand_edits_but_sweeps_re_enriched(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    kept = _seed(conn, name="The Quiet Harbor")
    swept = _seed(conn, name="A Second Book")
    _hand_edited(conn, kept, series="Harbor Tales")
    # a re-enriched row: snapshot kept, authorship handed back to enrichment
    conn.execute("UPDATE enrichment SET status='manually_fixed', "
                 "pre_edit='{}', hand_edited=0 WHERE item_id=?", (swept,))
    conn.commit()
    enrich.reset(reviews_only=True, _conn=conn)
    rows = dict(conn.execute("SELECT item_id, status FROM enrichment"))
    assert rows[kept] == "manually_fixed"
    assert rows[swept] == "pending"

def test_override_edited_requires_the_typed_word(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    item_id = _seed(conn)
    _hand_edited(conn, item_id, series="Harbor Tales")
    n = enrich.override_edited(db_path=tmp_path / "t.db", _conn=conn,
                               _input=lambda prompt: "yes")
    assert n == 0
    row = conn.execute("SELECT series, enrich_override FROM enrichment "
                       "WHERE item_id=?", (item_id,)).fetchone()
    assert row["series"] == "Harbor Tales" and row["enrich_override"] == 0

def test_override_edited_queues_on_confirmation(tmp_path, monkeypatch):
    conn = db.connect(tmp_path / "t.db")
    item_id = _seed(conn)
    _hand_edited(conn, item_id, series="Harbor Tales")
    monkeypatch.setattr(enrich, "run", lambda **kw: None)  # queue only
    n = enrich.override_edited(db_path=tmp_path / "t.db", _conn=conn,
                               _input=lambda prompt: "OVERRIDE")
    assert n == 1
    assert conn.execute("SELECT enrich_override FROM enrichment WHERE item_id=?",
                        (item_id,)).fetchone()[0] == 1

def test_override_edited_with_nothing_to_do_never_prompts(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    _seed(conn)  # enriched, not hand-edited
    def refuse(prompt):
        raise AssertionError("must not prompt when there is nothing to override")
    assert enrich.override_edited(db_path=tmp_path / "t.db", _conn=conn,
                                  _input=refuse) == 0

def test_override_edited_refuses_without_a_tty(tmp_path, monkeypatch):
    conn = db.connect(tmp_path / "t.db")
    item_id = _seed(conn)
    _hand_edited(conn, item_id, series="Harbor Tales")
    monkeypatch.setattr(enrich.sys.stdin, "isatty", lambda: False)
    assert enrich.override_edited(db_path=tmp_path / "t.db", _conn=conn) == 0
    assert conn.execute("SELECT enrich_override FROM enrichment WHERE item_id=?",
                        (item_id,)).fetchone()[0] == 0

def test_run_tallies_every_outcome_and_reports_from_them(tmp_path, capsys):
    # the live scoreboard and the summary are the same numbers; an outcome
    # that stops being counted must show up as a wrong summary, not silently
    conn = db.connect(tmp_path / "t.db")
    _seed(conn, name="All Systems Red")                      # -> matched
    _seed(conn, name="Extremely Obscure RPG Supplement")     # -> unmatched
    _seed(conn, name="Neon Drift OST", typ="music")          # -> skipped
    good = candidate(source="hardcover", title="All Systems Red",
                     authors=["Martha Wells"])
    bad = candidate(source="hardcover", title="Cooking for Two")

    def lookup(title):
        return [good] if title == "All Systems Red" else [bad]

    src = Mock()
    src.lookup.side_effect = lookup
    enrich.run(db_path=tmp_path / "t.db", sources={"hardcover": src}, _conn=conn)
    out = capsys.readouterr().out
    assert "Enriched 3 items: 1 matched automatically, 2 need review or retry." in out
    statuses = dict(conn.execute(
        "SELECT i.name, e.status FROM items i JOIN enrichment e ON e.item_id=i.id"))
    assert statuses["All Systems Red"] == "matched"
    assert statuses["Extremely Obscure RPG Supplement"] == "unmatched"
    assert statuses["Neon Drift OST"] == "skipped"

def test_run_counts_source_errors_once_per_item(tmp_path, capsys):
    conn = db.connect(tmp_path / "t.db")
    _seed(conn, name="Gray Waters")
    broken = Mock()
    broken.lookup.side_effect = RuntimeError("503 upstream")
    enrich.run(db_path=tmp_path / "t.db",
               sources={"hardcover": broken, "google_books": broken}, _conn=conn)
    out = capsys.readouterr().out
    assert out.count("503 upstream") == 2          # logged per failing source
    assert "1 items hit source errors" in out      # but counted per item
