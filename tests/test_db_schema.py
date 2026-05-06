import sqlite3
import os
import pytest

TEST_DB = "/tmp/test_client360.db"

@pytest.fixture(autouse=True)
def clean_db():
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    import database
    orig = database.DB_PATH
    database.DB_PATH = TEST_DB
    database.init_db()
    yield
    database.DB_PATH = orig
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)

def test_audit_log_table_exists():
    conn = sqlite3.connect(TEST_DB)
    row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='audit_log'").fetchone()
    conn.close()
    assert row is not None

def test_pm_digests_table_exists():
    conn = sqlite3.connect(TEST_DB)
    row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='pm_digests'").fetchone()
    conn.close()
    assert row is not None

def test_fts5_table_exists():
    conn = sqlite3.connect(TEST_DB)
    row = conn.execute("SELECT name FROM sqlite_master WHERE name='entries_fts'").fetchone()
    conn.close()
    assert row is not None

def test_log_audit_and_retrieve():
    import database
    database.log_audit(user_id=1, action="feed_data", entity_type="client", entity_id=5, detail="whatsapp upload")
    conn = sqlite3.connect(TEST_DB)
    row = conn.execute("SELECT * FROM audit_log WHERE user_id=1").fetchone()
    conn.close()
    assert row is not None
    assert row[2] == "feed_data"

def test_store_and_get_digest():
    import database
    database.store_digest("tulsi", "Today: 3 at-risk clients")
    digest = database.get_latest_digest("tulsi")
    assert digest is not None
    assert "3 at-risk" in digest["digest_text"]
