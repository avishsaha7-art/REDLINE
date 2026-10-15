import os
import re
import json
import threading
import uuid
import datetime
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

from backend.models.schemas import TaskContract, Run, RunState, OperationalResult, ResourceBudget, PatchCandidate
from backend.models.evidence import EvidenceReceipt, JudgeExplanation
from backend.verification.models import VerificationStatus
from backend.orchestrator.orchestrator import Orchestrator

router = APIRouter()

# System ceiling resource budget caps to prevent clients from inflating limits
MAX_ALLOWED_ITERATIONS = 50
MAX_ALLOWED_RUNTIME = 3600
MAX_ALLOWED_PATCH_SIZE = 1024 * 1024
MAX_ALLOWED_TOOL_CALLS = 100
MAX_ALLOWED_FAILED_ATTEMPTS = 5
MAX_ALLOWED_ATTACK_CASES = 20
MAX_ALLOWED_FILE_SIZE = 1024 * 1024
MAX_ALLOWED_REPO_FILES = 1000
MAX_ALLOWED_REPO_BYTES = 50 * 1024 * 1024
MAX_ALLOWED_CONTEXT_BYTES = 128 * 1024

def enforce_resource_budget_limits(budget: ResourceBudget) -> ResourceBudget:
    return ResourceBudget(
        max_iterations=min(budget.max_iterations, MAX_ALLOWED_ITERATIONS),
        max_runtime=min(budget.max_runtime, MAX_ALLOWED_RUNTIME),
        max_patch_size=min(budget.max_patch_size, MAX_ALLOWED_PATCH_SIZE),
        max_tool_calls=min(budget.max_tool_calls, MAX_ALLOWED_TOOL_CALLS),
        max_failed_attempts=min(budget.max_failed_attempts, MAX_ALLOWED_FAILED_ATTEMPTS),
        max_attack_cases=min(budget.max_attack_cases, MAX_ALLOWED_ATTACK_CASES),
        max_file_size=min(budget.max_file_size, MAX_ALLOWED_FILE_SIZE),
        max_repo_files=min(budget.max_repo_files, MAX_ALLOWED_REPO_FILES),
        max_repo_bytes=min(budget.max_repo_bytes, MAX_ALLOWED_REPO_BYTES),
        max_context_bytes=min(budget.max_context_bytes, MAX_ALLOWED_CONTEXT_BYTES),
    )

# Pydantic response models
class CreateRunResponse(BaseModel):
    run_id: str

class ResourceStatusResponse(BaseModel):
    iterations_used: int = 0
    iterations_limit: int = 20
    tool_calls_used: int = 0
    tool_calls_limit: int = 100

class RunStatusResponse(BaseModel):
    run_id: str
    task_id: str
    state: RunState
    status: str  # "active", "completed", "failed"
    iteration: int = 0
    resource_status: ResourceStatusResponse
    started_at: str = ""
    updated_at: str = ""
    patch_candidate: Optional[PatchCandidate] = None
    patch_lineage: List[str] = Field(default_factory=list)
    evidence_receipt: Optional[EvidenceReceipt] = None
    judge_explanation: Optional[JudgeExplanation] = None
    operational_result: Optional[OperationalResult] = None
    operational_error: Optional[str] = None

class RunHistoryItemResponse(BaseModel):
    run_id: str
    task_id: str
    final_state: RunState
    verdict: Optional[VerificationStatus] = None
    created_at: str = ""
    completed_at: Optional[str] = None

class RunDiffResponse(BaseModel):
    run_id: str
    patch_id: Optional[str] = None
    diff: Optional[str] = None
    changed_files: List[str] = Field(default_factory=list)

class ArtifactItemResponse(BaseModel):
    artifact_id: str
    run_id: str
    artifact_type: str
    media_type: str
    size_bytes: int
    sha256: str
    created_at: str
    lineage_ref: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

# Persistent SQLite repository, artifact storage, and transparent compatibility proxy
from backend.storage.repositories import SQLiteRunRepository, RunStoreProxy, get_run_repository
from backend.storage.artifacts import (
    ArtifactStorage,
    get_artifact_storage,
    ArtifactMetadata,
    ArtifactNotFoundError,
    ArtifactIntegrityError,
    ArtifactPathTraversalError,
    ArtifactSizeLimitError
)

_repository: SQLiteRunRepository = get_run_repository()
_repository.recover_interrupted_runs()
_runs: RunStoreProxy = RunStoreProxy(_repository)
_artifact_storage: ArtifactStorage = get_artifact_storage()
_orchestrators: Dict[str, Orchestrator] = {}
_threads: Dict[str, threading.Thread] = {}
_default_model_provider = None

def get_repository() -> SQLiteRunRepository:
    return _repository

def set_run_repository(repo: SQLiteRunRepository):
    global _repository, _runs
    _repository = repo
    _runs = RunStoreProxy(_repository)

def get_artifact_storage_instance() -> ArtifactStorage:
    return _artifact_storage

def set_artifact_storage(storage: ArtifactStorage):
    global _artifact_storage
    _artifact_storage = storage

def set_model_provider(provider):
    global _default_model_provider
    _default_model_provider = provider

def get_model_provider():
    global _default_model_provider
    if _default_model_provider is not None:
        return _default_model_provider
    if os.environ.get("NEBIUS_API_KEY"):
        from backend.models.nebius_provider import NebiusProvider
        return NebiusProvider()
    from backend.models.deterministic_provider import DeterministicTestProvider
    return DeterministicTestProvider()

def reset_run_store():
    _runs.clear()
    _artifact_storage.clear()
    _orchestrators.clear()
    _threads.clear()

def get_run(run_id: str) -> Run:
    if run_id not in _runs:
        raise HTTPException(status_code=404, detail="Run not found")
    return _runs[run_id]

def _persist_run_artifacts(run: Run):
    """
    Persists applicable execution artifacts (diffs, receipt, reports, logs)
    durably to the artifact storage layer.
    """
    import logging
    logger = logging.getLogger("redline.storage")

    # 1. Patch diff artifacts
    for patch in (run.patches or []):
        try:
            _artifact_storage.store_artifact(
                run_id=run.run_id,
                artifact_id=f"diff-{patch.patch_id}.diff",
                artifact_type="diff",
                content=patch.diff,
                media_type="text/x-diff",
                lineage_ref=patch.patch_id,
                metadata={
                    "task_id": patch.task_id,
                    "base_commit_or_snapshot": patch.base_commit_or_snapshot,
                    "changed_files": patch.changed_files
                }
            )
        except Exception as exc:
            logger.warning(f"Failed to persist patch diff artifact for run {run.run_id}: {exc}")

    # 2. Evidence Receipt artifact
    if run.evidence_receipt:
        rec = run.evidence_receipt
        try:
            rec_content = rec.model_dump_json(indent=2) if hasattr(rec, "model_dump_json") else json.dumps(rec, indent=2)
            verdict_val = rec.verdict.value if hasattr(getattr(rec, "verdict", None), "value") else str(getattr(rec, "verdict", "UNKNOWN"))
            _artifact_storage.store_artifact(
                run_id=run.run_id,
                artifact_id=f"receipt-{run.run_id}.json",
                artifact_type="receipt",
                content=rec_content,
                media_type="application/json",
                lineage_ref=getattr(rec, "receipt_hash", None),
                metadata={
                    "verdict": verdict_val,
                    "policy_version": getattr(rec, "policy_version", "1.0"),
                    "verifier_version": getattr(rec, "verifier_version", "1.0")
                }
            )
        except Exception as exc:
            logger.warning(f"Failed to persist receipt artifact for run {run.run_id}: {exc}")

        # 3. Test summary report
        if getattr(rec, "test_summary", None):
            try:
                ts = rec.test_summary
                ts_content = ts.model_dump_json(indent=2) if hasattr(ts, "model_dump_json") else json.dumps(ts, indent=2)
                _artifact_storage.store_artifact(
                    run_id=run.run_id,
                    artifact_id=f"test-report-{run.run_id}.json",
                    artifact_type="test_report",
                    content=ts_content,
                    media_type="application/json",
                    lineage_ref=getattr(rec, "receipt_hash", None),
                    metadata={
                        "executed": getattr(ts, "executed", 0),
                        "passed": getattr(ts, "passed", 0),
                        "failed": getattr(ts, "failed", 0)
                    }
                )
            except Exception as exc:
                logger.warning(f"Failed to persist test report artifact for run {run.run_id}: {exc}")

        # 4. Security summary report
        if getattr(rec, "security_summary", None):
            try:
                sec_obs = rec.security_summary
                sec_list = [s.model_dump() if hasattr(s, "model_dump") else s for s in sec_obs]
                _artifact_storage.store_artifact(
                    run_id=run.run_id,
                    artifact_id=f"security-report-{run.run_id}.json",
                    artifact_type="security_report",
                    content=json.dumps(sec_list, indent=2),
                    media_type="application/json",
                    lineage_ref=getattr(rec, "receipt_hash", None),
                    metadata={"findings_count": len(sec_list)}
                )
            except Exception as exc:
                logger.warning(f"Failed to persist security report artifact for run {run.run_id}: {exc}")

    # 5. Judge explanation artifact
    if run.judge_explanation:
        try:
            je = run.judge_explanation
            je_content = je.model_dump_json(indent=2) if hasattr(je, "model_dump_json") else json.dumps(je, indent=2)
            _artifact_storage.store_artifact(
                run_id=run.run_id,
                artifact_id=f"judge-explanation-{run.run_id}.json",
                artifact_type="judge_explanation",
                content=je_content,
                media_type="application/json",
                metadata={"confidence": getattr(je, "confidence", 1.0)}
            )
        except Exception as exc:
            logger.warning(f"Failed to persist judge explanation artifact for run {run.run_id}: {exc}")

    # 6. Execution events log artifact
    if run.events:
        try:
            _artifact_storage.store_artifact(
                run_id=run.run_id,
                artifact_id=f"execution-log-{run.run_id}.json",
                artifact_type="log",
                content=json.dumps(run.events, indent=2),
                media_type="application/json",
                metadata={"event_count": len(run.events)}
            )
        except Exception as exc:
            logger.warning(f"Failed to persist execution log artifact for run {run.run_id}: {exc}")

def execute_run(run_id: str):
    """
    Background worker executing the authoritative Orchestrator.
    Captures final state, receipt, judge explanation, or operational failures.
    NEVER silently swallows exceptions.
    Durably updates persistent storage and artifact files upon completion or abort.
    """
    orchestrator = _orchestrators.get(run_id)
    run = _runs.get(run_id)
    if not orchestrator or not run:
        return

    try:
        final_state = orchestrator.run()
        run.current_state = orchestrator.state_machine.current_state
        run.events = orchestrator.state_machine.events.get_events()
        
        if getattr(orchestrator, "patch_candidate", None):
            run.patches = [orchestrator.patch_candidate]
            
        receipt = getattr(orchestrator, "evidence_receipt", None)
        if receipt:
            run.evidence_receipt = receipt
            run.evidence_manifest = receipt.model_dump()
            
        judge = getattr(orchestrator, "judge_explanation", None)
        if judge:
            run.judge_explanation = judge
            
        run.current_iteration = orchestrator.state_machine.governance.iteration_count
        
        # Invariant: VERIFIED lifecycle state requires authoritative VERIFIED receipt verdict
        if run.current_state == RunState.VERIFIED:
            if not run.evidence_receipt or run.evidence_receipt.verdict != VerificationStatus.VERIFIED:
                run.current_state = RunState.ABORTED
        
        # Check if the run aborted during execution
        if run.current_state == RunState.ABORTED:
            for event in reversed(run.events):
                if event.get("event_type") in ("PATCH_POLICY_REJECTED", "REPAIR_POLICY_REJECTED", "ATTACK_VALIDATION_FAILED"):
                    details = event.get("details", {}) or event.get("payload", {})
                    reason = details.get("reason")
                    if reason:
                        run.operational_error = reason
                        break
                elif event.get("event_type") == "RUN_ABORTED":
                    details = event.get("details", {}) or event.get("payload", {})
                    if not run.operational_error:
                        run.operational_error = details.get("reason")
                    res = details.get("result")
                    if res and not run.operational_result:
                        try:
                            run.operational_result = OperationalResult(res)
                        except ValueError:
                            pass
        _persist_run_artifacts(run)
        _repository.update_run(run)
    except Exception as exc:
        # An exception must never silently disappear.
        run.current_state = RunState.ABORTED
        run.operational_error = str(exc)
        run.operational_result = OperationalResult.TOOL_FAILURE
        if hasattr(orchestrator, "state_machine") and hasattr(orchestrator.state_machine, "events"):
            orchestrator.state_machine.events.record_event("RUN_ABORTED", {
                "result": OperationalResult.TOOL_FAILURE.value,
                "reason": str(exc)
            })
            run.events = orchestrator.state_machine.events.get_events()
        _persist_run_artifacts(run)
        _repository.update_run(run)


@router.post("", response_model=CreateRunResponse, status_code=201)
async def create_run(contract: TaskContract):
    """
    Creates a new REDLINE run from a validated TaskContract.
    Backend remains authoritative: enforce resource budget caps,
    initialize run at INIT, and execute authoritative Orchestrator.
    """
    run_id = f"run-{uuid.uuid4().hex[:8]}"
    
    # Enforce authoritative backend policy on resource limits and trust
    from backend.sandbox.trust import resolve_repository_trust
    authoritative_budget = enforce_resource_budget_limits(contract.resource_budget)
    authoritative_trust = resolve_repository_trust(contract.repository_id, contract.repository_trust)
    authoritative_contract = contract.model_copy(update={
        "resource_budget": authoritative_budget,
        "repository_trust": authoritative_trust.value
    })
    
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    init_event = {"event_type": "RUN_CREATED", "details": {"task_id": authoritative_contract.task_id}, "timestamp": now_iso}
    
    run = Run(
        run_id=run_id,
        task_id=authoritative_contract.task_id,
        task_contract=authoritative_contract,
        current_state=RunState.INIT,
        events=[init_event]
    )
    _runs[run_id] = run
    
    provider = get_model_provider()
    orchestrator = Orchestrator(run_id=run_id, task_contract=authoritative_contract, model_provider=provider)
    _orchestrators[run_id] = orchestrator
    
    # Execute asynchronously in background thread
    t = threading.Thread(target=execute_run, args=(run_id,), daemon=True)
    _threads[run_id] = t
    t.start()
    
    return CreateRunResponse(run_id=run_id)

@router.get("/{run_id}", response_model=RunStatusResponse)
async def get_run_status(run_id: str):
    """
    Returns authoritative run status.
    """
    run = get_run(run_id)
    orchestrator = _orchestrators.get(run_id)
    
    # Sync progress from orchestrator
    if orchestrator:
        run.current_state = orchestrator.state_machine.current_state
        run.events = orchestrator.state_machine.events.get_events()
        run.current_iteration = orchestrator.state_machine.governance.iteration_count
        if getattr(orchestrator, "evidence_receipt", None):
            run.evidence_receipt = orchestrator.evidence_receipt
        if getattr(orchestrator, "judge_explanation", None):
            run.judge_explanation = orchestrator.judge_explanation
        _repository.update_run(run)
            
    # Invariant: VERIFIED lifecycle state requires authoritative VERIFIED receipt verdict
    if run.current_state == RunState.VERIFIED:
        if not run.evidence_receipt or run.evidence_receipt.verdict != VerificationStatus.VERIFIED:
            run.current_state = RunState.ABORTED
            
    if run.current_state == RunState.ABORTED:
        for event in reversed(run.events):
            if event.get("event_type") in ("PATCH_POLICY_REJECTED", "REPAIR_POLICY_REJECTED", "ATTACK_VALIDATION_FAILED"):
                details = event.get("details", {}) or event.get("payload", {})
                reason = details.get("reason")
                if reason:
                    run.operational_error = reason
                    break
            elif event.get("event_type") == "RUN_ABORTED":
                details = event.get("details", {}) or event.get("payload", {})
                if not run.operational_error:
                    run.operational_error = details.get("reason")
                res = details.get("result")
                if res and not run.operational_result:
                    try:
                        run.operational_result = OperationalResult(res)
                    except ValueError:
                        pass
    
    worker_t = _threads.get(run_id)
    is_worker_alive = worker_t.is_alive() if worker_t else False

    if is_worker_alive:
        status_str = "active"
    else:
        status_str = "completed" if run.current_state == RunState.VERIFIED else (
            "failed" if run.current_state == RunState.ABORTED else "active"
        )
    
    iterations_used = run.current_iteration
    if orchestrator:
        iterations_used = orchestrator.state_machine.governance.iteration_count
    
    tool_calls_used = orchestrator.state_machine.governance.tool_call_count if orchestrator else 0
    
    started_at = str(run.events[0].get("timestamp", "")) if run.events and "timestamp" in run.events[0] else ""
    updated_at = str(run.events[-1].get("timestamp", "")) if run.events and "timestamp" in run.events[-1] else ""
    
    patch_lineage = []
    if run.evidence_receipt and run.evidence_receipt.patch_lineage:
        patch_lineage = run.evidence_receipt.patch_lineage
    elif orchestrator and getattr(orchestrator, "patch_lineage", None):
        patch_lineage = orchestrator.patch_lineage
        
    patch_cand = orchestrator.patch_candidate if orchestrator and getattr(orchestrator, "patch_candidate", None) else None
    
    return RunStatusResponse(
        run_id=run.run_id,
        task_id=run.task_id,
        state=run.current_state,
        status=status_str,
        iteration=iterations_used,
        resource_status=ResourceStatusResponse(
            iterations_used=iterations_used,
            iterations_limit=run.task_contract.resource_budget.max_iterations,
            tool_calls_used=tool_calls_used,
            tool_calls_limit=run.task_contract.resource_budget.max_tool_calls
        ),
        started_at=started_at,
        updated_at=updated_at,
        patch_candidate=patch_cand,
        patch_lineage=patch_lineage,
        evidence_receipt=run.evidence_receipt,
        judge_explanation=run.judge_explanation,
        operational_result=run.operational_result,
        operational_error=run.operational_error
    )

@router.get("/{run_id}/receipt", response_model=EvidenceReceipt)
async def get_run_receipt(run_id: str):
    """
    Returns authoritative EvidenceReceipt.
    Returns 404 if run does not exist or verification has not completed a receipt.
    """
    run = get_run(run_id)
    if not run.evidence_receipt:
        raise HTTPException(status_code=404, detail="Evidence receipt not available")
    return run.evidence_receipt

@router.get("/{run_id}/judge", response_model=JudgeExplanation)
async def get_run_judge(run_id: str):
    """
    Returns authoritative JudgeExplanation.
    Returns 404 if run does not exist or Judge has not executed.
    """
    run = get_run(run_id)
    if not run.judge_explanation:
        raise HTTPException(status_code=404, detail="Judge explanation not available")
    return run.judge_explanation

@router.get("/{run_id}/diff", response_model=RunDiffResponse)
async def get_run_diff(run_id: str):
    """
    Returns authoritative patch diff and changed files for a run.
    Returns 404 if run does not exist or patch candidate has not been generated.
    """
    run = get_run(run_id)
    orchestrator = _orchestrators.get(run_id)
    patch = None
    if orchestrator and getattr(orchestrator, "patch_candidate", None):
        patch = orchestrator.patch_candidate
    elif run.patches:
        patch = run.patches[-1]
        
    if not patch:
        raise HTTPException(status_code=404, detail="Patch diff not available")
        
    return RunDiffResponse(
        run_id=run.run_id,
        patch_id=patch.patch_id,
        diff=patch.diff,
        changed_files=patch.changed_files
    )

@router.get("", response_model=List[RunHistoryItemResponse])
async def list_runs():
    """
    Returns run history.
    """
    items = []
    for run in _runs.values():
        created_at = str(run.events[0].get("timestamp", "")) if run.events and "timestamp" in run.events[0] else ""
        completed_at = str(run.events[-1].get("timestamp", "")) if run.current_state in (RunState.VERIFIED, RunState.ABORTED) and run.events and "timestamp" in run.events[-1] else None
        verdict = run.evidence_receipt.verdict if run.evidence_receipt else None
        
        # Invariant: VERIFIED lifecycle state requires authoritative VERIFIED receipt verdict
        effective_state = run.current_state
        if effective_state == RunState.VERIFIED and verdict != VerificationStatus.VERIFIED:
            effective_state = RunState.ABORTED
            
        items.append(RunHistoryItemResponse(
            run_id=run.run_id,
            task_id=run.task_id,
            final_state=effective_state,
            verdict=verdict,
            created_at=created_at,
            completed_at=completed_at
        ))
    return items

@router.get("/{run_id}/artifacts", response_model=List[ArtifactItemResponse])
async def list_run_artifacts(run_id: str):
    """
    Returns list of stored artifacts for a run.
    """
    get_run(run_id)
    try:
        artifacts = _artifact_storage.list_artifacts(run_id)
        return [
            ArtifactItemResponse(
                artifact_id=a.artifact_id,
                run_id=a.run_id,
                artifact_type=a.artifact_type,
                media_type=a.media_type,
                size_bytes=a.size_bytes,
                sha256=a.sha256,
                created_at=a.created_at,
                lineage_ref=a.lineage_ref,
                metadata=a.metadata
            )
            for a in artifacts
        ]
    except ArtifactPathTraversalError:
        raise HTTPException(status_code=400, detail="Invalid run identifier")

@router.get("/{run_id}/artifacts/{artifact_id}", response_model=ArtifactItemResponse)
async def get_artifact_metadata_endpoint(run_id: str, artifact_id: str):
    """
    Returns metadata for a specific artifact.
    """
    get_run(run_id)
    try:
        a = _artifact_storage.get_artifact_metadata(run_id, artifact_id)
        return ArtifactItemResponse(
            artifact_id=a.artifact_id,
            run_id=a.run_id,
            artifact_type=a.artifact_type,
            media_type=a.media_type,
            size_bytes=a.size_bytes,
            sha256=a.sha256,
            created_at=a.created_at,
            lineage_ref=a.lineage_ref,
            metadata=a.metadata
        )
    except ArtifactNotFoundError:
        raise HTTPException(status_code=404, detail="Artifact not found")
    except ArtifactPathTraversalError:
        raise HTTPException(status_code=400, detail="Invalid artifact identifier")

def sanitize_attachment_filename(filename: str) -> str:
    """
    Sanitizes a filename for Content-Disposition header.
    Strictly removes CRLF, quotes, path delimiters, and control characters to prevent header injection.
    """
    if not filename or not isinstance(filename, str):
        return "artifact.bin"
    base = os.path.basename(filename)
    safe = re.sub(r"[^a-zA-Z0-9_\.\-]", "_", base)
    safe = safe.strip("._-")
    return safe or "artifact.bin"

@router.get("/{run_id}/artifacts/{artifact_id}/content")
async def get_artifact_content_endpoint(run_id: str, artifact_id: str):
    """
    Returns raw artifact content with integrity verification and media type.
    Hardened with X-Content-Type-Options: nosniff and Content-Disposition: attachment.
    """
    get_run(run_id)
    try:
        content_bytes, meta = _artifact_storage.get_artifact_content(run_id, artifact_id, verify_integrity=True)
        safe_filename = sanitize_attachment_filename(meta.artifact_id)
        safe_art_id = re.sub(r"[\r\n\0]", "", meta.artifact_id)
        safe_sha256 = re.sub(r"[^a-fA-F0-9]", "", meta.sha256)
        return Response(
            content=content_bytes,
            media_type=meta.media_type,
            headers={
                "X-Content-Type-Options": "nosniff",
                "Content-Disposition": f'attachment; filename="{safe_filename}"',
                "X-Artifact-ID": safe_art_id,
                "X-Artifact-SHA256": safe_sha256,
                "X-Artifact-Size": str(meta.size_bytes),
            }
        )
    except ArtifactNotFoundError:
        raise HTTPException(status_code=404, detail="Artifact not found")
    except ArtifactIntegrityError:
        raise HTTPException(
            status_code=500,
            detail="Artifact integrity verification failed: cryptographic digest mismatch"
        )
    except ArtifactPathTraversalError:
        raise HTTPException(status_code=400, detail="Invalid artifact identifier")
