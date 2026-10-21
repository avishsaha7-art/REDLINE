"""
Persistent Storage and Repository for Benchmark Runs.

Manages:
- Creation, retrieval, and updates of BenchmarkRunRecords.
- Persistent recording of TaskEvaluationResults.
- Interrupted run recovery: marks incomplete runs as OPERATIONAL_FAILURE so they
  can never be mistaken for successful runs.
"""

import json
import sqlite3
import threading
from typing import Dict, Any, List, Optional
import datetime

from backend.benchmark.models import (
    BenchmarkRunRecord,
    BenchmarkRunConfig,
    BenchmarkRunState,
    TaskEvaluationResult,
    BenchmarkVerdict,
    BenchmarkArmType,
)
from backend.storage.database import Database, get_default_db_path


BENCHMARK_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS benchmark_runs (
    run_id TEXT PRIMARY KEY,
    state TEXT NOT NULL,
    config_json TEXT NOT NULL,
    integrity_result_json TEXT,
    capability_result_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    error_message TEXT
);

CREATE TABLE IF NOT EXISTS benchmark_task_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES benchmark_runs(run_id) ON DELETE CASCADE,
    task_id TEXT NOT NULL,
    arm TEXT NOT NULL,
    verdict TEXT NOT NULL,
    result_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(run_id, task_id, arm)
);

CREATE INDEX IF NOT EXISTS idx_bench_runs_created ON benchmark_runs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_bench_task_results ON benchmark_task_results(run_id, task_id);
"""


class BenchmarkRunRepository:
    """
    Thread-safe SQLite repository for BenchmarkRunRecord persistence.
    """
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or get_default_db_path()
        self._lock = threading.RLock()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA busy_timeout = 5000;")
        return conn

    def _init_db(self):
        with self._lock:
            conn = self._get_connection()
            try:
                conn.executescript(BENCHMARK_SCHEMA_SQL)
                conn.commit()
            finally:
                conn.close()

    def create_run(self, record: BenchmarkRunRecord) -> None:
        """Persists a new BenchmarkRunRecord."""
        with self._lock:
            conn = self._get_connection()
            try:
                conn.execute(
                    """
                    INSERT INTO benchmark_runs (
                        run_id, state, config_json, integrity_result_json,
                        capability_result_json, created_at, updated_at,
                        completed_at, error_message
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(run_id) DO UPDATE SET
                        state = excluded.state,
                        config_json = excluded.config_json,
                        integrity_result_json = excluded.integrity_result_json,
                        capability_result_json = excluded.capability_result_json,
                        updated_at = excluded.updated_at,
                        completed_at = excluded.completed_at,
                        error_message = excluded.error_message
                    """,
                    (
                        record.run_id,
                        record.state.value,
                        record.config.model_dump_json(),
                        json.dumps(record.integrity_result) if record.integrity_result else None,
                        json.dumps(record.capability_result) if record.capability_result else None,
                        record.created_at,
                        record.updated_at,
                        record.completed_at,
                        record.error_message,
                    )
                )
                conn.commit()
            finally:
                conn.close()

    def update_run_state(
        self,
        run_id: str,
        state: BenchmarkRunState,
        error_message: Optional[str] = None,
        integrity_result: Optional[Dict[str, Any]] = None,
        capability_result: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Updates run state, error message, and result payloads."""
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        completed_at = now if state.is_terminal else None

        with self._lock:
            conn = self._get_connection()
            try:
                conn.execute(
                    """
                    UPDATE benchmark_runs
                    SET state = ?,
                        updated_at = ?,
                        completed_at = COALESCE(completed_at, ?),
                        error_message = COALESCE(?, error_message),
                        integrity_result_json = COALESCE(?, integrity_result_json),
                        capability_result_json = COALESCE(?, capability_result_json)
                    WHERE run_id = ?
                    """,
                    (
                        state.value,
                        now,
                        completed_at,
                        error_message,
                        json.dumps(integrity_result) if integrity_result else None,
                        json.dumps(capability_result) if capability_result else None,
                        run_id,
                    )
                )
                conn.commit()
            finally:
                conn.close()

    def record_task_result(self, run_id: str, result: TaskEvaluationResult) -> None:
        """
        Records or updates a task-level evaluation result.
        Prevents overwriting stronger empirical evidence (VERIFIED/REJECTED) with OPERATIONAL_FAILURE.
        """
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self._lock:
            conn = self._get_connection()
            try:
                conn.execute(
                    """
                    INSERT INTO benchmark_task_results (
                        run_id, task_id, arm, verdict, result_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(run_id, task_id, arm) DO UPDATE SET
                        verdict = CASE
                            WHEN benchmark_task_results.verdict IN ('VERIFIED', 'REJECTED') AND excluded.verdict = 'OPERATIONAL_FAILURE'
                            THEN benchmark_task_results.verdict
                            ELSE excluded.verdict
                        END,
                        result_json = CASE
                            WHEN benchmark_task_results.verdict IN ('VERIFIED', 'REJECTED') AND excluded.verdict = 'OPERATIONAL_FAILURE'
                            THEN benchmark_task_results.result_json
                            ELSE excluded.result_json
                        END,
                        created_at = CASE
                            WHEN benchmark_task_results.verdict IN ('VERIFIED', 'REJECTED') AND excluded.verdict = 'OPERATIONAL_FAILURE'
                            THEN benchmark_task_results.created_at
                            ELSE excluded.created_at
                        END
                    """,
                    (
                        run_id,
                        result.task_id,
                        result.arm,
                        result.verdict.value,
                        result.model_dump_json(),
                        now,
                    )
                )
                conn.commit()
            finally:
                conn.close()

    def record_task_results_batch(self, run_id: str, results: List[TaskEvaluationResult]) -> None:
        """
        Atomically persists multiple TaskEvaluationResult items within a single transaction.
        Guarantees that early operational failure recording is all-or-nothing and cannot
        overwrite stronger empirical evidence (VERIFIED/REJECTED).
        """
        if not results:
            return
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self._lock:
            conn = self._get_connection()
            try:
                conn.execute("BEGIN TRANSACTION;")
                for result in results:
                    conn.execute(
                        """
                        INSERT INTO benchmark_task_results (
                            run_id, task_id, arm, verdict, result_json, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?)
                        ON CONFLICT(run_id, task_id, arm) DO UPDATE SET
                            verdict = CASE
                                WHEN benchmark_task_results.verdict IN ('VERIFIED', 'REJECTED') AND excluded.verdict = 'OPERATIONAL_FAILURE'
                                THEN benchmark_task_results.verdict
                                ELSE excluded.verdict
                            END,
                            result_json = CASE
                                WHEN benchmark_task_results.verdict IN ('VERIFIED', 'REJECTED') AND excluded.verdict = 'OPERATIONAL_FAILURE'
                                THEN benchmark_task_results.result_json
                                ELSE excluded.result_json
                            END,
                            created_at = CASE
                                WHEN benchmark_task_results.verdict IN ('VERIFIED', 'REJECTED') AND excluded.verdict = 'OPERATIONAL_FAILURE'
                                THEN benchmark_task_results.created_at
                                ELSE excluded.created_at
                            END
                        """,
                        (
                            run_id,
                            result.task_id,
                            result.arm,
                            result.verdict.value,
                            result.model_dump_json(),
                            now,
                        )
                    )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

    def get_run(self, run_id: str) -> Optional[BenchmarkRunRecord]:
        """Retrieves full BenchmarkRunRecord with all recorded task results."""
        with self._lock:
            conn = self._get_connection()
            try:
                cur = conn.execute("SELECT * FROM benchmark_runs WHERE run_id = ?", (run_id,))
                row = cur.fetchone()
                if not row:
                    return None

                config_dict = json.loads(row["config_json"])
                config = BenchmarkRunConfig(**config_dict)

                record = BenchmarkRunRecord(
                    run_id=row["run_id"],
                    config=config,
                    state=BenchmarkRunState(row["state"]),
                    integrity_result=json.loads(row["integrity_result_json"]) if row["integrity_result_json"] else None,
                    capability_result=json.loads(row["capability_result_json"]) if row["capability_result_json"] else None,
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                    completed_at=row["completed_at"],
                    error_message=row["error_message"],
                    task_results={},
                )

                # Fetch task results
                task_cur = conn.execute(
                    "SELECT * FROM benchmark_task_results WHERE run_id = ? ORDER BY task_id ASC",
                    (run_id,)
                )
                for trow in task_cur.fetchall():
                    res_dict = json.loads(trow["result_json"])
                    record.task_results[trow["task_id"]] = TaskEvaluationResult(**res_dict)

                return record
            finally:
                conn.close()

    def list_runs(self, limit: int = 50) -> List[BenchmarkRunRecord]:
        """Lists recent benchmark runs."""
        with self._lock:
            conn = self._get_connection()
            try:
                cur = conn.execute(
                    "SELECT run_id FROM benchmark_runs ORDER BY created_at DESC LIMIT ?",
                    (limit,)
                )
                run_ids = [row["run_id"] for row in cur.fetchall()]
            finally:
                conn.close()

        results = []
        for rid in run_ids:
            run = self.get_run(rid)
            if run:
                results.append(run)
        return results

    def recover_interrupted_runs(self) -> int:
        """
        Scans for active, non-terminal runs and marks them as OPERATIONAL_FAILURE.
        Guarantees that interrupted runs can never be mistaken for COMPLETED or VERIFIED.
        Returns count of recovered runs.
        """
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self._lock:
            conn = self._get_connection()
            try:
                cur = conn.execute(
                    """
                    SELECT run_id FROM benchmark_runs
                    WHERE state NOT IN (
                        'COMPLETED', 'OPERATIONAL_FAILURE', 'REJECTED',
                        'INCONCLUSIVE', 'CANCELLED', 'ABORTED'
                    )
                    """
                )
                interrupted_ids = [row["run_id"] for row in cur.fetchall()]
                if not interrupted_ids:
                    return 0

                conn.execute(
                    f"""
                    UPDATE benchmark_runs
                    SET state = 'OPERATIONAL_FAILURE',
                        error_message = 'INTERRUPTED_PROCESS_RECOVERY: Run did not reach terminal state before process termination.',
                        updated_at = ?,
                        completed_at = ?
                    WHERE run_id IN ({','.join(['?'] * len(interrupted_ids))})
                    """,
                    [now, now] + interrupted_ids
                )
                conn.commit()
                return len(interrupted_ids)
            finally:
                conn.close()


# Module-level singleton
_benchmark_repository: Optional[BenchmarkRunRepository] = None


def get_benchmark_repository() -> BenchmarkRunRepository:
    global _benchmark_repository
    if _benchmark_repository is None:
        _benchmark_repository = BenchmarkRunRepository()
    return _benchmark_repository


def set_benchmark_repository(repo: BenchmarkRunRepository) -> None:
    global _benchmark_repository
    _benchmark_repository = repo
