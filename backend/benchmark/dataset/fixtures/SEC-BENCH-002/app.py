import os

def read_workspace_file(base_dir: str, requested_path: str) -> str:
    # VULNERABILITY: Insecure os.path.join allows ../ traversal outside base_dir
    target = os.path.join(base_dir, requested_path)
    with open(target, "r", encoding="utf-8") as f:
        return f.read()
