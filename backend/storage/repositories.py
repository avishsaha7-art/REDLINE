import json
import sqlite3
import datetime
import threading
from typing import List, Optional, Dict, Any

from backend.models.schemas import TaskContract, Run, RunState, OperationalResult, PatchCandidate
from backend.models.evidence import EvidenceReceipt, JudgeExplanation
from backend.verification.models import VerificationStatus
from backend.storage.database import Database, get_database


class SQLiteRunRepository:
    """
    Authoritative SQLite repository for REDLINE run persistence and recovery.
    Enforces deterministic state and verdict separation, atomic transactions,
    and safe restart recovery.
    """
    def __init__(self, database: Optional[Database] = None):
        self.db = database or get_database()

    def save_new_run(self, run: Run) -> None:
        """
        Atomically persists a newly created Run and its initial events.
        """
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        created_at = (
            str(run.events[0].get("timestamp"))
            if run.events and "timestamp" in run.events[0]
            else now_iso
        )
        updated_at = created_at
        completed_at = None
        if run.current_state in (RunState.VERIFIED, RunState.ABORTED):
            completed_at = updated_at

        contract_json = run.task_contract.model_dump_json()
        manifest_json = json.dumps(run.evidence_manifest) if run.evidence_manifest else "{}"
        resource_status_json = json.dumps(run.resource_status) if run.resource_status else "{}"
        receipt_json = run.evidence_receipt.model_dump_json() if run.evidence_receipt else None
        judge_json = run.judge_explanation.model_dump_json() if run.judge_explanation else None
        
        patch_lineage = []
        if run.evidence_receipt and run.evidence_receipt.patch_lineage:
            patch_lineage = run.evidence_receipt.patch_lineage
        patch_lineage_json = json.dumps(patch_lineage)
        
        verdict_str = run.evidence_receipt.verdict.value if run.evidence_receipt else None
        op_res_str = run.operational_result.value if run.operational_result else None

        with self.db.connection() as conn:
            conn.execute(
                """
                INSERT INTO runs (
                    run_id, task_id, current_state, current_iteration, task_contract_json,
                    created_at, updated_at, completed_at, operational_result, operational_error,
                    evidence_manifest_json, resource_status_json, evidence_receipt_json,
                    judge_explanation_json, patch_lineage_json, verdict
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run.run_id,
                    run.task_id,
                    run.current_state.value,
                    run.current_iteration,
                    contract_json,
                    created_at,
                    updated_at,
                    completed_at,
                    op_res_str,
                    run.operational_error,
                    manifest_json,
                    resource_status_json,
                    receipt_json,
                    judge_json,
                    patch_lineage_json,
                    verdict_str
                )
            )

            # Insert initial events
            for idx, event in enumerate(run.events):
                ts = str(event.get("timestamp", now_iso))
                evt_type = str(event.get("event_type", "UNKNOWN"))
                conn.execute(
                    """
                    INSERT INTO run_events (run_id, event_index, event_type, timestamp, payload_json)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (run.run_id, idx, evt_type, ts, json.dumps(event))
                )

            # Insert initial patches if present
            for patch in run.patches:
                self._insert_patch_row(conn, run.run_id, patch)

    def update_run(self, run: Run) -> None:
        """
        Atomically updates run lifecycle state, iteration, evidence, diffs, and events.
        """
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        updated_at = (
            str(run.events[-1].get("timestamp"))
            if run.events and "timestamp" in run.events[-1]
            else now_iso
        )
        completed_at = None
        if run.current_state in (RunState.VERIFIED, RunState.ABORTED):
            completed_at = (
                str(run.events[-1].get("timestamp"))
                if run.events and "timestamp" in run.events[-1]
                else updated_at
            )

        manifest_json = json.dumps(run.evidence_manifest) if run.evidence_manifest else "{}"
        resource_status_json = json.dumps(run.resource_status) if run.resource_status else "{}"
        receipt_json = run.evidence_receipt.model_dump_json() if run.evidence_receipt else None
        judge_json = run.judge_explanation.model_dump_json() if run.judge_explanation else None
        
        patch_lineage = []
        if run.evidence_receipt and run.evidence_receipt.patch_lineage:
            patch_lineage = run.evidence_receipt.patch_lineage
        patch_lineage_json = json.dumps(patch_lineage)

        verdict_str = run.evidence_receipt.verdict.value if run.evidence_receipt else None
        op_res_str = run.operational_result.value if run.operational_result else None

        with self.db.connection() as conn:
            cur_upd = conn.execute(
                """
                UPDATE runs SET
                    current_state = ?,
                    current_iteration = ?,
                    updated_at = ?,
                    completed_at = ?,
                    operational_result = ?,
                    operational_error = ?,
                    evidence_manifest_json = ?,
                    resource_status_json = ?,
                    evidence_receipt_json = ?,
                    judge_explanation_json = ?,
                    patch_lineage_json = ?,
                    verdict = ?
                WHERE run_id = ?
                """,
                (
                    run.current_state.value,
                    run.current_iteration,
                    updated_at,
                    completed_at,
                    op_res_str,
                    run.operational_error,
                    manifest_json,
                    resource_status_json,
                    receipt_json,
                    judge_json,
                    patch_lineage_json,
                    verdict_str,
                    run.run_id
                )
            )

            # If the run was deleted (e.g. store cleared during test teardown), do not insert events
            if cur_upd.rowcount == 0:
                return

            # Append only new events
            cur = conn.execute("SELECT COUNT(*) FROM run_events WHERE run_id = ?", (run.run_id,))
            existing_event_count = cur.fetchone()[0]
            if len(run.events) > existing_event_count:
                for idx in range(existing_event_count, len(run.events)):
                    event = run.events[idx]
                    ts = str(event.get("timestamp", now_iso))
                    evt_type = str(event.get("event_type", "UNKNOWN"))
                    conn.execute(
                        """
                        INSERT INTO run_events (run_id, event_index, event_type, timestamp, payload_json)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (run.run_id, idx, evt_type, ts, json.dumps(event))
                    )

            # Synchronize patches
            cur = conn.execute("SELECT patch_id FROM run_patches WHERE run_id = ?", (run.run_id,))
            existing_patches = {row[0] for row in cur.fetchall()}
            for patch in run.patches:
                if patch.patch_id not in existing_patches:
                    self._insert_patch_row(conn, run.run_id, patch)
                    existing_patches.add(patch.patch_id)

    def _insert_patch_row(self, conn, run_id: str, patch: PatchCandidate) -> None:
        conn.execute(
            """
            INSERT INTO run_patches (
                run_id, patch_id, task_id, base_commit_or_snapshot,
                diff, diff_sha256, changed_files_json, patch_metadata_json,
                generation_provenance_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                patch.patch_id,
                patch.task_id,
                patch.base_commit_or_snapshot,
                patch.diff,
                patch.diff_sha256,
                json.dumps(patch.changed_files),
                json.dumps(patch.patch_metadata),
                json.dumps(patch.generation_provenance)
            )
        )

    def get_run(self, run_id: str) -> Optional[Run]:
        """
        Retrieves a run by ID from durable storage, reconstructing full models.
        Enforces deterministic verdict invariants (VERIFIED state requires VERIFIED receipt verdict).
        """
        with self.db.connection() as conn:
            cur = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,))
            row = cur.fetchone()
            if not row:
                return None
            return self._row_to_run(conn, row)

    def list_runs(self) -> List[Run]:
        """
        Returns all runs ordered deterministically by created_at DESC, run_id DESC.
        """
        with self.db.connection() as conn:
            cur = conn.execute("SELECT * FROM runs ORDER BY created_at DESC, run_id DESC")
            rows = cur.fetchall()
            return [self._row_to_run(conn, r) for r in rows]

    def _row_to_run(self, conn, row) -> Run:
        run_id = row["run_id"]
        task_id = row["task_id"]
        current_state = RunState(row["current_state"])
        current_iteration = row["current_iteration"]
        task_contract = TaskContract.model_validate_json(row["task_contract_json"])
        
        operational_result = (
            OperationalResult(row["operational_result"])
            if row["operational_result"]
            else None
        )
        operational_error = row["operational_error"]

        evidence_manifest = json.loads(row["evidence_manifest_json"]) if row["evidence_manifest_json"] else {}
        resource_status = json.loads(row["resource_status_json"]) if row["resource_status_json"] else {}

        evidence_receipt = (
            EvidenceReceipt.model_validate_json(row["evidence_receipt_json"])
            if row["evidence_receipt_json"]
            else None
        )
        judge_explanation = (
            JudgeExplanation.model_validate_json(row["judge_explanation_json"])
            if row["judge_explanation_json"]
            else None
        )

        # Load events
        cur_ev = conn.execute("SELECT payload_json FROM run_events WHERE run_id = ? ORDER BY event_index ASC", (run_id,))
        events = [json.loads(r[0]) for r in cur_ev.fetchall()]

        # Load patches
        cur_pa = conn.execute("SELECT * FROM run_patches WHERE run_id = ? ORDER BY id ASC", (run_id,))
        patches = []
        for p_row in cur_pa.fetchall():
            patches.append(PatchCandidate(
                patch_id=p_row["patch_id"],
                task_id=p_row["task_id"],
                base_commit_or_snapshot=p_row["base_commit_or_snapshot"],
                diff=p_row["diff"],
                changed_files=json.loads(p_row["changed_files_json"]),
                patch_metadata=json.loads(p_row["patch_metadata_json"]),
                generation_provenance=json.loads(p_row["generation_provenance_json"])
            ))

        # Enforce deterministic verdict invariant
        if current_state == RunState.VERIFIED:
            if not evidence_receipt or evidence_receipt.verdict != VerificationStatus.VERIFIED:
                current_state = RunState.ABORTED

        run = Run(
            run_id=run_id,
            task_id=task_id,
            task_contract=task_contract,
            current_state=current_state,
            events=events,
            patches=patches,
            evidence_manifest=evidence_manifest,
            operational_result=operational_result,
            operational_error=operational_error,
            current_iteration=current_iteration,
            resource_status=resource_status,
            evidence_receipt=evidence_receipt,
            judge_explanation=judge_explanation
        )
        return run

    def delete_run(self, run_id: str) -> bool:
        """Deletes a run and associated records (cascaded)."""
        with self.db.connection() as conn:
            cur = conn.execute("DELETE FROM runs WHERE run_id = ?", (run_id,))
            return cur.rowcount > 0

    def clear(self) -> None:
        """Deletes all run records (used in test teardown)."""
        with self.db.connection() as conn:
            conn.execute("DELETE FROM run_events")
            conn.execute("DELETE FROM run_patches")
            try:
                conn.execute("DELETE FROM run_artifacts")
            except sqlite3.OperationalError:
                pass
            conn.execute("DELETE FROM runs")

    def recover_interrupted_runs(self) -> int:
        """
        Scans for any in-flight runs interrupted by a process restart/crash.
        Transitions them safely to ABORTED with TOOL_FAILURE and records a terminal event.
        Guarantees that untrusted execution is NOT resumed automatically and incomplete
        runs are never falsely reported as VERIFIED.
        """
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        recovered_count = 0

        with self.db.connection() as conn:
            cur = conn.execute(
                "SELECT run_id FROM runs WHERE current_state NOT IN (?, ?)",
                (RunState.VERIFIED.value, RunState.ABORTED.value)
            )
            interrupted_ids = [r[0] for r in cur.fetchall()]

            for run_id in interrupted_ids:
                conn.execute(
                    """
                    UPDATE runs SET
                        current_state = ?,
                        operational_result = ?,
                        operational_error = ?,
                        completed_at = ?,
                        updated_at = ?
                    WHERE run_id = ?
                    """,
                    (
                        RunState.ABORTED.value,
                        OperationalResult.TOOL_FAILURE.value,
                        "PROCESS_INTERRUPTED: Backend restarted during active execution",
                        now_iso,
                        now_iso,
                        run_id
                    )
                )

                # Append terminal event
                cur_cnt = conn.execute("SELECT COUNT(*) FROM run_events WHERE run_id = ?", (run_id,))
                next_index = cur_cnt.fetchone()[0]
                abort_event = {
                    "event_type": "RUN_ABORTED",
                    "details": {
                        "reason": "Backend restarted while run was in-flight",
                        "result": OperationalResult.TOOL_FAILURE.value
                    },
                    "timestamp": now_iso
                }
                conn.execute(
                    """
                    INSERT INTO run_events (run_id, event_index, event_type, timestamp, payload_json)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (run_id, next_index, "RUN_ABORTED", now_iso, json.dumps(abort_event))
                )
                recovered_count += 1

        return recovered_count


class RunStoreProxy:
    """
    Transparent dictionary proxy bridging the existing API routes and test suites
    with the authoritative SQLiteRunRepository.
    Enforces that writes update SQLite and reads query SQLite while preserving
    in-memory references during active runs.
    """
    def __init__(self, repository: SQLiteRunRepository):
        self._repo = repository
        self._active_runs: Dict[str, Run] = {}

    def __getitem__(self, run_id: str) -> Run:
        if run_id in self._active_runs:
            return self._active_runs[run_id]
        run = self._repo.get_run(run_id)
        if run is None:
            raise KeyError(run_id)
        return run

    def __setitem__(self, run_id: str, run: Run):
        self._active_runs[run_id] = run
        existing = self._repo.get_run(run_id)
        if existing is None:
            self._repo.save_new_run(run)
        else:
            self._repo.update_run(run)

    def __delitem__(self, run_id: str):
        if run_id in self._active_runs:
            del self._active_runs[run_id]
        deleted = self._repo.delete_run(run_id)
        if not deleted:
            raise KeyError(run_id)

    def __contains__(self, run_id: str) -> bool:
        if run_id in self._active_runs:
            return True
        return self._repo.get_run(run_id) is not None

    def __len__(self) -> int:
        return len(self.values())

    def __iter__(self):
        return iter(self.keys())

    def get(self, run_id: str, default=None):
        try:
            return self[run_id]
        except KeyError:
            return default

    def keys(self) -> List[str]:
        return [r.run_id for r in self.values()]

    def items(self) -> List[tuple]:
        return [(r.run_id, r) for r in self.values()]

    def values(self) -> List[Run]:
        persisted = self._repo.list_runs()
        result = []
        seen = set()
        for p in persisted:
            run_inst = self._active_runs.get(p.run_id, p)
            result.append(run_inst)
            seen.add(p.run_id)
        for k, v in self._active_runs.items():
            if k not in seen:
                result.append(v)
        return result

    def clear(self):
        self._active_runs.clear()
        self._repo.clear()


_global_repository: Optional[SQLiteRunRepository] = None
_repo_lock = threading.Lock()

def get_run_repository(database: Optional[Database] = None) -> SQLiteRunRepository:
    """Singleton accessor for the global SQLiteRunRepository."""
    global _global_repository
    with _repo_lock:
        if database is not None:
            return SQLiteRunRepository(database=database)
        if _global_repository is None:
            _global_repository = SQLiteRunRepository()
        return _global_repository

def reset_global_repository():
    """Resets the global repository singleton."""
    global _global_repository
    with _repo_lock:
        _global_repository = None
