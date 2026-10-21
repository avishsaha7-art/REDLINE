"""
Benchmark API Router for REDLINE.

Provides versioned endpoints:
- POST /api/v1/benchmark/runs: Initialize a benchmark run
- POST /api/v1/benchmark/runs/{run_id}/start: Execute runner lifecycle
- GET  /api/v1/benchmark/runs/{run_id}: Query run state and task-level outcomes
- POST /api/v1/benchmark/runs/{run_id}/cancel: Cancel active benchmark run
- POST /api/v1/benchmark/compare: Comparative analysis across completed runs
- GET  /api/v1/benchmark/runs/{run_id}/report: Fetch structured JSON or Markdown report
"""

import uuid
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel, Field

from backend.benchmark.models import (
    BenchmarkRunConfig,
    BenchmarkRunRecord,
    BenchmarkRunState,
    BenchmarkArmType,
    ComparativeEvaluationSummary,
    BenchmarkReport,
)
from backend.benchmark.runner import BenchmarkRunner
from backend.benchmark.storage import get_benchmark_repository
from backend.benchmark.comparison import BenchmarkComparator, IncompatibleBenchmarkRunError
from backend.benchmark.report import BenchmarkReportGenerator
from backend.sandbox.secure_backend import SecureSandboxBackend
from backend.sandbox.models import SandboxPolicy

router = APIRouter()


class CreateBenchmarkRunRequest(BaseModel):
    arm_type: BenchmarkArmType = BenchmarkArmType.ARM_A_REDLINE
    tasks_selected: List[str] = Field(default_factory=list)
    strict_working_tree: bool = True
    timeout_seconds_per_task: int = 120
    max_iterations_per_task: int = 10


class CompareRunsRequest(BaseModel):
    run_ids: List[str]


@router.post("/runs", response_model=BenchmarkRunRecord, status_code=201)
def create_benchmark_run(req: CreateBenchmarkRunRequest):
    """Initializes a new benchmark run in CREATED state."""
    run_id = f"bench_{uuid.uuid4().hex[:12]}"
    config = BenchmarkRunConfig(
        run_id=run_id,
        arm_type=req.arm_type,
        tasks_selected=req.tasks_selected,
        strict_working_tree=req.strict_working_tree,
        timeout_seconds_per_task=req.timeout_seconds_per_task,
        max_iterations_per_task=req.max_iterations_per_task,
    )
    repo = get_benchmark_repository()
    record = BenchmarkRunRecord(run_id=run_id, config=config, state=BenchmarkRunState.CREATED)
    repo.create_run(record)
    return record


@router.post("/runs/{run_id}/start", response_model=BenchmarkRunRecord)
def start_benchmark_run(run_id: str):
    """Executes the runner lifecycle across all mandatory gates."""
    repo = get_benchmark_repository()
    record = repo.get_run(run_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Benchmark run '{run_id}' not found")
    
    if record.state.is_terminal:
        raise HTTPException(status_code=400, detail=f"Benchmark run is already in terminal state: {record.state.value}")

    # Initialize secure sandbox backend
    secure_backend = SecureSandboxBackend(policy=SandboxPolicy())
    runner = BenchmarkRunner(
        config=record.config,
        sandbox_backend=secure_backend,
        repository=repo,
    )
    return runner.run()


@router.get("/runs/{run_id}", response_model=BenchmarkRunRecord)
def get_benchmark_run(run_id: str):
    """Retrieves current run state, metadata, and task-level results."""
    repo = get_benchmark_repository()
    record = repo.get_run(run_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Benchmark run '{run_id}' not found")
    return record


@router.post("/runs/{run_id}/cancel", response_model=BenchmarkRunRecord)
def cancel_benchmark_run(run_id: str):
    """Cancels an active benchmark run."""
    repo = get_benchmark_repository()
    record = repo.get_run(run_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Benchmark run '{run_id}' not found")
    
    if record.state.is_terminal:
        return record

    repo.update_run_state(
        run_id,
        BenchmarkRunState.CANCELLED,
        error_message="Run cancelled by API request"
    )
    return repo.get_run(run_id)


@router.post("/compare", response_model=ComparativeEvaluationSummary)
def compare_benchmark_runs(req: CompareRunsRequest):
    """Performs comparative evaluation across two or more compatible benchmark runs."""
    repo = get_benchmark_repository()
    runs = []
    for rid in req.run_ids:
        r = repo.get_run(rid)
        if not r:
            raise HTTPException(status_code=404, detail=f"Run '{rid}' not found for comparison")
        runs.append(r)

    try:
        return BenchmarkComparator.compare_runs(runs)
    except IncompatibleBenchmarkRunError as e:
        raise HTTPException(status_code=400, detail=f"Incompatible runs: {str(e)}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/runs/{run_id}/report")
def get_benchmark_report(run_id: str, format: str = Query("json", pattern="^(json|markdown)$")):
    """Retrieves an auditable benchmark report in JSON or Markdown format."""
    repo = get_benchmark_repository()
    record = repo.get_run(run_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Benchmark run '{run_id}' not found")

    report = BenchmarkReportGenerator.generate_report(record)
    if format == "markdown":
        md_text = BenchmarkReportGenerator.to_markdown(report)
        return Response(content=md_text, media_type="text/markdown")
    return report
