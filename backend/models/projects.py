import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

from backend.models.schemas import ResourceBudget


class ProjectFile(BaseModel):
    path: str = Field(..., description="Normalized relative path within the project workspace")
    content: Optional[str] = Field(None, description="UTF-8 text content of the file")
    size_bytes: int = Field(0, description="Size of file in bytes")
    sha256: Optional[str] = Field(None, description="SHA-256 hash of file content")


class LocalProjectImportRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128, description="Human-readable project name")
    files: List[ProjectFile] = Field(..., min_length=1, description="List of files to import into project workspace")
    resource_budget: Optional[ResourceBudget] = None


class ProjectRecord(BaseModel):
    project_id: str
    name: str
    root_path: str
    trust: str = "UNTRUSTED"
    snapshot_hash: str
    file_manifest_hash: str
    file_count: int = 0
    total_bytes: int = 0
    created_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())


class ProjectFileContentResponse(BaseModel):
    path: str
    content: str
    size_bytes: int
    sha256: str


class ConversationRecord(BaseModel):
    conversation_id: str
    project_id: str
    title: str
    created_at: str
    updated_at: str


class MessageRecord(BaseModel):
    message_id: str
    conversation_id: str
    role: str
    content: str
    mentioned_files: List[str] = Field(default_factory=list)
    proposal_id: Optional[str] = None
    timestamp: str


class ProposalRecord(BaseModel):
    proposal_id: str
    project_id: str
    conversation_id: Optional[str] = None
    status: str = "PENDING"  # PENDING, APPLIED, REJECTED
    description: str
    diff: str
    diff_sha256: str
    changed_files: List[str] = Field(default_factory=list)
    proposed_content: Dict[str, str] = Field(default_factory=dict)
    created_at: str
    resolved_at: Optional[str] = None


class CreateConversationRequest(BaseModel):
    title: Optional[str] = None


class SendMessageRequest(BaseModel):
    message: str = Field(..., min_length=1, description="User prompt or instructions")
    conversation_id: Optional[str] = None
    mentioned_files: Optional[List[str]] = None


class ChatResponse(BaseModel):
    conversation_id: str
    message_id: str
    role: str = "assistant"
    content: str
    mentioned_files: List[str] = Field(default_factory=list)
    proposal: Optional[ProposalRecord] = None


class ProjectVerifyRequest(BaseModel):
    task_description: Optional[str] = None
    test_command: Optional[List[str]] = None
    allowed_scope: Optional[List[str]] = None
