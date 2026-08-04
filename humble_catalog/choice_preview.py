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
from humble_catalog import import_games, shapes
from humble_catalog.game_match import (classify_game, keyed_games,
                                       owned_games, prepare_pool)

# Delivery methods that are not storefronts. `other-key` means a key
# redeemed somewhere that is not a store account at all, so no importer
# can ever exist for it -- and the unimported-store warning's whole
# content is "go import that store".
NON_STORES = frozenset({"other-key"})


def delivery_stores(game):
    """The storefronts a Choice game is delivered on, as a set.

    Read through shapes.text_list rather than as_list because this is
    third-party content and the quiet failure is the dangerous one:
    set() over a STRING yields its characters, so a delivery_methods
    field arriving unwrapped as "steam" would produce five single-letter
    storefronts, each read as a store the owner never imported.

    The `or ()` is REQUIRED, not defensive noise: text_list returns None
    rather than [] when there is nothing (so callers can pass it straight
    to `candidate`), and a game with no delivery_methods would otherwise
    raise TypeError here. bundle_preview writes the same `or []`.
    """
    return {store for store in (shapes.text_list(
        shapes.as_mapping(game).get("delivery_methods")) or ())
        if store and store not in NON_STORES}


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
    # Tried only AFTER the imported libraries have said "new", so a game
    # that is both keyed and activated reports as the plain library match
    # it is, and the keyed list stays what it claims to be: the games
    # whose only evidence is a key.
    keyed = keyed_games(conn)
    keyed_pool = prepare_pool(
        [(normalized, display) for normalized, display, _t, _b in keyed])
    # Keyed on the display title, which is what classify_game hands back.
    keyed_extra = {display: (key_type, bundle_name)
                   for _n, display, key_type, bundle_name in keyed}

    owned_items, possible_items, new_items, keyed_items = [], [], [], []
    # Storefronts this month delivers on that still have a game nothing
    # accounted for. Deliberately not every store it delivers on: the
    # warning these feed says those games were counted as new by default,
    # and a store whose every game matched makes that sentence false.
    unmatched_stores = set()
    for machine_name, entry in offered.items():
        entry = shapes.as_mapping(entry)
        # Falls back to the machine_name so counting stays exhaustive even
        # for an entry the page failed to title. A machine_name is not a
        # title, but a missing row would be a wrong count.
        title = shapes.as_text(entry.get("title")) or machine_name
        verdict, match = classify_game(title, library)
        if verdict == "new":
            # Only an outright keyed 'owned' is honoured. A keyed
            # 'possible' would be a guess about a guess, so it is left to
            # fall through to whatever the libraries decided.
            keyed_verdict, keyed_match = classify_game(title, keyed_pool)
            if keyed_verdict == "owned":
                key_type, bundle_name = keyed_extra.get(
                    keyed_match["owned_title"], (None, None))
                keyed_items.append({**keyed_match, "key_type": key_type,
                                    "bundle": bundle_name})
                owned_items.append(title)
                continue
        if verdict == "owned":
            owned_items.append(title)
        elif verdict == "possible":
            possible_items.append(match)
        else:
            new_items.append(title)
            # Only a `new` verdict counts toward the warning. A `possible`
            # was not counted as new either, and an owned game says
            # nothing about a missing importer.
            unmatched_stores |= delivery_stores(entry)

    state = shapes.as_mapping(opts.get("contentChoiceState"))
    libraries = import_games.imported_stores(conn)
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
        # Counted inside `owned` above, listed separately here: the count
        # answers "how much of this do I already have", the list answers
        # "and how sure is that".
        "keyed": len(keyed_items),
        "keyed_items": sorted(keyed_items,
                              key=lambda k: k["offered"].lower()),
        "possible_items": sorted(possible_items,
                                 key=lambda p: p["offered"].lower()),
        "new_items": sorted(new_items, key=str.lower),
        # Listed, never counted. These are coupon-class entries rather
        # than games -- nothing about them can be owned, so folding them
        # into `total` would corrupt every count derived from it. Shown so
        # the report does not appear to be hiding part of the month.
        "extras": sorted(
            (shapes.as_text(shapes.as_mapping(extra).get("human_name"))
             or shapes.as_text(shapes.as_mapping(extra).get("machine_name"))
             or "")
            for extra in shapes.as_list(month.get("extras"))),
        # Whether this month's picks have already been made. bool() rather
        # than a shape assertion: Humble has shipped this as a list, and
        # emptiness is the only property being asked about.
        "claimed": bool(shapes.as_mapping(state.get("initial")
                                          ).get("choices_made")),
        "libraries": libraries,
        # A store this month delivers on that has never been imported and
        # still has a game nothing accounted for. That game was counted as
        # new by DEFAULT, which is a guess dressed as a fact -- so the
        # report says so out loud.
        "unimported_stores": sorted(unmatched_stores - set(libraries)),
    }
