from unittest.mock import Mock
import pytest
import requests
from humble_catalog import db, url_import

def _http(payload=None, text="", ctype="text/html; charset=utf-8", url=None):
    http = Mock()
    resp = Mock(status_code=200)
    resp.json = Mock(return_value=payload)
    resp.text = text
    resp.url = url or "https://examplegames.com/p/1"
    resp.headers = {"Content-Type": ctype}
    resp.encoding = "utf-8"
    resp.iter_content = Mock(return_value=[text.encode("utf-8")])
    resp.raise_for_status = Mock()
    http.request.return_value = resp
    return http

def _conn(tmp_path):
    return db.connect(tmp_path / "t.db")

def test_comicvine_issue_url(tmp_path, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    monkeypatch.setenv("COMICVINE_API_KEY", "k")
    payload = {"results": {
        "name": "Shadow Hound: Origins",
        "site_detail_url": "https://comicvine.gamespot.com/shadow-hound/4000-693789/",
        "person_credits": [{"name": "Bo Writer", "role": "writer"},
                           {"name": "Ann Inker", "role": "artist"}]}}
    http = _http(payload)
    cand = url_import.resolve(
        _conn(tmp_path),
        "https://comicvine.gamespot.com/sample-comic-vol-2/4000-693789/",
        http=http)
    called_url = http.request.call_args[0][1]
    assert "/api/issue/4000-693789/" in called_url
    assert cand["source"] == "comicvine"
    assert cand["title"] == "Shadow Hound: Origins"
    assert cand["authors"] == ["Bo Writer"]
    assert cand["illustrator"] == "Ann Inker"
    assert cand["url"] == "https://comicvine.gamespot.com/shadow-hound/4000-693789/"

def test_comicvine_volume_url_uses_volume_endpoint(tmp_path, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    monkeypatch.setenv("COMICVINE_API_KEY", "k")
    http = _http({"results": {"name": "Shadow Hound", "site_detail_url": "x",
                              "person_credits": []}})
    url_import.resolve(_conn(tmp_path),
                       "https://comicvine.gamespot.com/shadow-hound/4050-123/", http=http)
    assert "/api/volume/4050-123/" in http.request.call_args[0][1]

def test_comicvine_requires_key(tmp_path, monkeypatch):
    monkeypatch.delenv("COMICVINE_API_KEY", raising=False)
    with pytest.raises(ValueError, match="COMICVINE_API_KEY"):
        url_import.resolve(_conn(tmp_path),
                           "https://comicvine.gamespot.com/x/4050-1/", http=_http({}))

def test_hardcover_url_matches_slug_not_first_hit(tmp_path, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    monkeypatch.setenv("HARDCOVER_API_KEY", "t")
    hits = [{"document": {"title": "The Hobbit Annotated", "slug": "the-hobbit-annotated",
                          "author_names": ["J. R. R. Tolkien"], "genres": []}},
            {"document": {"title": "The Hobbit", "slug": "the-hobbit",
                          "author_names": ["J. R. R. Tolkien"], "genres": ["Fantasy"]}}]
    payload = {"data": {"search": {"results": {"hits": hits}}}}
    cand = url_import.resolve(_conn(tmp_path),
                              "https://hardcover.app/books/the-hobbit", http=_http(payload))
    assert cand["title"] == "The Hobbit"
    assert cand["url"] == "https://hardcover.app/books/the-hobbit"

def test_open_library_work_url(tmp_path, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    payload = {"docs": [{"title": "All Systems Red", "author_name": ["Martha Wells"],
                         "key": "/works/OL17091839W", "subject": ["Science fiction"],
                         "ratings_average": 4.2}]}
    http = _http(payload)
    cand = url_import.resolve(
        _conn(tmp_path),
        "https://openlibrary.org/works/OL17091839W/All_Systems_Red", http=http)
    assert http.request.call_args[1]["params"]["q"] == "key:/works/OL17091839W"
    assert cand["source"] == "open_library"
    assert cand["authors"] == ["Martha Wells"]
    assert cand["url"] == "https://openlibrary.org/works/OL17091839W"

def test_google_books_urls(tmp_path, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    payload = {"id": "zyTCAlFPjgYC", "volumeInfo": {
        "title": "The Google Story", "authors": ["David A. Vise"],
        "categories": ["Business"], "averageRating": 3.5,
        "infoLink": "https://books.google.com/books?id=zyTCAlFPjgYC"}}
    urls = ("https://books.google.com/books?id=zyTCAlFPjgYC&hl=en",
            "https://www.google.com/books/edition/The_Google_Story/zyTCAlFPjgYC")
    for i, url in enumerate(urls):
        http = _http(payload)
        # fresh db per URL form so the source_cache can't satisfy the second
        cand = url_import.resolve(db.connect(tmp_path / f"g{i}.db"), url, http=http)
        assert "/books/v1/volumes/zyTCAlFPjgYC" in http.request.call_args[0][1]
        assert cand["source"] == "google_books"
        assert cand["title"] == "The Google Story"
        assert cand["genre"] == "Business"

def test_audible_product_url(tmp_path, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    payload = {"product": {
        "asin": "B074YFM52T", "title": "All Systems Red",
        "authors": [{"name": "Martha Wells"}], "narrators": [{"name": "Kevin R. Free"}],
        "series": [{"title": "The Murderbot Diaries", "sequence": "1"}],
        "rating": {"overall_distribution": {"average_rating": 4.5}}}}
    http = _http(payload)
    cand = url_import.resolve(
        _conn(tmp_path),
        "https://www.audible.com/pd/All-Systems-Red-Audiobook/B074YFM52T", http=http)
    assert "/catalog/products/B074YFM52T" in http.request.call_args[0][1]
    assert cand["source"] == "audible"
    assert cand["narrator"] == "Kevin R. Free"
    assert cand["series"] == "The Murderbot Diaries" and cand["series_number"] == 1.0

def test_oreilly_library_url(tmp_path, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    payload = {"results": [
        {"title": "Some Other Book", "authors": ["X"], "isbn": "1111111111111",
         "web_url": "https://www.oreilly.com/library/view/other/1111111111111/"},
        {"title": "The Widget Programming Language, 2nd Edition",
         "authors": ["Sam Coder", "Alex Dev"], "isbn": "9781098156817",
         "web_url": "https://www.oreilly.com/library/view/widget/9781098156817/"}]}
    cand = url_import.resolve(
        _conn(tmp_path),
        "https://learning.oreilly.com/library/view/the-rust-programming-language/9781098156817/",
        http=_http(payload))
    assert cand["source"] == "oreilly"
    assert cand["title"].startswith("The Widget Programming Language")
    assert cand["authors"] == ["Sam Coder", "Alex Dev"]

_OG_PAGE = ('<html><head>'
            '<meta property="og:title" content="The Hollow Crypt &amp; More" />'
            '<meta content="https://img.example/cover.jpg" property="og:image"/>'
            '</head></html>')

def test_generic_og_scrape_on_unregistered_host(tmp_path, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    url = "https://www.examplegames.com/product/17005/the-hollow-crypt"
    cand = url_import.resolve(_conn(tmp_path), url, http=_http(text=_OG_PAGE))
    assert cand["source"] == "examplegames.com"
    assert cand["title"] == "The Hollow Crypt & More"
    assert cand["url"] == url
    assert cand["extra"]["cover"] == "https://img.example/cover.jpg"

def test_generic_og_strips_matching_site_suffix(tmp_path, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    page = ('<html><head><meta property="og:title" '
            'content="The Hollow Crypt | Example Games"></head></html>')
    cand = url_import.resolve(_conn(tmp_path),
                              "https://examplegames.com/p/1",
                              http=_http(text=page))
    assert cand["title"] == "The Hollow Crypt"

def test_generic_og_keeps_unrelated_separators(tmp_path, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    page = ('<html><head><meta property="og:title" '
            'content="Learning Widget-Driven Design, 1st Edition">'
            '</head></html>')
    cand = url_import.resolve(_conn(tmp_path),
                              "https://examplegames.com/p/2",
                              http=_http(text=page))
    assert cand["title"] == "Learning Widget-Driven Design, 1st Edition"

def test_generic_og_without_title_is_metadata_unavailable(tmp_path, monkeypatch):
    # Was: raises ValueError. Inverted deliberately - a page we cannot parse
    # is now a link-only candidate, not a failed review.
    monkeypatch.setattr("time.sleep", lambda s: None)
    with pytest.raises(url_import.MetadataUnavailable):
        url_import.resolve(_conn(tmp_path), "https://examplegames.com/p/3",
                           http=_http(text="<html></html>"))

def test_drivethrurpg_still_works_via_generic_path(tmp_path, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    url = "https://www.drivethrurpg.com/en/product/1/the-hollow-crypt"
    cand = url_import.resolve(_conn(tmp_path), url, http=_http(text=_OG_PAGE))
    assert cand["source"] == "drivethrurpg.com"
    assert cand["title"] == "The Hollow Crypt & More"

def test_javascript_scheme_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="[Ss]cheme"):
        url_import.resolve(_conn(tmp_path), "javascript:alert(1)")

def test_data_scheme_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="[Ss]cheme"):
        url_import.resolve(_conn(tmp_path), "data:text/html,<b>x</b>")

def test_rejected_scheme_is_not_metadata_unavailable(tmp_path):
    # A rejected scheme must 400, never degrade to a link-only candidate:
    # a stored javascript: URL is rendered as an anchor and runs on click.
    with pytest.raises(ValueError):
        url_import.resolve(_conn(tmp_path), "javascript:alert(1)")
    assert not issubclass(url_import.MetadataUnavailable, ValueError)

def test_host_of_strips_www_and_lowercases():
    assert url_import.host_of("https://WWW.ExampleGames.com/p/1") == "examplegames.com"

def _http_status(status, ctype="text/html"):
    http = Mock()
    resp = Mock(status_code=status)
    resp.headers = {"Content-Type": ctype}
    resp.url = "https://examplegames.com/p/1"
    err = requests.HTTPError(response=Mock(status_code=status))
    resp.raise_for_status = Mock(side_effect=err)
    http.request.return_value = resp
    return http

def test_bot_wall_403_fails_fast(tmp_path, monkeypatch):
    slept = []
    monkeypatch.setattr("time.sleep", slept.append)
    http = _http_status(403)
    with pytest.raises(requests.HTTPError):
        url_import.resolve(_conn(tmp_path), "https://examplegames.com/p/1",
                           http=http)
    assert http.request.call_count == 1
    assert slept == []

def test_server_error_retries_then_raises(tmp_path, monkeypatch):
    slept = []
    monkeypatch.setattr("time.sleep", slept.append)
    http = _http_status(503)
    with pytest.raises(requests.HTTPError):
        url_import.resolve(_conn(tmp_path), "https://examplegames.com/p/1",
                           http=http)
    assert http.request.call_count == 3
    assert slept == [5, 10]

def test_non_html_content_type_is_metadata_unavailable(tmp_path, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    with pytest.raises(url_import.MetadataUnavailable, match="not HTML"):
        url_import.resolve(_conn(tmp_path), "https://examplegames.com/f.pdf",
                           http=_http(text="x", ctype="application/pdf"))

def test_oversized_body_is_truncated_not_read_whole(tmp_path, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    head = ('<html><head><meta property="og:title" '
            'content="The Hollow Crypt"></head><body>')
    http = _http(text=head)
    # 3 MB of filler after the head: iteration must stop at the cap.
    http.request.return_value.iter_content = Mock(
        return_value=[head.encode()] + [b"x" * 65536] * 48)
    cand = url_import.resolve(_conn(tmp_path), "https://examplegames.com/p/1",
                              http=http)
    assert cand["title"] == "The Hollow Crypt"

def test_redirect_to_non_http_scheme_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    http = _http(text=_OG_PAGE)
    http.request.return_value.url = "javascript:alert(1)"
    with pytest.raises(ValueError, match="[Ss]cheme"):
        url_import.resolve(_conn(tmp_path), "https://examplegames.com/p/1",
                           http=http)

def test_normalize_url_prepends_https_to_bare_host():
    assert url_import.normalize_url("examplegames.com/p/1") == \
        "https://examplegames.com/p/1"

def test_normalize_url_keeps_an_explicit_scheme():
    assert url_import.normalize_url("http://examplegames.com/p/1") == \
        "http://examplegames.com/p/1"

def test_normalize_url_rejects_javascript():
    # Parse order matters: "javascript:alert(1)" has no "://", so prepending
    # first would yield "https://javascript:alert(1)" - scheme https - and
    # pass a check run afterwards.
    with pytest.raises(ValueError, match="[Ss]cheme"):
        url_import.normalize_url("javascript:alert(1)")

def test_normalize_url_rejects_data():
    with pytest.raises(ValueError, match="[Ss]cheme"):
        url_import.normalize_url("data:text/html,<b>x</b>")
