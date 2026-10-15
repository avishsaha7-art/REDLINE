import sqlite3
import pytest
from app import init_db, find_users_by_username

@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    yield conn
    conn.close()

def test_find_existing_user(db):
    results = find_users_by_username(db, "alice")
    assert len(results) == 1
    assert results[0][1] == "alice"

def test_find_nonexistent_user(db):
    results = find_users_by_username(db, "charlie")
    assert len(results) == 0
