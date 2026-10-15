import os
import tempfile
import pytest
from app import read_workspace_file

def test_path_traversal_blocked():
    with tempfile.TemporaryDirectory() as parent:
        outside_secret = os.path.join(parent, "secret.key")
        with open(outside_secret, "w", encoding="utf-8") as f:
            f.write("SUPER_SECRET_HOST_DATA")
        
        workspace = os.path.join(parent, "workspace")
        os.makedirs(workspace)
        
        traversal_path = os.path.join("..", "secret.key")
        with pytest.raises((ValueError, PermissionError)):
            read_workspace_file(workspace, traversal_path)

def test_legitimate_nested_file_allowed():
    with tempfile.TemporaryDirectory() as td:
        sub = os.path.join(td, "docs")
        os.makedirs(sub)
        file_path = os.path.join(sub, "readme.txt")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("Valid doc")
        
        assert read_workspace_file(td, os.path.join("docs", "readme.txt")) == "Valid doc"
