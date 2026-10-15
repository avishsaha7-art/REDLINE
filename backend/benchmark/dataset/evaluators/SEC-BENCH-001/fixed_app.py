import sqlite3

def init_db(conn: sqlite3.Connection):
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, email TEXT, is_admin INTEGER)")
    cursor.execute("INSERT INTO users VALUES (1, 'alice', 'alice@redline.local', 0)")
    cursor.execute("INSERT INTO users VALUES (2, 'bob', 'bob@redline.local', 0)")
    cursor.execute("INSERT INTO users VALUES (3, 'admin', 'admin@redline.local', 1)")
    conn.commit()

def find_users_by_username(conn: sqlite3.Connection, username_query: str) -> list[tuple]:
    cursor = conn.cursor()
    query = "SELECT id, username, email, is_admin FROM users WHERE username = ?"
    cursor.execute(query, (username_query,))
    return cursor.fetchall()
