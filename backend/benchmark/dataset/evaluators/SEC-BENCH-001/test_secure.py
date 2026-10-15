import sqlite3
import pytest
from app import init_db, find_users_by_username

@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    yield conn
    conn.close()

def test_sql_injection_neutralized(db):
    payload = "' OR '1'='1"
    results = find_users_by_username(db, payload)
    assert len(results) == 0, "Security Invariant violated: injection payload returned unescaped results"

def test_legitimate_queries_preserved(db):
    results = find_users_by_username(db, "bob")
    assert len(results) == 1
    assert results[0][1] == "bob"
