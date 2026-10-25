import os
import sys

# Test fixture for repo-cons-1
# Verifies candidate patch modifications in isolated workspace
with open("main.py", "r", encoding="utf-8") as f:
    content = f.read()

if content.strip() == "old":
    sys.stderr.write("AssertionError: main.py has not been patched\n")
    sys.exit(1)

print("1 passed")
sys.exit(0)
