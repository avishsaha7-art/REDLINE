import os
import sys

# Test fixture for repo-int-1
# Verifies candidate patch modifications in isolated workspace
has_patch = False

if os.path.exists("backend/orchestrator/orchestrator.py"):
    with open("backend/orchestrator/orchestrator.py", "r", encoding="utf-8") as f:
        if "def utility" in f.read():
            has_patch = True

if os.path.exists("main.py"):
    with open("main.py", "r", encoding="utf-8") as f:
        content = f.read()
    if content.strip() != "a" and content.strip() != "":
        has_patch = True

if not has_patch:
    sys.stderr.write("AssertionError: No candidate patch applied to workspace\n")
    sys.exit(1)

print("1 passed")
sys.exit(0)
