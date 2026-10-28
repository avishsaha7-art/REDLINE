import json
import sqlite3
import datetime
from typing import List, Optional, Dict, Any

from backend.models.projects import (
    ProjectRecord,
    ConversationRecord,
    MessageRecord,
    ProposalRecord,
)
from backend.storage.database import Database, get_database


class SQLiteProjectRepository:
    """
    Authoritative SQLite repository for REDLINE project workspace persistence.
    Stores imported projects, conversation threads, messages, and controlled change proposals.
    """
    def __init__(self, database: Optional[Database] = None):
        self._db = database

    @property
    def db(self) -> Database:
        return self._db or get_database()


    def create_project(self, project: ProjectRecord) -> None:
        with self.db.connection() as conn:
            conn.execute(
                """
                INSERT INTO projects (
                    project_id, name, root_path, trust, snapshot_hash,
                    file_manifest_hash, file_count, total_bytes, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project.project_id,
                    project.name,
                    project.root_path,
                    project.trust,
                    project.snapshot_hash,
                    project.file_manifest_hash,
                    project.file_count,
                    project.total_bytes,
                    project.created_at,
                    project.updated_at,
                ),
            )

    def get_project(self, project_id: str) -> Optional[ProjectRecord]:
        with self.db.connection() as conn:
            row = conn.execute(
                "SELECT * FROM projects WHERE project_id = ?",
                (project_id,),
            ).fetchone()
            if not row:
                return None
            return ProjectRecord(
                project_id=row["project_id"],
                name=row["name"],
                root_path=row["root_path"],
                trust=row["trust"],
                snapshot_hash=row["snapshot_hash"],
                file_manifest_hash=row["file_manifest_hash"],
                file_count=row["file_count"],
                total_bytes=row["total_bytes"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )

    def list_projects(self) -> List[ProjectRecord]:
        with self.db.connection() as conn:
            rows = conn.execute("SELECT * FROM projects ORDER BY created_at DESC").fetchall()
            return [
                ProjectRecord(
                    project_id=row["project_id"],
                    name=row["name"],
                    root_path=row["root_path"],
                    trust=row["trust"],
                    snapshot_hash=row["snapshot_hash"],
                    file_manifest_hash=row["file_manifest_hash"],
                    file_count=row["file_count"],
                    total_bytes=row["total_bytes"],
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                )
                for row in rows
            ]

    def update_project_snapshot(
        self,
        project_id: str,
        snapshot_hash: str,
        file_manifest_hash: str,
        file_count: int,
        total_bytes: int,
    ) -> None:
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self.db.connection() as conn:
            conn.execute(
                """
                UPDATE projects
                SET snapshot_hash = ?, file_manifest_hash = ?, file_count = ?, total_bytes = ?, updated_at = ?
                WHERE project_id = ?
                """,
                (snapshot_hash, file_manifest_hash, file_count, total_bytes, now_iso, project_id),
            )

    def delete_project(self, project_id: str) -> bool:
        with self.db.connection() as conn:
            cur = conn.execute("DELETE FROM projects WHERE project_id = ?", (project_id,))
            return cur.rowcount > 0

    def create_conversation(self, conv: ConversationRecord) -> None:
        with self.db.connection() as conn:
            conn.execute(
                """
                INSERT INTO project_conversations (
                    conversation_id, project_id, title, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    conv.conversation_id,
                    conv.project_id,
                    conv.title,
                    conv.created_at,
                    conv.updated_at,
                ),
            )

    def get_conversation(self, conversation_id: str) -> Optional[ConversationRecord]:
        with self.db.connection() as conn:
            row = conn.execute(
                "SELECT * FROM project_conversations WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()
            if not row:
                return None
            return ConversationRecord(
                conversation_id=row["conversation_id"],
                project_id=row["project_id"],
                title=row["title"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )

    def list_conversations(self, project_id: str) -> List[ConversationRecord]:
        with self.db.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM project_conversations WHERE project_id = ? ORDER BY updated_at DESC",
                (project_id,),
            ).fetchall()
            return [
                ConversationRecord(
                    conversation_id=row["conversation_id"],
                    project_id=row["project_id"],
                    title=row["title"],
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                )
                for row in rows
            ]

    def save_message(self, msg: MessageRecord) -> None:
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self.db.connection() as conn:
            conn.execute(
                """
                INSERT INTO project_messages (
                    message_id, conversation_id, role, content,
                    mentioned_files_json, proposal_id, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    msg.message_id,
                    msg.conversation_id,
                    msg.role,
                    msg.content,
                    json.dumps(msg.mentioned_files),
                    msg.proposal_id,
                    msg.timestamp,
                ),
            )
            conn.execute(
                "UPDATE project_conversations SET updated_at = ? WHERE conversation_id = ?",
                (now_iso, msg.conversation_id),
            )

    def list_messages(self, conversation_id: str) -> List[MessageRecord]:
        with self.db.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM project_messages WHERE conversation_id = ? ORDER BY timestamp ASC",
                (conversation_id,),
            ).fetchall()
            return [
                MessageRecord(
                    message_id=row["message_id"],
                    conversation_id=row["conversation_id"],
                    role=row["role"],
                    content=row["content"],
                    mentioned_files=json.loads(row["mentioned_files_json"]) if row["mentioned_files_json"] else [],
                    proposal_id=row["proposal_id"],
                    timestamp=row["timestamp"],
                )
                for row in rows
            ]

    def create_proposal(self, prop: ProposalRecord) -> None:
        with self.db.connection() as conn:
            conn.execute(
                """
                INSERT INTO project_proposals (
                    proposal_id, project_id, conversation_id, status,
                    description, diff, diff_sha256, changed_files_json,
                    proposed_content_json, created_at, resolved_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    prop.proposal_id,
                    prop.project_id,
                    prop.conversation_id,
                    prop.status,
                    prop.description,
                    prop.diff,
                    prop.diff_sha256,
                    json.dumps(prop.changed_files),
                    json.dumps(prop.proposed_content),
                    prop.created_at,
                    prop.resolved_at,
                ),
            )

    def get_proposal(self, proposal_id: str) -> Optional[ProposalRecord]:
        with self.db.connection() as conn:
            row = conn.execute(
                "SELECT * FROM project_proposals WHERE proposal_id = ?",
                (proposal_id,),
            ).fetchone()
            if not row:
                return None
            return ProposalRecord(
                proposal_id=row["proposal_id"],
                project_id=row["project_id"],
                conversation_id=row["conversation_id"],
                status=row["status"],
                description=row["description"],
                diff=row["diff"],
                diff_sha256=row["diff_sha256"],
                changed_files=json.loads(row["changed_files_json"]) if row["changed_files_json"] else [],
                proposed_content=json.loads(row["proposed_content_json"]) if row["proposed_content_json"] else {},
                created_at=row["created_at"],
                resolved_at=row["resolved_at"],
            )

    def list_proposals(self, project_id: str) -> List[ProposalRecord]:
        with self.db.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM project_proposals WHERE project_id = ? ORDER BY created_at DESC",
                (project_id,),
            ).fetchall()
            return [
                ProposalRecord(
                    proposal_id=row["proposal_id"],
                    project_id=row["project_id"],
                    conversation_id=row["conversation_id"],
                    status=row["status"],
                    description=row["description"],
                    diff=row["diff"],
                    diff_sha256=row["diff_sha256"],
                    changed_files=json.loads(row["changed_files_json"]) if row["changed_files_json"] else [],
                    proposed_content=json.loads(row["proposed_content_json"]) if row["proposed_content_json"] else {},
                    created_at=row["created_at"],
                    resolved_at=row["resolved_at"],
                )
                for row in rows
            ]

    def update_proposal_status(self, proposal_id: str, status: str, resolved_at: str) -> None:
        with self.db.connection() as conn:
            conn.execute(
                "UPDATE project_proposals SET status = ?, resolved_at = ? WHERE proposal_id = ?",
                (status, resolved_at, proposal_id),
            )


_project_repo: Optional[SQLiteProjectRepository] = None


def get_project_repository() -> SQLiteProjectRepository:
    global _project_repo
    if _project_repo is None:
        _project_repo = SQLiteProjectRepository()
    return _project_repo


def set_project_repository(repo: Optional[SQLiteProjectRepository]) -> None:
    global _project_repo
    _project_repo = repo


def reset_project_repository() -> None:
    global _project_repo
    _project_repo = None
