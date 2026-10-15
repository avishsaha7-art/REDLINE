import os

def read_workspace_file(base_dir: str, requested_path: str) -> str:
    base_resolved = os.path.realpath(base_dir)
    target = os.path.realpath(os.path.join(base_dir, requested_path))
    if not (target == base_resolved or target.startswith(base_resolved + os.sep)):
        raise ValueError("Path traversal detected")
    with open(target, "r", encoding="utf-8") as f:
        return f.read()
