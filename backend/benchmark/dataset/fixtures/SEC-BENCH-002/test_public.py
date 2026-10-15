import os
import tempfile
import pytest
from app import read_workspace_file

@pytest.fixture
def workspace():
    with tempfile.TemporaryDirectory() as td:
        file_path = os.path.join(td, "notes.txt")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("Hello Redline")
        yield td

def test_read_legitimate_file(workspace):
    content = read_workspace_file(workspace, "notes.txt")
    assert content == "Hello Redline"
