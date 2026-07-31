"""The demo catalog must stay loadable as the schema moves.

Titles are invented -- see docs/TEST-DATA.md. This file is what stops
scripts/demo_catalog.py rotting unnoticed between visual checks."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import demo_catalog                                    # noqa: E402
from humble_catalog import db                          # noqa: E402


def test_seed_builds_a_loadable_catalog(tmp_path):
    dbp = tmp_path / "demo.db"
    demo_catalog.seed(dbp)
    items = db.fetch_items(db.connect(dbp))
    assert len(items) == len(demo_catalog.DEMO_ROWS)
    # fetch_items is what /api/items and the export both go through, so
    # loading cleanly is the property worth asserting.
    assert all(i["name"] and i["type"] for i in items)


def test_seed_covers_every_item_type(tmp_path):
    # The tool exists for visual checks in general, not one feature, so
    # a type missing here is a viewer surface nobody can eyeball.
    dbp = tmp_path / "demo.db"
    demo_catalog.seed(dbp)
    types = {i["type"] for i in db.fetch_items(db.connect(dbp))}
    assert types == {"ebook", "audiobook", "comic", "music", "android"}


def test_seed_is_rerunnable(tmp_path):
    # main() reuses one temp path across runs; a second seed must not
    # trip the machine_name UNIQUE constraint.
    dbp = tmp_path / "demo.db"
    demo_catalog.seed(dbp)
    demo_catalog.seed(dbp)
    assert len(db.fetch_items(db.connect(dbp))) == len(demo_catalog.DEMO_ROWS)


def test_every_row_lands_in_a_bundle(tmp_path):
    # An item in no bundle renders an empty Bundle cell, which is a
    # state worth being able to see deliberately rather than by accident.
    dbp = tmp_path / "demo.db"
    demo_catalog.seed(dbp)
    assert all(i["bundles"] for i in db.fetch_items(db.connect(dbp)))
