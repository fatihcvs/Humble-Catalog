"""Preview how much of this month's Humble Choice the catalog already holds.

Read-only throughout: nothing here writes to catalog.db. The report is a
question the owner asks before buying, not a fact about the library.

Split at the network seam -- fetch_choice() does the HTTP, preview() is
pure -- so every counting rule is testable from a committed fixture with
no network and no Humble session. Same split, and same reason, as
bundle_preview and harvest.

Unlike a bundle, a Choice month cannot be read exactly. A bundle re-sells
the SAME subproduct, so machine_name is a shared id and ownership is a set
intersection. Choice negotiates fresh games every month, so its ids never
collide with anything already stored -- measured during design: zero of
nine offered games matched by any id the blob carries. Ownership is
therefore decided by TITLE, and the report says so out loud.
"""
from humble_catalog import shapes
from humble_catalog.game_match import (classify_game, owned_games,
                                       prepare_pool)


def _month(hub):
    """(contentChoiceOptions, contentChoiceData) from a parsed hub blob.

    Both through shapes: this is the parsed page, which the envelope
    classes adversarial, and `x or {}` is not a type check -- a non-empty
    list is truthy and would reach the attribute access.
    """
    opts = shapes.as_mapping(shapes.as_mapping(hub).get("contentChoiceOptions"))
    return opts, shapes.as_mapping(opts.get("contentChoiceData"))


def preview(conn, hub):
    """The ownership report for one parsed subscriber-hub blob.

    Pure: no network, no writes. `hub` is what fetch_choice returns -- the
    whole blob, not the month, because the price sits at its top level and
    the month does not carry it.

    Every game gets exactly one verdict. `possible` is the band where the
    tool declines to guess and is counted as NEITHER owned nor new: the
    expensive mistake here is recommending a second purchase.
    """
    opts, month = _month(hub)
    offered = shapes.as_mapping(month.get("game_data"))
    library = prepare_pool(owned_games(conn))

    owned_items, possible_items, new_items = [], [], []
    for machine_name, entry in offered.items():
        entry = shapes.as_mapping(entry)
        # Falls back to the machine_name so counting stays exhaustive even
        # for an entry the page failed to title. A machine_name is not a
        # title, but a missing row would be a wrong count.
        title = shapes.as_text(entry.get("title")) or machine_name
        verdict, match = classify_game(title, library)
        if verdict == "owned":
            owned_items.append(title)
        elif verdict == "possible":
            possible_items.append(match)
        else:
            new_items.append(title)

    money = shapes.as_mapping(hub.get("baseSubscriptionPrice|money"))
    title = shapes.as_text(opts.get("title"))
    return {
        "name": f"Humble Choice: {title}" if title else "Humble Choice",
        # as_number, not a bare get: the amount is formatted with `:.2f`
        # downstream, so a string here must raise at the read that
        # accepted it rather than inside the report.
        "price": shapes.as_number(money.get("amount")) or 0.0,
        "currency": shapes.as_text(money.get("currency")) or "USD",
        "total": len(offered),
        "owned": len(owned_items),
        "possible": len(possible_items),
        "new": len(new_items),
        "owned_items": sorted(owned_items, key=str.lower),
        "possible_items": sorted(possible_items,
                                 key=lambda p: p["offered"].lower()),
        "new_items": sorted(new_items, key=str.lower),
    }
