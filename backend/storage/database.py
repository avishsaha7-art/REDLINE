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
CREATE UNIQUE INDEX IF NOT EXISTS uidx_run_artifacts_run_art ON run_artifacts(run_id, artifact_id);

CREATE TABLE IF NOT EXISTS projects (
    project_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    root_path TEXT NOT NULL,
    trust TEXT NOT NULL,
    snapshot_hash TEXT NOT NULL,
    file_manifest_hash TEXT NOT NULL,
    file_count INTEGER NOT NULL DEFAULT 0,
    total_bytes INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS project_conversations (
    conversation_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS project_messages (
    message_id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES project_conversations(conversation_id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    mentioned_files_json TEXT NOT NULL DEFAULT '[]',
    proposal_id TEXT,
    timestamp TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS project_proposals (
    proposal_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    conversation_id TEXT,
    status TEXT NOT NULL,
    description TEXT NOT NULL,
    diff TEXT NOT NULL,
    diff_sha256 TEXT NOT NULL,
    changed_files_json TEXT NOT NULL,
    proposed_content_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    resolved_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_projects_created_at ON projects(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_project_conversations_proj_id ON project_conversations(project_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_project_messages_conv_id ON project_messages(conversation_id, timestamp ASC);
CREATE INDEX IF NOT EXISTS idx_project_proposals_proj_id ON project_proposals(project_id, created_at DESC);
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

    def _migrate_schema(self, conn: sqlite3.Connection):
        """
        Backward-compatible schema migration.
        Ensures run_artifacts has composite PRIMARY KEY (run_id, artifact_id)
        and matching UNIQUE index for ON CONFLICT(run_id, artifact_id).
        Preserves all existing data.
        """
        cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='run_artifacts'")
        if not cur.fetchone():
            return

        cols = conn.execute("PRAGMA table_info(run_artifacts)").fetchall()
        pk_cols = [c[1] for c in cols if c[5] > 0]
        if "run_id" not in pk_cols or len(pk_cols) < 2:
            # Table has legacy single-column primary key (artifact_id).
            # Migrate to composite primary key (run_id, artifact_id) preserving all data.
            conn.execute("ALTER TABLE run_artifacts RENAME TO _run_artifacts_legacy")
            conn.execute("""
                CREATE TABLE run_artifacts (
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
                )
            """)
            conn.execute("""
                INSERT OR IGNORE INTO run_artifacts (
                    artifact_id, run_id, artifact_type, media_type, storage_path,
                    size_bytes, sha256, created_at, lineage_ref, metadata_json
                )
                SELECT
                    artifact_id, run_id, artifact_type, media_type, storage_path,
                    size_bytes, sha256, created_at, lineage_ref, metadata_json
                FROM _run_artifacts_legacy
            """)
            conn.execute("DROP TABLE _run_artifacts_legacy")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_run_artifacts_run_id ON run_artifacts(run_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_run_artifacts_created_at ON run_artifacts(created_at DESC)")
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS uidx_run_artifacts_run_art ON run_artifacts(run_id, artifact_id)")

    def _initialize(self):
        if self.db_path != ":memory:":
            parent_dir = os.path.dirname(os.path.abspath(self.db_path))
            if parent_dir and not os.path.exists(parent_dir):
                os.makedirs(parent_dir, exist_ok=True)
            with self.connection() as conn:
                conn.executescript(SCHEMA_SQL)
                self._migrate_schema(conn)
        else:
            with self._lock:
                if self._memory_conn is None:
                    self._memory_conn = sqlite3.connect(":memory:", check_same_thread=False)
                    self._configure_connection(self._memory_conn)
                    self._memory_conn.executescript(SCHEMA_SQL)
                    self._migrate_schema(self._memory_conn)

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

def set_database(database: Optional[Database]) -> None:
    """Sets or overrides the global Database singleton."""
    global _global_database
    with _db_lock:
        _global_database = database

def reset_global_database():
    """Resets the global Database singleton (used in test teardown)."""
    global _global_database
    with _db_lock:
        if _global_database is not None:
            _global_database.close()
            _global_database = None
