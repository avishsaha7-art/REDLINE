import os
import re
import json
import uuid
import sqlite3
import hashlib
import datetime
import threading
from typing import Optional, List, Dict, Any, Generator, Tuple
from pydantic import BaseModel, Field

from backend.storage.database import Database, get_database


SAFE_ID_REGEX = re.compile(r"^[a-zA-Z0-9_\.\-]+$")
DEFAULT_MAX_ARTIFACT_BYTES = 50 * 1024 * 1024  # 50 MB


class ArtifactError(Exception):
    """Base error for artifact storage operations."""
    pass


class ArtifactNotFoundError(ArtifactError):
    """Raised when an artifact cannot be found."""
    pass


class ArtifactIntegrityError(ArtifactError):
    """Raised when artifact SHA-256 digest fails verification."""
    pass


class ArtifactPathTraversalError(ArtifactError):
    """Raised when an unsafe path or path traversal attempt is detected."""
    pass


class ArtifactSizeLimitError(ArtifactError):
    """Raised when an artifact exceeds the maximum configured size limit."""
    pass


class ArtifactWriteError(ArtifactError):
    """Raised when artifact storage writing fails."""
    pass


class ArtifactMetadata(BaseModel):
    artifact_id: str
    run_id: str
    artifact_type: str
    media_type: str
    storage_path: str
    size_bytes: int
    sha256: str
    created_at: str
    lineage_ref: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


def get_default_artifacts_root() -> str:
    """Resolves the default root directory for artifact storage."""
    env_root = os.environ.get("REDLINE_ARTIFACTS_DIR") or os.environ.get("REDLINE_ARTIFACT_ROOT")
    if env_root:
        return os.path.abspath(env_root)

    repo_root = os.environ.get("REDLINE_REPO_ROOT")
    if not repo_root:
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    return os.path.abspath(os.path.join(repo_root, "data", "artifacts"))


def get_max_artifact_bytes() -> int:
    """Returns the maximum allowed artifact size in bytes."""
    val = os.environ.get("REDLINE_MAX_ARTIFACT_BYTES")
    if val:
        try:
            return int(val)
        except ValueError:
            pass
    return DEFAULT_MAX_ARTIFACT_BYTES


def _normalize_path_for_containment(path: str) -> str:
    r"""
    Normalizes paths for cross-platform containment comparison.
    Strips Windows \\?\ extended length prefixes and canonicalizes case.
    """
    real = os.path.realpath(path)
    if real.startswith("\\\\?\\"):
        real = real[4:]
    return os.path.normcase(os.path.abspath(real))


class ArtifactStorage:
    """
    Secure, durable local artifact storage layer.
    Manages raw artifact bytes on disk with SHA-256 integrity validation,
    path-traversal defenses, size limits, and synchronized SQLite metadata.
    """
    def __init__(self, root_dir: Optional[str] = None, database: Optional[Database] = None):
        self.root_dir = os.path.abspath(root_dir or get_default_artifacts_root())
        self.db = database or get_database()
        self._lock = threading.RLock()
        self._ensure_root()

    def _ensure_root(self):
        if not os.path.exists(self.root_dir):
            os.makedirs(self.root_dir, exist_ok=True)

    def _validate_identifier(self, identifier: str, name: str = "Identifier") -> str:
        if not identifier or not isinstance(identifier, str):
            raise ArtifactPathTraversalError(f"{name} must be a non-empty string")
        if not SAFE_ID_REGEX.match(identifier) or ".." in identifier or "/" in identifier or "\\" in identifier or "\0" in identifier:
            raise ArtifactPathTraversalError(f"Invalid {name} '{identifier}': forbidden characters or path traversal attempt")
        return identifier

    def _resolve_safe_path(self, run_id: str, artifact_id: str) -> Tuple[str, str]:
        """
        Validates run_id and artifact_id, returning (relative_storage_path, absolute_file_path).
        Enforces containment strictly within self.root_dir.
        """
        valid_run = self._validate_identifier(run_id, "run_id")
        valid_art = self._validate_identifier(artifact_id, "artifact_id")

        rel_path = os.path.join(valid_run, valid_art)
        abs_path = os.path.abspath(os.path.join(self.root_dir, rel_path))

        # Containment verification
        norm_root = _normalize_path_for_containment(self.root_dir)
        norm_path = _normalize_path_for_containment(abs_path)

        # Check that path stays strictly inside root
        try:
            common = os.path.commonpath([norm_root, norm_path])
        except ValueError as e:
            raise ArtifactPathTraversalError(f"Path escape attempt: {abs_path} (cause: {e!r})")

        if common != norm_root:
            raise ArtifactPathTraversalError(f"Path escape attempt detected: {abs_path} outside {self.root_dir}")

        return rel_path.replace("\\", "/"), abs_path

    def store_artifact(
        self,
        run_id: str,
        artifact_id: str,
        artifact_type: str,
        content: bytes | str,
        media_type: str = "application/octet-stream",
        lineage_ref: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        max_bytes: Optional[int] = None
    ) -> ArtifactMetadata:
        """
        Atomically writes artifact content to filesystem and commits metadata to SQLite.
        If SQLite commit fails, cleans up the written file to prevent orphaned state.
        """
        if isinstance(content, str):
            content_bytes = content.encode("utf-8")
        elif isinstance(content, (bytes, bytearray)):
            content_bytes = bytes(content)
        else:
            raise ArtifactWriteError("Artifact content must be bytes or str")

        size_limit = max_bytes or get_max_artifact_bytes()
        size_bytes = len(content_bytes)
        if size_bytes > size_limit:
            raise ArtifactSizeLimitError(f"Artifact size {size_bytes} exceeds limit of {size_limit} bytes")

        # Compute SHA-256 digest
        sha256_hash = hashlib.sha256(content_bytes).hexdigest()
        rel_path, abs_path = self._resolve_safe_path(run_id, artifact_id)
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

        meta_dict = metadata or {}
        art_meta = ArtifactMetadata(
            artifact_id=artifact_id,
            run_id=run_id,
            artifact_type=artifact_type,
            media_type=media_type,
            storage_path=rel_path,
            size_bytes=size_bytes,
            sha256=sha256_hash,
            created_at=now_iso,
            lineage_ref=lineage_ref,
            metadata=meta_dict
        )

        parent_dir = os.path.dirname(abs_path)
        os.makedirs(parent_dir, exist_ok=True)

        # Atomic file write pattern: write to temporary file, flush & fsync, then atomic replace
        tmp_filename = f"{abs_path}.tmp.{uuid.uuid4().hex}"
        try:
            with open(tmp_filename, "wb") as f:
                f.write(content_bytes)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_filename, abs_path)
        except Exception as exc:
            if os.path.exists(tmp_filename):
                try:
                    os.remove(tmp_filename)
                except OSError:
                    pass
            raise ArtifactWriteError(f"Failed to write artifact file to disk: {exc}")

        # Commit metadata row to SQLite
        try:
            with self.db.connection() as conn:
                conn.execute(
                    """
                    INSERT INTO run_artifacts (
                        artifact_id, run_id, artifact_type, media_type, storage_path,
                        size_bytes, sha256, created_at, lineage_ref, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(run_id, artifact_id) DO UPDATE SET
                        artifact_type = excluded.artifact_type,
                        media_type = excluded.media_type,
                        storage_path = excluded.storage_path,
                        size_bytes = excluded.size_bytes,
                        sha256 = excluded.sha256,
                        created_at = excluded.created_at,
                        lineage_ref = excluded.lineage_ref,
                        metadata_json = excluded.metadata_json
                    """,
                    (
                        art_meta.artifact_id,
                        art_meta.run_id,
                        art_meta.artifact_type,
                        art_meta.media_type,
                        art_meta.storage_path,
                        art_meta.size_bytes,
                        art_meta.sha256,
                        art_meta.created_at,
                        art_meta.lineage_ref,
                        json.dumps(art_meta.metadata)
                    )
                )
        except Exception as db_exc:
            # Consistency guarantee: on database commit failure, clean up written file
            if os.path.exists(abs_path):
                try:
                    os.remove(abs_path)
                except OSError:
                    pass
            raise ArtifactWriteError(f"Failed to persist artifact metadata in database: {db_exc}")

        return art_meta

    def get_artifact_metadata(self, run_id: str, artifact_id: str) -> ArtifactMetadata:
        """Retrieves artifact metadata from SQLite."""
        self._validate_identifier(run_id, "run_id")
        self._validate_identifier(artifact_id, "artifact_id")

        with self.db.connection() as conn:
            cur = conn.execute(
                "SELECT * FROM run_artifacts WHERE run_id = ? AND artifact_id = ?",
                (run_id, artifact_id)
            )
            row = cur.fetchone()
            if not row:
                raise ArtifactNotFoundError(f"Artifact '{artifact_id}' not found for run '{run_id}'")

            return self._row_to_metadata(row)

    def list_artifacts(self, run_id: str) -> List[ArtifactMetadata]:
        """Lists all artifacts for a run ordered deterministically by created_at DESC, artifact_id DESC."""
        self._validate_identifier(run_id, "run_id")
        with self.db.connection() as conn:
            cur = conn.execute(
                "SELECT * FROM run_artifacts WHERE run_id = ? ORDER BY created_at DESC, artifact_id DESC",
                (run_id,)
            )
            rows = cur.fetchall()
            return [self._row_to_metadata(r) for r in rows]

    def get_artifact_content(
        self,
        run_id: str,
        artifact_id: str,
        verify_integrity: bool = True
    ) -> Tuple[bytes, ArtifactMetadata]:
        """
        Retrieves artifact bytes and validates SHA-256 digest against authoritative metadata.
        Raises ArtifactIntegrityError if bytes do not match stored SHA-256.
        """
        meta = self.get_artifact_metadata(run_id, artifact_id)
        _, abs_path = self._resolve_safe_path(run_id, artifact_id)

        if not os.path.exists(abs_path):
            raise ArtifactNotFoundError(f"Artifact byte file missing on disk: {abs_path}")

        try:
            with open(abs_path, "rb") as f:
                content_bytes = f.read()
        except OSError as e:
            raise ArtifactError(f"Could not read artifact file: {e}")

        if verify_integrity:
            actual_hash = hashlib.sha256(content_bytes).hexdigest()
            if actual_hash != meta.sha256:
                raise ArtifactIntegrityError(
                    f"Artifact integrity compromised! Expected SHA-256 {meta.sha256}, calculated {actual_hash}"
                )

        return content_bytes, meta

    def stream_artifact_chunks(
        self,
        run_id: str,
        artifact_id: str,
        chunk_size: int = 64 * 1024,
        verify_integrity: bool = True
    ) -> Generator[bytes, None, None]:
        """
        Yields artifact bytes in chunks without loading entire file into memory at once.
        Performs streaming SHA-256 digest calculation if verify_integrity is enabled.
        """
        meta = self.get_artifact_metadata(run_id, artifact_id)
        _, abs_path = self._resolve_safe_path(run_id, artifact_id)

        if not os.path.exists(abs_path):
            raise ArtifactNotFoundError(f"Artifact byte file missing on disk: {abs_path}")

        hasher = hashlib.sha256() if verify_integrity else None

        with open(abs_path, "rb") as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                if hasher:
                    hasher.update(chunk)
                yield chunk

        if hasher:
            actual_hash = hasher.hexdigest()
            if actual_hash != meta.sha256:
                raise ArtifactIntegrityError(
                    f"Artifact integrity compromised! Expected SHA-256 {meta.sha256}, calculated {actual_hash}"
                )

    def delete_artifact(self, run_id: str, artifact_id: str) -> bool:
        """Deletes artifact metadata and removes file from disk safely."""
        self._validate_identifier(run_id, "run_id")
        self._validate_identifier(artifact_id, "artifact_id")
        _, abs_path = self._resolve_safe_path(run_id, artifact_id)

        deleted = False
        with self.db.connection() as conn:
            cur = conn.execute(
                "DELETE FROM run_artifacts WHERE run_id = ? AND artifact_id = ?",
                (run_id, artifact_id)
            )
            deleted = cur.rowcount > 0

        if os.path.exists(abs_path):
            try:
                os.remove(abs_path)
            except OSError:
                pass

        return deleted

    def clear(self):
        """Cleans up all artifacts in the root directory (used in test teardown)."""
        with self.db.connection() as conn:
            try:
                conn.execute("DELETE FROM run_artifacts")
            except sqlite3.OperationalError:
                pass
        if os.path.exists(self.root_dir):
            import shutil
            shutil.rmtree(self.root_dir, ignore_errors=True)
            self._ensure_root()

    def _row_to_metadata(self, row) -> ArtifactMetadata:
        meta_dict = json.loads(row["metadata_json"]) if row["metadata_json"] else {}
        return ArtifactMetadata(
            artifact_id=row["artifact_id"],
            run_id=row["run_id"],
            artifact_type=row["artifact_type"],
            media_type=row["media_type"],
            storage_path=row["storage_path"],
            size_bytes=row["size_bytes"],
            sha256=row["sha256"],
            created_at=row["created_at"],
            lineage_ref=row["lineage_ref"],
            metadata=meta_dict
        )


_global_artifact_storage: Optional[ArtifactStorage] = None
_storage_lock = threading.Lock()

def get_artifact_storage(root_dir: Optional[str] = None, database: Optional[Database] = None) -> ArtifactStorage:
    """Singleton accessor for the global ArtifactStorage instance."""
    global _global_artifact_storage
    with _storage_lock:
        if root_dir is not None or database is not None:
            return ArtifactStorage(root_dir=root_dir, database=database)
        if _global_artifact_storage is None:
            _global_artifact_storage = ArtifactStorage()
        return _global_artifact_storage

def reset_global_artifact_storage():
    """Resets the global ArtifactStorage singleton."""
    global _global_artifact_storage
    with _storage_lock:
        _global_artifact_storage = None
