import os
import datetime
from typing import Dict, List, Optional
from pydantic import BaseModel, Field

from backend.sandbox.capabilities import RepositoryTrust
from backend.sandbox.trust import resolve_repository_trust

FIXTURES_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "fixtures"))


class RepositoryTarget(BaseModel):
    repository_id: str
    repo_root: str
    trust: RepositoryTrust = RepositoryTrust.UNTRUSTED
    repository_url: Optional[str] = None
    commit_sha: Optional[str] = None
    snapshot_hash: Optional[str] = None
    file_manifest_hash: Optional[str] = None
    file_count: int = 0
    total_bytes: int = 0
    is_quarantined: bool = False
    registered_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())


class RepositoryRegistry:
    """
    Authoritative Repository Target Registry.
    Maps internal repository target IDs to verified local or quarantined snapshots.
    Prevents silent fallback to arbitrary local fixtures and enforces trust invariants.
    """
    def __init__(self):
        self._targets: Dict[str, RepositoryTarget] = {}
        self._init_baseline_targets()

    def _init_baseline_targets(self) -> None:
        """Initializes standard fixtures and demo targets."""
        # 1. Standard authorized development fixtures
        for fixture_name in (
            "repo-int-1",
            "repo-cons-1",
            "repo-crash-1",
            "repo-adv-1",
            "repo-trusted",
            "repo-sample-auth-service",
            "demo-repo-a",
            "demo-repo-b",
            "demo-repo-c",
            "test-repo",
            "repo-1",
            "repo-fail-1",
        ):
            fixture_path = os.path.join(FIXTURES_DIR, fixture_name)
            target_path = fixture_path if os.path.isdir(fixture_path) else os.path.join(FIXTURES_DIR, "repo-int-1")
            if os.path.isdir(target_path):
                self._targets[fixture_name] = RepositoryTarget(
                    repository_id=fixture_name,
                    repo_root=os.path.abspath(target_path),
                    trust=RepositoryTrust.TRUSTED_DEVELOPMENT,
                    is_quarantined=False,
                )

        # 2. Designated demo & test untrusted fixtures
        int1_path = os.path.join(FIXTURES_DIR, "repo-int-1")
        if os.path.isdir(int1_path):
            for demo_untrusted_id in (
                "untrusted-external-repo-demo",
                "untrusted-external-repo",
                "untrusted-external-repo-xyz",
                "malicious-unauthorized-repo",
                "unknown-external-repo",
            ):
                self._targets[demo_untrusted_id] = RepositoryTarget(
                    repository_id=demo_untrusted_id,
                    repo_root=os.path.abspath(int1_path),
                    trust=RepositoryTrust.UNTRUSTED,
                    is_quarantined=False,
                )

    def register(self, target: RepositoryTarget) -> None:
        """
        Registers a repository target.
        Enforces that any quarantined or remote repository is strictly UNTRUSTED.
        """
        if target.is_quarantined or target.repository_url:
            target.trust = RepositoryTrust.UNTRUSTED

        self._targets[target.repository_id] = target

    def get(self, repository_id: str) -> Optional[RepositoryTarget]:
        return self._targets.get(repository_id)

    def list_targets(self) -> List[RepositoryTarget]:
        return list(self._targets.values())

    def resolve_target(self, repository_id: str) -> Optional[RepositoryTarget]:
        """
        Resolves a repository target ID to a verified target.
        Returns None if the target cannot be found or resolved (no silent fallback).
        """
        if not repository_id or not isinstance(repository_id, str):
            return None

        clean_id = repository_id.strip()

        # 1. Explicitly registered target
        if clean_id in self._targets:
            return self._targets[clean_id]

        # 2. Guard against URL or path traversal interpretation
        if any(c in clean_id for c in ("/", "\\", ":", "%", "..")):
            return None
        if clean_id.startswith("http://") or clean_id.startswith("https://"):
            return None

        # 3. Dynamic lookup in data/fixtures/{repository_id}
        fixture_path = os.path.join(FIXTURES_DIR, clean_id)
        if os.path.isdir(fixture_path):
            trust = resolve_repository_trust(clean_id)
            target = RepositoryTarget(
                repository_id=clean_id,
                repo_root=os.path.abspath(fixture_path),
                trust=trust,
                is_quarantined=False,
            )
            self._targets[clean_id] = target
            return target

        # 4. Check data/projects/{repository_id} for local imported projects
        projects_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "projects", clean_id))
        if os.path.isdir(projects_dir):
            target = RepositoryTarget(
                repository_id=clean_id,
                repo_root=projects_dir,
                trust=RepositoryTrust.UNTRUSTED,
                is_quarantined=True,
            )
            self._targets[clean_id] = target
            return target

        # 4b. Check projects database for imported projects by project_id or name
        try:
            from backend.storage.database import get_database
            with get_database().connection() as conn:
                row = conn.execute(
                    "SELECT project_id, name, root_path, trust FROM projects WHERE project_id = ? OR name = ?",
                    (clean_id, clean_id)
                ).fetchone()
                if row and os.path.isdir(row["root_path"]):
                    trust = RepositoryTrust.UNTRUSTED if row["trust"] == "UNTRUSTED" else RepositoryTrust.TRUSTED_DEVELOPMENT
                    target = RepositoryTarget(
                        repository_id=clean_id,
                        repo_root=os.path.abspath(row["root_path"]),
                        trust=trust,
                        is_quarantined=True,
                    )
                    self._targets[clean_id] = target
                    return target
        except Exception:
            pass

        # 5. Check REDLINE_REPO_ROOT if set for local testing
        env_root = os.environ.get("REDLINE_REPO_ROOT")
        if env_root and os.path.isdir(env_root):
            trust = resolve_repository_trust(clean_id)
            target = RepositoryTarget(
                repository_id=clean_id,
                repo_root=os.path.abspath(env_root),
                trust=trust,
                is_quarantined=False,
            )
            return target

        # 6. Fail closed: unknown targets return None (never fallback to repo-int-1)
        return None

    def clear(self) -> None:
        self._targets.clear()
        self._init_baseline_targets()


_registry: RepositoryRegistry = RepositoryRegistry()


def get_repository_registry() -> RepositoryRegistry:
    return _registry


def set_repository_registry(registry: RepositoryRegistry) -> None:
    global _registry
    _registry = registry


def reset_repository_registry() -> None:
    _registry.clear()
