import datetime as dt
import io
import json
import webbrowser
from pathlib import Path
import requests
from flask import Flask, Response, g, jsonify, request, send_from_directory
from humble_catalog import (bundle_preview, db, dedupe, editions, export,
                            keys, stats, url_import)
from humble_catalog.enrich import EDITABLE_FIELDS, apply_candidate
from humble_catalog.sources.base import candidate

# The only authorities the viewer answers to. Everything here is served
# on 127.0.0.1, so any other name means the request was addressed
# somewhere else and merely arrived here -- which is exactly what DNS
# rebinding looks like: a page on evil.com whose name is re-pointed at
# 127.0.0.1 becomes same-origin with the viewer, and same-origin policy
# stops protecting the catalog. The browser keeps sending Host: evil.com,
# so refusing unknown hosts closes it.
LOOPBACK_AUTHORITIES = frozenset({"127.0.0.1", "localhost", "[::1]"})


def host_is_loopback(host_header):
    """True when the Host header addresses this machine by a loopback name.

    The port is deliberately not checked. The security property comes from
    the *name*: a browser sets Host from the URL it was given and a page
    cannot forge it cross-origin, so an attacker cannot present a loopback
    name they do not already control. Pinning the port would add no defence
    and would break a legitimate `serve --port` or HUMBLE_PORT override.
    """
    if not host_header:
        # HTTP/1.1 requires Host. Absent, there is nothing to validate, so
        # fail closed rather than guess.
        return False
    authority = host_header.strip().lower()
    if authority.startswith("["):        # IPv6 literal: [::1] or [::1]:8087
        name = authority.partition("]")[0] + "]"
    else:
        name = authority.partition(":")[0]
    return name in LOOPBACK_AUTHORITIES


def _sorted_candidates(raw):
    # Single source of truth for candidate ordering: /api/review presents
    # this order and /choose receives an index into it, so both must sort
    # identically (stable sort keeps stored order on confidence ties).
    cands = json.loads(raw or "[]")
    cands.sort(key=lambda c: c.get("confidence", 0), reverse=True)
    return cands

def create_app(db_path="catalog.db", covers_dir="covers"):
    app = Flask(__name__, static_folder="static", static_url_path="/static")
    app.config["DB_PATH"] = db_path
    covers = Path(covers_dir).resolve()

    @app.before_request
    def refuse_foreign_hosts():
        # Before routing, so a foreign caller cannot reach any handler --
        # not even by getting the content type right on a write.
        if not host_is_loopback(request.headers.get("Host")):
            return Response(
                "Refused: the catalog viewer only answers requests "
                "addressed to localhost.\n",
                status=403, mimetype="text/plain")

    def conn():
        if "conn" not in g:
            g.conn = db.connect(app.config["DB_PATH"])
        return g.conn

    @app.teardown_appcontext
    def close(_exc):
        c = g.pop("conn", None)
        if c is not None:
            c.close()

    @app.get("/")
    def index():
        return send_from_directory(app.static_folder, "index.html")

    @app.get("/covers/<path:filename>")
    def cover(filename):
        return send_from_directory(covers, filename)

    @app.get("/api/items")
    def items():
        rows = db.fetch_items(conn())
        # Attached HERE and not in fetch_items, which is shared with CSV
        # and XLSX export: an edition link is a derived view, while the
        # export stays a serialization of what the catalog stores. One
        # O(n) pass over the payload, no per-item query.
        #
        # The key is absent rather than [] for the rows with no sibling,
        # which is nearly all of them on a real catalog.
        by_id = {i["id"]: i for i in rows}
        for group in editions.find_groups(conn()):
            for iid in group:
                by_id[iid]["editions"] = [
                    {"id": o, "type": by_id[o]["type"], "name": by_id[o]["name"]}
                    for o in group if o != iid]
        return jsonify({"items": rows})

    @app.get("/api/stats")
    def catalog_stats():
        # A reshaping of stats.report, never a second count: the CLI and
        # this route must not be able to disagree. GET with no parameters
        # -- the report is always the whole catalog, so there is nothing
        # to pass, and nothing about the library reaches a query string.
        sections, total = stats.report(db.fetch_items(conn()))
        return jsonify({
            "total": total,
            "sections": [
                {"key": key, "label": label,
                 "rows": [{"label": row_label, "count": count}
                          for row_label, count in rows]}
                for key, label, rows in sections]})

    @app.get("/api/keys")
    def key_report():
        # The same shape keys.report returns, jsonified and nothing more:
        # the CLI and this panel must not be able to disagree, which is the
        # rule /api/stats follows. GET with no parameters -- the report is
        # always the whole key set, so there is nothing to pass, and
        # nothing about the library reaches a query string.
        return jsonify(keys.report(conn()))

    def _key_ref():
        """(gamekey, machine_name) from the request body, or (None, None).

        Both travel in a POST body, never a query string: machine_name is
        derived from the product title, so it names something owned, and
        query strings reach access logs and browser history. Same reason
        filter-aware export posts its id list rather than passing it.
        """
        data = request.get_json(silent=True) or {}
        gamekey, machine_name = data.get("gamekey"), data.get("machine_name")
        if not isinstance(gamekey, str) or not gamekey \
                or not isinstance(machine_name, str) or not machine_name:
            return None, None
        return gamekey, machine_name

    @app.post("/api/keys/hide")
    def hide_key():
        gamekey, machine_name = _key_ref()
        if gamekey is None:
            return jsonify({"error": "gamekey and machine_name required"}), 400
        exists = conn().execute(
            "SELECT 1 FROM external_keys WHERE gamekey=? AND machine_name=?",
            (gamekey, machine_name)).fetchone()
        if not exists:
            return jsonify({"error": "no such key"}), 400
        # OR IGNORE, so hiding twice keeps the first timestamp rather than
        # refreshing it: the date answers "when did I decide this", and a
        # second click is not a second decision.
        conn().execute(
            "INSERT OR IGNORE INTO hidden_keys "
            "(gamekey, machine_name, hidden_at) VALUES (?,?,?)",
            (gamekey, machine_name,
             dt.datetime.now(dt.timezone.utc).isoformat()))
        conn().commit()
        return jsonify({"ok": True})

    @app.post("/api/keys/unhide")
    def unhide_key():
        gamekey, machine_name = _key_ref()
        if gamekey is None:
            return jsonify({"error": "gamekey and machine_name required"}), 400
        # No existence check against external_keys, unlike hide, and not an
        # oversight: a hide outlives the key it names -- every hide is
        # stale straight after a reset -- and those are exactly the rows
        # most in need of removing. Do not "tidy" this into symmetry.
        conn().execute(
            "DELETE FROM hidden_keys WHERE gamekey=? AND machine_name=?",
            (gamekey, machine_name))
        conn().commit()
        return jsonify({"ok": True})

    @app.post("/api/items/<int:item_id>/rating")
    def set_rating(item_id):
        conn().execute("UPDATE items SET my_rating=? WHERE id=?",
                       (request.get_json()["rating"], item_id))
        conn().commit()
        return jsonify({"ok": True})

    def _item_exists(item_id):
        return conn().execute("SELECT 1 FROM items WHERE id=?",
                              (item_id,)).fetchone() is not None

    # User-owned fields. These deliberately follow the /rating pattern and
    # never reach apply_hand_edit, so writing them leaves pre_edit NULL and
    # the row stays open to re-enrichment.
    @app.post("/api/items/<int:item_id>/user-tags")
    def set_user_tags(item_id):
        tags = (request.get_json() or {}).get("tags")
        if not isinstance(tags, list):
            return jsonify({"error": "tags must be a list"}), 400
        if not _item_exists(item_id):
            return jsonify({"error": "no such item"}), 404
        value = db.tags_to_json(db.normalize_tags(conn(), db.USER_TAGS, tags))
        conn().execute("UPDATE items SET user_tags=? WHERE id=?",
                       (value, item_id))
        conn().commit()
        return jsonify({"ok": True})

    @app.post("/api/items/<int:item_id>/comment")
    def set_comment(item_id):
        comment = (request.get_json() or {}).get("comment")
        if comment is not None and not isinstance(comment, str):
            return jsonify({"error": "comment must be a string"}), 400
        if not _item_exists(item_id):
            return jsonify({"error": "no such item"}), 404
        comment = (comment or "").strip() or None
        conn().execute("UPDATE items SET user_comment=? WHERE id=?",
                       (comment, item_id))
        conn().commit()
        return jsonify({"ok": True})

    @app.post("/api/items/<int:item_id>/type")
    def set_type(item_id):
        new_type = request.get_json()["type"]
        if new_type not in ("ebook", "audiobook", "comic", "music"):
            return jsonify({"error": "bad type"}), 400
        conn().execute("UPDATE items SET type=?, type_overridden=1 WHERE id=?",
                       (new_type, item_id))
        conn().commit()
        return jsonify({"ok": True})

    # read_status is user-owned, like /rating: its own route, never routed
    # through apply_hand_edit, so it never touches pre_edit or hand_edited.
    READ_STATUSES = ("want_to_read", "unread", "reading", "read", "dnf")

    @app.post("/api/items/<int:item_id>/read-status")
    def set_read_status(item_id):
        status = (request.get_json() or {}).get("status")
        if status not in READ_STATUSES:
            return jsonify({"error": "bad status"}), 400
        if not _item_exists(item_id):
            return jsonify({"error": "no such item"}), 404
        conn().execute("UPDATE items SET read_status=? WHERE id=?",
                       (status, item_id))
        conn().commit()
        return jsonify({"ok": True})

    @app.get("/api/review")
    def review():
        rows = conn().execute(
            "SELECT i.id, i.name, i.type, i.cover_path, e.status, e.candidates "
            "FROM items i JOIN enrichment e ON e.item_id = i.id "
            "WHERE e.status IN ('low_confidence','unmatched')").fetchall()
        out = []
        for r in rows:
            cands = _sorted_candidates(r["candidates"])
            out.append({"id": r["id"], "name": r["name"], "type": r["type"],
                        "cover_path": r["cover_path"], "status": r["status"],
                        "candidates": cands,
                        "best": cands[0].get("confidence", 0) if cands else 0})
        out.sort(key=lambda x: (x["best"], x["name"]), reverse=True)
        return jsonify({"items": out})

    @app.get("/api/duplicates")
    def duplicates():
        out = []
        for ids in dedupe.find_groups(conn()):
            members = []
            for iid in ids:
                r = conn().execute(
                    "SELECT i.id, i.machine_name, i.name, i.type, i.cover_path, "
                    "i.publisher, i.my_rating, e.genre, e.series, e.hand_edited "
                    "FROM items i JOIN enrichment e ON e.item_id=i.id "
                    "WHERE i.id=?", (iid,)).fetchone()
                m = dict(r)
                m["genre"] = db.tags_from_json(m["genre"])
                m["edited"] = bool(m.pop("hand_edited"))
                m["bundles"] = [b["name"] for b in conn().execute(
                    "SELECT b.name FROM bundles b "
                    "JOIN item_bundles ib ON ib.gamekey=b.gamekey "
                    "WHERE ib.item_id=? ORDER BY b.name", (iid,))]
                members.append(m)
            out.append(members)
        return jsonify({"groups": out})

    @app.post("/api/merge")
    def merge():
        data = request.get_json() or {}
        keep_id, drop_id = data.get("keep_id"), data.get("drop_id")
        if not isinstance(keep_id, int) or not isinstance(drop_id, int) \
                or keep_id == drop_id:
            return jsonify({"error": "two distinct item ids required"}), 400
        rows = {r["id"]: r["type"] for r in conn().execute(
            "SELECT id, type FROM items WHERE id IN (?,?)", (keep_id, drop_id))}
        if len(rows) != 2:
            return jsonify({"error": "no such item"}), 400
        # An ebook and its audiobook are different files from different
        # bundles, so they stay separate rows. `editions.py` supplies the
        # relationship instead -- this refusal is half an answer without
        # it.
        if rows[keep_id] != rows[drop_id]:
            return jsonify({"error": "items have different types; an ebook "
                            "and its audiobook stay separate"}), 400
        db.merge_items(conn(), keep_id, drop_id)
        return jsonify({"ok": True})

    @app.post("/api/dismiss_pair")
    def dismiss_pair():
        data = request.get_json() or {}
        id_a, id_b = data.get("id_a"), data.get("id_b")
        if not isinstance(id_a, int) or not isinstance(id_b, int) or id_a == id_b:
            return jsonify({"error": "two distinct item ids required"}), 400
        rows = conn().execute(
            "SELECT machine_name FROM items WHERE id IN (?,?)",
            (id_a, id_b)).fetchall()
        if len(rows) != 2:
            return jsonify({"error": "no such item"}), 400
        a, b = sorted(r["machine_name"] for r in rows)
        conn().execute(
            "INSERT OR IGNORE INTO dismissed_pairs (a, b) VALUES (?,?)", (a, b))
        conn().commit()
        return jsonify({"ok": True})

    @app.post("/api/items/<int:item_id>/reopen")
    def reopen(item_id):
        conn().execute(
            "UPDATE enrichment SET status='low_confidence' "
            "WHERE item_id=? AND status != 'pending'", (item_id,))
        conn().commit()
        return jsonify({"ok": True})

    @app.post("/api/items/<int:item_id>/apply")
    def apply_arbitrary(item_id):
        cand = (request.get_json() or {}).get("candidate")
        if not isinstance(cand, dict) or not cand.get("source") or not cand.get("title"):
            return jsonify({"error": "candidate with source and title required"}), 400
        apply_candidate(conn(), item_id, cand, cand.get("confidence", 1.0),
                        "manually_fixed")
        return jsonify({"ok": True})

    @app.post("/api/items/<int:item_id>/edit")
    def edit(item_id):
        fields = (request.get_json() or {}).get("fields")
        if not isinstance(fields, dict) or not fields:
            return jsonify({"error": "fields required"}), 400
        clean = {}
        for key, value in fields.items():
            if key not in EDITABLE_FIELDS:
                return jsonify({"error": f"'{key}' is not editable"}), 400
            if key in db.TAG_FIELDS:
                if not isinstance(value, list):
                    return jsonify({"error": f"'{key}' must be a list of tags"}), 400
                if key == "genre":
                    value = db.normalize_tags(conn(), db.GENRE, value)
                clean[key] = db.tags_to_json(value)
            elif key == "source_url" and value not in (None, ""):
                try:
                    clean[key] = url_import.normalize_url(str(value).strip())
                except ValueError as exc:
                    return jsonify({"error": str(exc)}), 400
            elif value in (None, ""):
                clean[key] = None
            elif key == "series_number":
                try:
                    clean[key] = float(value)
                except (TypeError, ValueError):
                    return jsonify({"error": "series_number must be a number"}), 400
            else:
                clean[key] = str(value)
        if not db.apply_hand_edit(conn(), item_id, clean):
            return jsonify({"error": "no such item"}), 404
        return jsonify({"ok": True})

    @app.post("/api/genres/rename")
    def rename_genre():
        data = request.get_json() or {}
        old = (data.get("old") or "").strip()
        new = (data.get("new") or "").strip()
        if not old or not new:
            return jsonify({"error": "old and new tag names required"}), 400
        changed = db.rename_tag(conn(), db.GENRE, old, new)
        if changed is None:
            return jsonify({"error": f"no such genre tag: {old}"}), 404
        return jsonify({"changed": changed})

    @app.post("/api/genres/delete")
    def delete_genre():
        data = request.get_json() or {}
        tag = (data.get("tag") or "").strip()
        if not tag:
            return jsonify({"error": "tag required"}), 400
        changed = db.delete_tag(conn(), db.GENRE, tag)
        if changed is None:
            return jsonify({"error": f"no such genre tag: {tag}"}), 404
        return jsonify({"changed": changed})

    # The user-tag vocabulary is a separate pool from genre: these mirror
    # the /api/genres routes, one TagColumn argument apart.
    @app.post("/api/user-tags/rename")
    def rename_user_tag():
        data = request.get_json() or {}
        old = (data.get("old") or "").strip()
        new = (data.get("new") or "").strip()
        if not old or not new:
            return jsonify({"error": "old and new tag names required"}), 400
        changed = db.rename_tag(conn(), db.USER_TAGS, old, new)
        if changed is None:
            return jsonify({"error": f"no such user tag: {old}"}), 404
        return jsonify({"changed": changed})

    @app.post("/api/user-tags/delete")
    def delete_user_tag():
        tag = (request.get_json() or {}).get("tag") or ""
        if not tag.strip():
            return jsonify({"error": "tag required"}), 400
        changed = db.delete_tag(conn(), db.USER_TAGS, tag.strip())
        if changed is None:
            return jsonify({"error": f"no such user tag: {tag}"}), 404
        return jsonify({"changed": changed})

    @app.post("/api/user-tags/bulk")
    def bulk_user_tags():
        data = request.get_json() or {}
        ids = data.get("ids")
        tag = (data.get("tag") or "").strip()
        action = data.get("action")
        if not isinstance(ids, list) or not ids:
            return jsonify({"error": "ids must be a non-empty list"}), 400
        if not all(isinstance(i, int) for i in ids):
            return jsonify({"error": "ids must be integers"}), 400
        if not tag:
            return jsonify({"error": "tag required"}), 400
        if action not in ("add", "remove"):
            return jsonify({"error": "action must be 'add' or 'remove'"}), 400
        # Unknown ids are ignored rather than rejected: the catalog can
        # change under a page that has been open a while.
        changed = db.bulk_user_tag(conn(), ids, tag, action)
        return jsonify({"changed": changed})

    @app.post("/api/items/<int:item_id>/revert")
    def revert(item_id):
        row = conn().execute("SELECT pre_edit FROM enrichment WHERE item_id=?",
                             (item_id,)).fetchone()
        if row is None or row["pre_edit"] is None:
            return jsonify({"error": "nothing to revert"}), 400
        snapshot = json.loads(row["pre_edit"])
        # Only restore what the snapshot actually captured. A key missing
        # because it predates the field joining EDITABLE_FIELDS means "not
        # recorded", not "was null" - writing NULL there destroys live data.
        restore = [f for f in EDITABLE_FIELDS if f in snapshot]
        conn().execute(
            # Authorship flips rather than being set: pre_edit always holds
            # the OTHER author's values. Reverting a hand edit shows the
            # enriched values again (not edited); reverting a re-enriched row
            # gives the typed values back (edited once more).
            "UPDATE enrichment SET pre_edit=NULL, hand_edited=NOT hand_edited"
            + "".join(f", {f}=?" for f in restore)
            + " WHERE item_id=?",
            (*(snapshot[f] for f in restore), item_id))
        conn().commit()
        return jsonify({"ok": True})

    @app.post("/api/items/<int:item_id>/override")
    def set_override(item_id):
        """Queue (or unqueue) one hand-edited row for re-enrichment.

        One-shot: the next enrich run consumes the flag. Nothing changes
        until that run, so this is safe to toggle freely.
        """
        want = (request.get_json() or {}).get("override")
        if not isinstance(want, bool):
            return jsonify({"error": "override must be a boolean"}), 400
        row = conn().execute("SELECT hand_edited FROM enrichment WHERE item_id=?",
                             (item_id,)).fetchone()
        if row is None:
            return jsonify({"error": "no such item"}), 404
        if want and not row["hand_edited"]:
            # not an error of degree: an un-edited row is already eligible
            return jsonify({"error": "only hand-edited rows need an override"}), 400
        conn().execute("UPDATE enrichment SET enrich_override=? WHERE item_id=?",
                       (1 if want else 0, item_id))
        conn().commit()
        return jsonify({"ok": True})

    @app.post("/api/items/<int:item_id>/fetch_url")
    def fetch_url(item_id):
        url = ((request.get_json() or {}).get("url") or "").strip()
        if not url:
            return jsonify({"error": "url required"}), 400
        try:
            cand = url_import.resolve(conn(), url)
        # MetadataUnavailable first: it is not a ValueError, but keeping the
        # order explicit documents that a rejected URL must never degrade to
        # a link-only candidate.
        except (url_import.MetadataUnavailable, requests.RequestException) as exc:
            row = conn().execute("SELECT name FROM items WHERE id=?",
                                 (item_id,)).fetchone()
            if row is None:
                return jsonify({"error": "no such item"}), 404
            cand = candidate(source=url_import.host_of(url),
                             title=row["name"], url=url)
            cand["link_only"] = True
            cand["reason"] = str(exc)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify({"candidate": cand})

    @app.post("/api/bundle-preview")
    def bundle_preview_route():
        # POST, not GET, for the reason filter-aware export chose one: a
        # bundle URL in a query string reaches access logs and history.
        # Nothing here writes to the catalog -- the report is a question,
        # not a fact about the library.
        url = ((request.get_json() or {}).get("url") or "").strip()
        if not url:
            return jsonify({"error": "url required"}), 400
        try:
            bundle = bundle_preview.fetch_bundle(url)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except requests.RequestException as exc:
            # An upstream failure, not a bad request: 502 keeps a retired
            # bundle distinguishable from a URL we refused.
            return jsonify({"error": str(exc)}), 502
        return jsonify(bundle_preview.preview(conn(), bundle, url=url))

    @app.post("/api/items/<int:item_id>/choose")
    def choose(item_id):
        idx = request.get_json()["candidate"]
        row = conn().execute("SELECT candidates FROM enrichment WHERE item_id=?",
                             (item_id,)).fetchone()
        cands = _sorted_candidates(row["candidates"])
        if not (0 <= idx < len(cands)):
            return jsonify({"error": "bad candidate index"}), 400
        cand = cands[idx]
        apply_candidate(conn(), item_id, cand,
                        cand.get("confidence", 1.0), "manually_fixed")
        return jsonify({"ok": True})

    def _export_request():
        # (ids, error_response). GET is the whole catalog at a plain URL --
        # what a bookmark, a curl, or a script wants. POST carries the ids
        # the viewer is showing, in the order it shows them; the filter
        # predicate lives only in the browser, so the row set has to
        # arrive from there. Not a GET query string: a list of item ids
        # describes the private library, and query strings reach access
        # logs and history.
        #
        # Shared by both format routes so they cannot drift on what a
        # malformed body means.
        #
        # `columns` rides along because the row set and the column set are
        # independent choices that arrive in the same click. A non-list is
        # a 400 like `ids`; an unknown NAME is not -- export._columns drops
        # it, because stored browser state outlives a schema rename.
        if request.method != "POST":
            return None, None, None
        body = request.get_json(silent=True) or {}
        ids = body.get("ids")
        if not isinstance(ids, list):
            return None, None, (jsonify({"error": "ids must be a list"}), 400)
        columns = body.get("columns")
        if columns is not None and not isinstance(columns, list):
            return None, None, (jsonify({"error": "columns must be a list"}), 400)
        return ids, columns, None

    @app.route("/api/export.csv", methods=["GET", "POST"])
    def export_csv():
        ids, columns, err = _export_request()
        if err:
            return err
        buf = io.StringIO(newline="")
        export.write_csv(conn(), buf, ids=ids, columns=columns)
        # utf-8-sig prepends the BOM: same bytes the CLI export writes.
        return Response(buf.getvalue().encode("utf-8-sig"), mimetype="text/csv",
                        headers={"Content-Disposition":
                                 "attachment; filename=catalog.csv"})

    @app.route("/api/export.xlsx", methods=["GET", "POST"])
    def export_xlsx():
        # A sibling route, not a ?format= parameter: the suffix is what
        # makes the GET form bookmarkable and self-describing.
        ids, columns, err = _export_request()
        if err:
            return err
        buf = io.BytesIO()  # binary: openpyxl owns the encoding
        export.write_xlsx(conn(), buf, ids=ids, columns=columns)
        return Response(
            buf.getvalue(),
            mimetype="application/vnd.openxmlformats-officedocument"
                     ".spreadsheetml.sheet",
            headers={"Content-Disposition":
                     "attachment; filename=catalog.xlsx"})

    @app.get("/api/status")
    def status():
        rows = conn().execute("SELECT * FROM run_status WHERE phase != 'done'").fetchall()
        return jsonify({"runs": [dict(r) for r in rows]})

    return app

def serve(db_path="catalog.db", port=8087):
    app = create_app(db_path=db_path)
    webbrowser.open(f"http://127.0.0.1:{port}/")
    app.run(host="127.0.0.1", port=port)
