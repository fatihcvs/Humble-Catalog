from humble_catalog import db, failures

def test_a_first_failure_starts_the_count(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    failures.record(conn, "google_books", "Learn C#", "503 backendFailed")
    row = conn.execute("SELECT * FROM source_failure").fetchone()
    assert row["source"] == "google_books"
    assert row["title"] == "Learn C#"
    assert row["failures"] == 1
    assert row["first_failed_at"] == row["last_failed_at"]
    assert row["last_error"] == "503 backendFailed"

def test_recording_the_same_title_again_increments_and_keeps_the_first_time(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    failures.record(conn, "google_books", "Learn C#", "503 one")
    first = conn.execute("SELECT first_failed_at FROM source_failure").fetchone()[0]
    failures.record(conn, "google_books", "Learn C#", "503 two")
    row = conn.execute("SELECT * FROM source_failure").fetchone()
    assert row["failures"] == 2
    assert row["first_failed_at"] == first     # the first time never moves
    assert row["last_failed_at"] >= first      # the last time does
    assert row["last_error"] == "503 two"      # newest error wins

def test_the_same_title_under_two_sources_is_two_rows(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    failures.record(conn, "google_books", "Moonfall Vol. 1-3", "a")
    failures.record(conn, "comicvine", "Moonfall Vol. 1-3", "b")
    assert conn.execute("SELECT COUNT(*) FROM source_failure").fetchone()[0] == 2

def test_top_orders_most_persistent_first(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    failures.record(conn, "google_books", "Gray Waters", "a")
    for _ in range(3):
        failures.record(conn, "google_books", "Shadow Hound Vol. 1-6", "b")
    rows = failures.top(conn)
    assert [r["title"] for r in rows] == ["Shadow Hound Vol. 1-6", "Gray Waters"]

def test_top_can_exclude_one_off_failures(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    failures.record(conn, "google_books", "Gray Waters", "a")
    failures.record(conn, "google_books", "Learn C#", "b")
    failures.record(conn, "google_books", "Learn C#", "b")
    rows = failures.top(conn, min_failures=2)
    assert [r["title"] for r in rows] == ["Learn C#"]

def test_error_kind_drops_the_url_so_titles_group_together():
    # The URL carries the title, so without this every stored error is
    # unique and a tally reports one of everything - no information.
    a = failures.error_kind(
        "503 Server Error: Service Unavailable for url: https://x/?q=Learn+C%23")
    b = failures.error_kind(
        "503 Server Error: Service Unavailable for url: https://x/?q=Gray+Waters")
    assert a == b == "503 Server Error: Service Unavailable"

def test_error_kind_passes_through_an_error_with_no_url():
    assert failures.error_kind("Connection aborted") == "Connection aborted"

def test_count_since_counts_titles_that_failed_in_the_window(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    failures.record(conn, "google_books", "Gray Waters", "a")
    mark = conn.execute(
        "SELECT last_failed_at FROM source_failure").fetchone()[0]
    failures.record(conn, "google_books", "Learn C#", "b")
    assert failures.count_since(conn, "google_books", mark) == 2
    assert failures.count_since(conn, "google_books", "2099-01-01T00:00:00+00:00") == 0
    assert failures.count_since(conn, "comicvine", mark) == 0
