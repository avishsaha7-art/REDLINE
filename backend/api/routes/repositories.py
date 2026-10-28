from typing import List, Optional
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from backend.sandbox.cloner import QuarantinedRepositoryCloner, ClonerError, QuarantinedRepositoryMetadata
from backend.sandbox.registry import get_repository_registry, RepositoryTarget
from backend.models.schemas import ResourceBudget

router = APIRouter()


class ImportRepositoryRequest(BaseModel):
    repository_url: str = Field(..., description="Public HTTPS Git repository URL")
    commit_sha: str = Field(..., description="Full 40-character or 64-character pinned Git commit SHA")
    resource_budget: Optional[ResourceBudget] = None


class RepositoryResponse(BaseModel):
    repository_id: str
    trust: str
    repository_url: Optional[str] = None
    commit_sha: Optional[str] = None
    snapshot_hash: Optional[str] = None
    file_manifest_hash: Optional[str] = None
    file_count: int = 0
    total_bytes: int = 0
    is_quarantined: bool = False
    registered_at: str


@router.post("/import", response_model=RepositoryResponse, status_code=status.HTTP_201_CREATED)
def import_repository(request: ImportRepositoryRequest):
    """
    Imports and quarantines a public HTTPS repository at a pinned Git commit SHA.
    Enforces SSRF defense, execution timeouts, workspace limits, and UNTRUSTED classification.
    """
    cloner = QuarantinedRepositoryCloner()
    budget = request.resource_budget or ResourceBudget()
    try:
        meta: QuarantinedRepositoryMetadata = cloner.import_repository(
            url=request.repository_url,
            commit_sha=request.commit_sha,
            budget=budget
        )
    except ClonerError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Repository import rejected: {str(exc)}"
        )

    return RepositoryResponse(
        repository_id=meta.target_id,
        trust=meta.trust.value,
        repository_url=meta.repository_url,
        commit_sha=meta.commit_sha,
        snapshot_hash=meta.snapshot_hash,
        file_manifest_hash=meta.file_manifest_hash,
        file_count=meta.file_count,
        total_bytes=meta.total_bytes,
        is_quarantined=True,
        registered_at=meta.imported_at
    )


@router.get("", response_model=List[RepositoryResponse])
def list_repositories():
    """Lists all registered repository targets."""
    registry = get_repository_registry()
    targets = registry.list_targets()
    return [
        RepositoryResponse(
            repository_id=t.repository_id,
            trust=t.trust.value if hasattr(t.trust, "value") else str(t.trust),
            repository_url=t.repository_url,
            commit_sha=t.commit_sha,
            snapshot_hash=t.snapshot_hash,
            file_manifest_hash=t.file_manifest_hash,
            file_count=t.file_count,
            total_bytes=t.total_bytes,
            is_quarantined=t.is_quarantined,
            registered_at=t.registered_at
        )
        for t in targets
    ]


@router.get("/{repository_id}", response_model=RepositoryResponse)
def get_repository(repository_id: str):
    """Retrieves metadata for a registered repository target."""
    registry = get_repository_registry()
    target = registry.resolve_target(repository_id)
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Repository target '{repository_id}' not found."
        )
    return RepositoryResponse(
        repository_id=target.repository_id,
        trust=target.trust.value if hasattr(target.trust, "value") else str(target.trust),
        repository_url=target.repository_url,
        commit_sha=target.commit_sha,
        snapshot_hash=target.snapshot_hash,
        file_manifest_hash=target.file_manifest_hash,
        file_count=target.file_count,
        total_bytes=target.total_bytes,
        is_quarantined=target.is_quarantined,
        registered_at=target.registered_at
    )
