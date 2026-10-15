import os
import sqlite3
import threading
from contextlib import contextmanager
from typing import Optional

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    current_state TEXT NOT NULL,
    current_iteration INTEGER NOT NULL DEFAULT 0,
    task_contract_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    operational_result TEXT,
    operational_error TEXT,
    evidence_manifest_json TEXT,
    resource_status_json TEXT,
    evidence_receipt_json TEXT,
    judge_explanation_json TEXT,
    patch_lineage_json TEXT,
    verdict TEXT
);

CREATE TABLE IF NOT EXISTS run_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    event_index INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    payload_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS run_patches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    patch_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    base_commit_or_snapshot TEXT NOT NULL,
    diff TEXT NOT NULL,
    diff_sha256 TEXT NOT NULL,
    changed_files_json TEXT NOT NULL,
    patch_metadata_json TEXT NOT NULL,
    generation_provenance_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS run_artifacts (
    artifact_id TEXT NOT NULL,
    run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    artifact_type TEXT NOT NULL,
    media_type TEXT NOT NULL,
    storage_path TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    sha256 TEXT NOT NULL,
    created_at TEXT NOT NULL,
    lineage_ref TEXT,
    metadata_json TEXT,
    PRIMARY KEY (run_id, artifact_id)
);

CREATE INDEX IF NOT EXISTS idx_runs_created_at ON runs(created_at DESC, run_id DESC);
CREATE INDEX IF NOT EXISTS idx_runs_task_id ON runs(task_id);
CREATE INDEX IF NOT EXISTS idx_run_events_run_id_seq ON run_events(run_id, event_index ASC);
CREATE INDEX IF NOT EXISTS idx_run_patches_run_id ON run_patches(run_id);
CREATE INDEX IF NOT EXISTS idx_run_artifacts_run_id ON run_artifacts(run_id);
CREATE INDEX IF NOT EXISTS idx_run_artifacts_created_at ON run_artifacts(created_at DESC);
"""

def get_default_db_path() -> str:
    """
    Returns the resolved database path.
    Honors REDLINE_DB_PATH if set; defaults to 'data/redline.db' within the repo root.
    """
    env_path = os.environ.get("REDLINE_DB_PATH")
    if env_path:
        return env_path
    
    # Resolve relative to repo root
    repo_root = os.environ.get("REDLINE_REPO_ROOT")
    if not repo_root:
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    return os.path.join(repo_root, "data", "redline.db")


class Database:
    """
    Manages SQLite database initialization, pragmas, and transactional connections.
    Supports file-based WAL databases and in-memory test databases.
    """
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or get_default_db_path()
        self._lock = threading.RLock()
        self._memory_conn: Optional[sqlite3.Connection] = None
        self._initialize()

    def _configure_connection(self, conn: sqlite3.Connection):
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA busy_timeout = 5000;")
        if self.db_path != ":memory:":
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA synchronous = NORMAL;")

    def _initialize(self):
        if self.db_path != ":memory:":
            parent_dir = os.path.dirname(os.path.abspath(self.db_path))
            if parent_dir and not os.path.exists(parent_dir):
                os.makedirs(parent_dir, exist_ok=True)
            with self.connection() as conn:
                conn.executescript(SCHEMA_SQL)
        else:
            with self._lock:
                if self._memory_conn is None:
                    self._memory_conn = sqlite3.connect(":memory:", check_same_thread=False)
                    self._configure_connection(self._memory_conn)
                    self._memory_conn.executescript(SCHEMA_SQL)

    @contextmanager
    def connection(self):
        """
        Yields an open, configured sqlite3 connection.
        Commits automatically on clean exit, rolls back on exception.
        """
        if self.db_path == ":memory:":
            with self._lock:
                try:
                    yield self._memory_conn
                    self._memory_conn.commit()
                except Exception:
                    self._memory_conn.rollback()
                    raise
        else:
            conn = sqlite3.connect(self.db_path, timeout=10.0, check_same_thread=False)
            self._configure_connection(conn)
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

    def close(self):
        """Closes any persistent memory connection."""
        with self._lock:
            if self._memory_conn is not None:
                self._memory_conn.close()
                self._memory_conn = None


_global_database: Optional[Database] = None
_db_lock = threading.Lock()

def get_database(db_path: Optional[str] = None) -> Database:
    """
    Singleton accessor for the global Database instance.
    If a specific db_path is requested, creates or returns that instance.
    """
    global _global_database
    with _db_lock:
        if db_path is not None:
            return Database(db_path=db_path)
        if _global_database is None:
            _global_database = Database()
        return _global_database

def reset_global_database():
    """Resets the global Database singleton (used in test teardown)."""
    global _global_database
    with _db_lock:
        if _global_database is not None:
            _global_database.close()
            _global_database = None
