import os
import shutil
import tempfile
import pytest

from backend.sandbox.local_importer import (
    LocalProjectImporter,
    LocalImportSecurityError,
    LocalImportResourceLimitError,
    sanitize_and_validate_relative_path,
    is_path_excluded,
)
from backend.models.projects import ProjectFile
from backend.models.schemas import ResourceBudget
from backend.sandbox.capabilities import RepositoryTrust
from backend.sandbox.registry import get_repository_registry


@pytest.fixture
def temp_importer():
    temp_dir = tempfile.mkdtemp(prefix="test_redline_projects_")
    importer = LocalProjectImporter(projects_base=temp_dir)
    yield importer, temp_dir
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_sanitize_and_validate_relative_path():
    # Valid relative paths
    assert sanitize_and_validate_relative_path("src/main.py") == "src/main.py"
    assert sanitize_and_validate_relative_path("./src/main.py") == "src/main.py"
    assert sanitize_and_validate_relative_path("src\\sub\\module.py") == "src/sub/module.py"
    assert sanitize_and_validate_relative_path("README.md") == "README.md"

    # Path traversal rejection
    with pytest.raises(LocalImportSecurityError):
        sanitize_and_validate_relative_path("../etc/passwd")

    with pytest.raises(LocalImportSecurityError):
        sanitize_and_validate_relative_path("src/../../secret.txt")

    # Absolute path rejection
    with pytest.raises(LocalImportSecurityError):
        sanitize_and_validate_relative_path("/etc/shadow")

    with pytest.raises(LocalImportSecurityError):
        sanitize_and_validate_relative_path("C:\\Windows\\System32\\cmd.exe")

    # Null byte rejection
    with pytest.raises(LocalImportSecurityError):
        sanitize_and_validate_relative_path("src/main.py\0.txt")

    # Prohibited directory / file patterns
    with pytest.raises(LocalImportSecurityError):
        sanitize_and_validate_relative_path(".git/config")

    with pytest.raises(LocalImportSecurityError):
        sanitize_and_validate_relative_path("node_modules/express/index.js")

    with pytest.raises(LocalImportSecurityError):
        sanitize_and_validate_relative_path("src/.env")

    with pytest.raises(LocalImportSecurityError):
        sanitize_and_validate_relative_path("certs/server.pem")


def test_is_path_excluded():
    assert is_path_excluded(".git/HEAD") is True
    assert is_path_excluded("node_modules/package.json") is True
    assert is_path_excluded("venv/bin/activate") is True
    assert is_path_excluded(".venv/pyvenv.cfg") is True
    assert is_path_excluded("__pycache__/main.cpython-311.pyc") is True
    assert is_path_excluded(".env") is True
    assert is_path_excluded(".env.local") is True
    assert is_path_excluded("certs/private.key") is True
    assert is_path_excluded("src/main.py") is False
    assert is_path_excluded("package.json") is False


def test_import_python_project_success(temp_importer):
    importer, _ = temp_importer
    files = [
        ProjectFile(path="src/app.py", content="print('hello')\n"),
        ProjectFile(path="tests/test_app.py", content="def test(): assert True\n"),
        ProjectFile(path="README.md", content="# Test App\n"),
        ProjectFile(path=".git/index", content="ignored"),  # Should be excluded
    ]

    record = importer.import_project(name="python-sample", files=files)

    assert record.project_id.startswith("project-")
    assert record.name == "python-sample"
    assert record.trust == RepositoryTrust.UNTRUSTED.value
    assert record.file_count == 3  # 3 valid files, .git ignored
    assert os.path.isdir(record.root_path)
    assert os.path.isfile(os.path.join(record.root_path, "src", "app.py"))
    assert os.path.isfile(os.path.join(record.root_path, ".baseline", "src", "app.py"))

    # Confirms registered in authoritative RepositoryRegistry
    target = get_repository_registry().resolve_target(record.project_id)
    assert target is not None
    assert target.trust == RepositoryTrust.UNTRUSTED


def test_import_javascript_project_success(temp_importer):
    importer, _ = temp_importer
    files = [
        ProjectFile(path="src/index.ts", content="export const add = (a: number, b: number) => a + b;\n"),
        ProjectFile(path="package.json", content='{"name": "ts-sample", "version": "1.0.0"}\n'),
        ProjectFile(path="tsconfig.json", content='{"compilerOptions": {}}\n'),
    ]

    record = importer.import_project(name="ts-sample", files=files)
    assert record.project_id.startswith("project-")
    assert record.file_count == 3
    assert record.trust == "UNTRUSTED"


def test_resource_limits_enforced(temp_importer):
    importer, _ = temp_importer

    # 1. Single file size limit exceeded
    budget = ResourceBudget(max_file_size=50)
    files = [ProjectFile(path="large.txt", content="A" * 100)]
    with pytest.raises(LocalImportResourceLimitError):
        importer.import_project("oversized-file", files, budget=budget)

    # 2. Total bytes limit exceeded
    budget2 = ResourceBudget(max_repo_bytes=80, max_file_size=100)
    files2 = [
        ProjectFile(path="f1.txt", content="A" * 50),
        ProjectFile(path="f2.txt", content="B" * 50),
    ]
    with pytest.raises(LocalImportResourceLimitError):
        importer.import_project("oversized-repo", files2, budget=budget2)

    # 3. File count limit exceeded
    budget3 = ResourceBudget(max_repo_files=2)
    files3 = [
        ProjectFile(path="a.txt", content="1"),
        ProjectFile(path="b.txt", content="2"),
        ProjectFile(path="c.txt", content="3"),
    ]
    with pytest.raises(LocalImportResourceLimitError):
        importer.import_project("too-many-files", files3, budget=budget3)
