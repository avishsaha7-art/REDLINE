import pytest
from backend.sandbox.client import SandboxClient

def test_normalize_patch_diff_handles_indented_markers_and_recount():
    raw_diff = (
        "--- a/src/calculator.py\n"
        "+++ b/src/calculator.py\n"
        "@@ -10,14 +10,19 @@\n"
        "        a = float(a_str)\n"
        "        b = float(b_str)\n"
        "    \n"
        "   -   if op == \"+\":\n"
        "   -       return a + b\n"
        "   +   if op == \"+\":\n"
        "   +       return a + b\n"
        "   +   elif op == \"/\":\n"
        "   +       if b == 0:\n"
        "   +           raise ValueError(\"Division by zero is not allowed\")\n"
        "   +       return a / b\n"
        "   \n"
    )

    norm = SandboxClient._normalize_patch_diff(raw_diff)

    assert norm.startswith("--- a/src/calculator.py\n+++ b/src/calculator.py\n")
    # Verify hunk header recounted
    assert "@@ -10," in norm
    # Verify diff markers are in column 0
    lines = norm.splitlines()
    hunk_lines = [l for l in lines if not l.startswith("---") and not l.startswith("+++") and not l.startswith("@@")]
    for line in hunk_lines:
        assert line[0] in ("-", "+", " "), f"Line does not start with valid diff marker: {line!r}"

    # Verify indentation preserved after marker
    assert "-    if op == \"+\":" in lines
    assert "-        return a + b" in lines
    assert "+    if op == \"+\":" in lines
    assert "+        return a + b" in lines
    assert "+    elif op == \"/\":" in lines
    assert "+        if b == 0:" in lines
    assert "+            raise ValueError(\"Division by zero is not allowed\")" in lines
