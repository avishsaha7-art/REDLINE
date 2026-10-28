import os
import tempfile
import subprocess
import pytest
from backend.models.schemas import TaskContract, PatchCandidate, ResourceBudget, OperationalResult, RepairCandidate, ArchitectPlan
from backend.models.provider import ModelProvider, ModelResponse
from backend.verification.patch_validation import validate_patch, extract_paths_from_diff, is_safe_path
from backend.sandbox.client import SandboxClient
from backend.agents.repairer import RepairerAgent
from backend.agents.builder import BuilderAgent
from backend.orchestrator.events import EventRecorder

# ---------------------------------------------------------------------------
# 1. Patch Normalization Tests
# ---------------------------------------------------------------------------

def test_normalize_patch_diff_aligns_markers_and_preserves_indentation():
    raw_diff = (
        "--- a/src/calculator.py\n"
        "+++ b/src/calculator.py\n"
        "@@ -10,6 +10,9 @@\n"
        "     a = float(a_str)\n"
        "     b = float(b_str)\n"
        " \n"
        "-    if op == \"+\":\n"
        "+    if op == \"+\":\n"
        "+        return a + b\n"
        "+    elif op == \"/\":\n"
        "+        if b == 0:\n"
        "+            raise ValueError(\"Division by zero is not allowed\")\n"
        "+        return a / b\n"
    )

    norm = SandboxClient._normalize_patch_diff(raw_diff)

    assert norm.startswith("--- a/src/calculator.py\n+++ b/src/calculator.py\n")
    assert "@@ -10," in norm
    lines = norm.splitlines()
    # Check that diff markers are strictly in column 0
    hunk_lines = [l for l in lines if not l.startswith("---") and not l.startswith("+++") and not l.startswith("@@")]
    for line in hunk_lines:
        assert line[0] in ("-", "+", " "), f"Marker not at col 0: {line!r}"

    # Verify 4-space and 8-space python indents are preserved exactly
    assert "+    elif op == \"/\":" in lines
    assert "+        if b == 0:" in lines
    assert "+            raise ValueError(\"Division by zero is not allowed\")" in lines

def test_normalize_patch_diff_handles_indented_diff_markers():
    # LLMs frequently indent the whole diff inside a markdown/JSON string
    indented_diff = (
        "  --- a/src/calc.py\n"
        "  +++ b/src/calc.py\n"
        "  @@ -1,3 +1,4 @@\n"
        "   def foo():\n"
        "  -    return 1\n"
        "  +    if True:\n"
        "  +        return 2\n"
    )

    norm = SandboxClient._normalize_patch_diff(indented_diff)
    lines = norm.splitlines()
    assert lines[0] == "--- a/src/calc.py"
    assert lines[1] == "+++ b/src/calc.py"
    assert lines[2].startswith("@@ -1,")
    assert lines[3] == " def foo():"
    assert lines[4] == "-    return 1"
    assert lines[5] == "+    if True:"
    assert lines[6] == "+        return 2"

# ---------------------------------------------------------------------------
# 2. Missing-Hunk Rejection & Hunk Syntax Tests
# ---------------------------------------------------------------------------

def test_extract_paths_rejects_missing_hunks():
    # Diff with headers but no hunks at all
    no_hunks = (
        "--- a/src/calculator.py\n"
        "+++ b/src/calculator.py\n"
    )
    with pytest.raises(ValueError, match="Malformed patch format: Missing hunks"):
        extract_paths_from_diff(no_hunks)

def test_extract_paths_rejects_placeholder_hunks():
    # Diff with placeholder hunk markers like @@ ... @@
    placeholder = (
        "--- a/src/calculator.py\n"
        "+++ b/src/calculator.py\n"
        "@@ ... @@\n"
        "+    return a / b\n"
    )
    with pytest.raises(ValueError, match="Malformed patch format: Missing hunks"):
        extract_paths_from_diff(placeholder)

def test_extract_paths_accepts_valid_hunk_formats():
    # Standard format with count
    diff1 = (
        "--- a/src/calculator.py\n"
        "+++ b/src/calculator.py\n"
        "@@ -10,5 +10,8 @@\n"
        " context\n"
    )
    assert extract_paths_from_diff(diff1) == {"src/calculator.py"}

    # Single-line hunk format
    diff2 = (
        "--- a/src/calculator.py\n"
        "+++ b/src/calculator.py\n"
        "@@ -1 +1 @@\n"
        "-old\n"
        "+new\n"
    )
    assert extract_paths_from_diff(diff2) == {"src/calculator.py"}

def test_validate_patch_rejects_missing_target_header():
    task = TaskContract(
        task_id="t1", repository_id="r1", base_commit_or_snapshot="snap1",
        task_description="desc", allowed_scope=["src/calculator.py"]
    )
    # Missing +++ b/ header
    bad_diff = (
        "--- a/src/calculator.py\n"
        "@@ -1,2 +1,2 @@\n"
        "-a\n"
        "+b\n"
    )
    patch = PatchCandidate(
        patch_id="p1", task_id="t1", base_commit_or_snapshot="snap1",
        diff=bad_diff, changed_files=["src/calculator.py"]
    )
    with pytest.raises(ValueError, match="Malformed patch format: Missing target header"):
        validate_patch(patch, task)

# ---------------------------------------------------------------------------
# 3. Allowed-Scope & Protected File Enforcement
# ---------------------------------------------------------------------------

def test_validate_patch_enforces_allowed_scope():
    task = TaskContract(
        task_id="t1", repository_id="r1", base_commit_or_snapshot="snap1",
        task_description="desc", allowed_scope=["src/calculator.py"]
    )
    diff = (
        "--- a/src/unauthorized.py\n"
        "+++ b/src/unauthorized.py\n"
        "@@ -1,2 +1,2 @@\n"
        "-a\n"
        "+b\n"
    )
    patch = PatchCandidate(
        patch_id="p1", task_id="t1", base_commit_or_snapshot="snap1",
        diff=diff, changed_files=["src/unauthorized.py"]
    )
    with pytest.raises(ValueError, match="Unauthorized file modification: src/unauthorized.py"):
        validate_patch(patch, task)

def test_validate_patch_rejects_protected_files():
    task = TaskContract(
        task_id="t1", repository_id="r1", base_commit_or_snapshot="snap1",
        task_description="desc", allowed_scope=[".env"]
    )
    diff = (
        "--- a/.env\n"
        "+++ b/.env\n"
        "@@ -1,1 +1,1 @@\n"
        "+SECRET=evil\n"
    )
    patch = PatchCandidate(
        patch_id="p1", task_id="t1", base_commit_or_snapshot="snap1",
        diff=diff, changed_files=[".env"]
    )
    with pytest.raises(ValueError, match="Protected-file modification attempted: .env"):
        validate_patch(patch, task)

# ---------------------------------------------------------------------------
# 4. Path Traversal & Absolute Path Rejection
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad_path", [
    "../secret.py",
    "foo/../../secret.py",
    "..\\secret.py",
    "/etc/passwd",
    "\\Windows\\System32\\cmd.exe",
    "C:/Windows/System32/cmd.exe",
    "C:\\secret.txt",
    "\\\\server\\share\\evil.py",
])
def test_is_safe_path_rejects_unsafe_paths(bad_path):
    assert not is_safe_path(bad_path), f"Failed to reject unsafe path: {bad_path}"

def test_validate_patch_rejects_traversal_in_diff():
    task = TaskContract(
        task_id="t1", repository_id="r1", base_commit_or_snapshot="snap1",
        task_description="desc", allowed_scope=["../secret.py"]
    )
    diff = (
        "--- a/../secret.py\n"
        "+++ b/../secret.py\n"
        "@@ -1,1 +1,1 @@\n"
        "+leak\n"
    )
    patch = PatchCandidate(
        patch_id="p1", task_id="t1", base_commit_or_snapshot="snap1",
        diff=diff, changed_files=["../secret.py"]
    )
    with pytest.raises(ValueError, match="Path traversal or absolute path detected"):
        validate_patch(patch, task)

# ---------------------------------------------------------------------------
# 5. Repairer Structured Output & Bounded Retry
# ---------------------------------------------------------------------------

class MockProvider(ModelProvider):
    def __init__(self, responses):
        self.responses = list(responses)
        self.call_count = 0
        self.provider_name = "mock_provider"

    def generate(self, messages, temperature=0.0):
        if self.call_count >= len(self.responses):
            raise RuntimeError("Exceeded mock responses")
        resp_text = self.responses[self.call_count]
        self.call_count += 1
        return ModelResponse(
            response_text=resp_text,
            provider="mock",
            model="mock-model",
            prompt_version="v1",
            request_id="req-1",
            latency_ms=10.0,
            input_tokens=50,
            output_tokens=50,
            timestamp=123456.0
        )

def test_repairer_parses_valid_json_diff():
    valid_json = (
        '{\n'
        '  "changed_files": ["src/calculator.py"],\n'
        '  "diff": "--- a/src/calculator.py\\n+++ b/src/calculator.py\\n@@ -1,2 +1,3 @@\\n-old\\n+new\\n context\\n",\n'
        '  "target_failure": "Zero division",\n'
        '  "reasoning_summary": "Added check"\n'
        '}'
    )
    provider = MockProvider([valid_json])
    repairer = RepairerAgent(tools=None, model_provider=provider)

    task = TaskContract(task_id="t1", repository_id="r1", base_commit_or_snapshot="s1", task_description="d")
    current_patch = PatchCandidate(patch_id="p0", task_id="t1", base_commit_or_snapshot="s1", diff="--- a/src/calculator.py\n+++ b/src/calculator.py\n@@ -1 +1 @@\n-x\n+y\n")

    result = repairer.repair(task, current_patch, counterexample_text="ZeroDivisionError")
    assert isinstance(result, RepairCandidate)
    assert result.changed_files == ["src/calculator.py"]
    assert "--- a/src/calculator.py" in result.diff
    assert provider.call_count == 1

def test_repairer_retries_and_recovers_on_initial_malformed_diff():
    malformed_first_response = (
        '{\n'
        '  "changed_files": ["src/calculator.py"],\n'
        '  "diff": "--- a/src/calculator.py\\n+++ b/src/calculator.py\\n@@ ... @@\\n+fixed code\\n",\n'
        '  "target_failure": "Zero division",\n'
        '  "reasoning_summary": "Placeholder hunk"\n'
        '}'
    )
    valid_second_response = (
        '{\n'
        '  "changed_files": ["src/calculator.py"],\n'
        '  "diff": "--- a/src/calculator.py\\n+++ b/src/calculator.py\\n@@ -1,2 +1,3 @@\\n-old\\n+new\\n context\\n",\n'
        '  "target_failure": "Zero division",\n'
        '  "reasoning_summary": "Valid hunk"\n'
        '}'
    )
    events = EventRecorder("test-run-retry")
    provider = MockProvider([malformed_first_response, valid_second_response])
    repairer = RepairerAgent(tools=None, model_provider=provider, events=events)

    task = TaskContract(task_id="t1", repository_id="r1", base_commit_or_snapshot="s1", task_description="d")
    current_patch = PatchCandidate(patch_id="p0", task_id="t1", base_commit_or_snapshot="s1", diff="--- a/src/calculator.py\n+++ b/src/calculator.py\n@@ -1 +1 @@\n-x\n+y\n")

    result = repairer.repair(task, current_patch, counterexample_text="ZeroDivisionError")
    assert isinstance(result, RepairCandidate)
    assert provider.call_count == 2
    recorded = [e["event_type"] for e in events.events]
    assert "REPAIR_RETRY_TRIGGERED" in recorded
    assert "REPAIR_RETRY_COMPLETED" in recorded

def test_repairer_fails_closed_when_retry_also_fails():
    bad_output = '{"broken": "json"}'
    events = EventRecorder("test-run-fail")
    provider = MockProvider([bad_output, bad_output])
    repairer = RepairerAgent(tools=None, model_provider=provider, events=events)

    task = TaskContract(task_id="t1", repository_id="r1", base_commit_or_snapshot="s1", task_description="d")
    current_patch = PatchCandidate(patch_id="p0", task_id="t1", base_commit_or_snapshot="s1", diff="--- a/src/calculator.py\n+++ b/src/calculator.py\n@@ -1 +1 @@\n-x\n+y\n")

    result = repairer.repair(task, current_patch, counterexample_text="ZeroDivisionError")
    assert result == OperationalResult.MODEL_FAILURE
    assert provider.call_count == 2

def test_builder_parses_valid_json_diff():
    valid_json = (
        '{\n'
        '  "changed_files": ["src/calculator.py"],\n'
        '  "diff": "--- a/src/calculator.py\\n+++ b/src/calculator.py\\n@@ -1,2 +1,3 @@\\n-old\\n+new\\n context\\n"\n'
        '}'
    )
    provider = MockProvider([valid_json])
    builder = BuilderAgent(tools=None, model_provider=provider)
    task = TaskContract(task_id="t1", repository_id="r1", base_commit_or_snapshot="s1", task_description="d")
    plan = ArchitectPlan(objective="Fix bugs", files_to_modify=["src/calculator.py"], implementation_steps=["step 1"])

    patch = builder.build(task, plan)
    assert isinstance(patch, PatchCandidate)
    assert patch.changed_files == ["src/calculator.py"]
    assert "--- a/src/calculator.py" in patch.diff

def test_builder_retries_and_recovers_on_placeholder_hunks():
    bad_json = (
        '{\n'
        '  "changed_files": ["src/calculator.py"],\n'
        '  "diff": "--- a/src/calculator.py\\n+++ b/src/calculator.py\\n@@ ... @@\\n<placeholder>\\n"\n'
        '}'
    )
    good_json = (
        '{\n'
        '  "changed_files": ["src/calculator.py"],\n'
        '  "diff": "--- a/src/calculator.py\\n+++ b/src/calculator.py\\n@@ -1,2 +1,3 @@\\n-old\\n+new\\n context\\n"\n'
        '}'
    )
    events = EventRecorder("test-builder-retry")
    provider = MockProvider([bad_json, good_json])
    builder = BuilderAgent(tools=None, model_provider=provider, events=events)
    task = TaskContract(task_id="t1", repository_id="r1", base_commit_or_snapshot="s1", task_description="d")
    plan = ArchitectPlan(objective="Fix bugs", files_to_modify=["src/calculator.py"], implementation_steps=["step 1"])

    patch = builder.build(task, plan)
    assert isinstance(patch, PatchCandidate)
    assert provider.call_count == 2
    retry_evs = [e for e in events.events if e["event_type"] == "BUILD_RETRY_TRIGGERED"]
    assert len(retry_evs) == 1

def test_builder_fails_closed_when_retry_exhausted():
    bad_json = '{"changed_files": ["src/calculator.py"], "diff": "--- a/src/calculator.py\\n+++ b/src/calculator.py\\n@@ ... @@\\n"}'
    events = EventRecorder("test-builder-fail")
    provider = MockProvider([bad_json, bad_json])
    builder = BuilderAgent(tools=None, model_provider=provider, events=events)
    task = TaskContract(task_id="t1", repository_id="r1", base_commit_or_snapshot="s1", task_description="d")
    plan = ArchitectPlan(objective="Fix bugs", files_to_modify=["src/calculator.py"], implementation_steps=["step 1"])

    result = builder.build(task, plan)
    assert result == OperationalResult.MODEL_FAILURE
    assert provider.call_count == 2

def test_repairer_handles_thinking_trace_and_markdown_blocks():
    output_with_thinking = (
        "Here's my thought process:\n"
        "Let's check the schema: { 'some_key': 'not_the_patch' }\n"
        "Now I will generate the response:\n"
        "```json\n"
        "{\n"
        '  "changed_files": ["src/calculator.py"],\n'
        '  "diff": "--- a/src/calculator.py\\n+++ b/src/calculator.py\\n@@ -1,2 +1,3 @@\\n-old\\n+new\\n context\\n",\n'
        '  "target_failure": "Zero division",\n'
        '  "reasoning_summary": "Added check"\n'
        "}\n"
        "```\n"
    )
    provider = MockProvider([output_with_thinking])
    repairer = RepairerAgent(tools=None, model_provider=provider)
    task = TaskContract(task_id="t1", repository_id="r1", base_commit_or_snapshot="s1", task_description="d")
    current_patch = PatchCandidate(patch_id="p0", task_id="t1", base_commit_or_snapshot="s1", diff="--- a/src/calculator.py\n+++ b/src/calculator.py\n@@ -1 +1 @@\n-x\n+y\n")

    result = repairer.repair(task, current_patch, counterexample_text="ZeroDivisionError")
    assert isinstance(result, RepairCandidate)
    assert result.changed_files == ["src/calculator.py"]
    assert "--- a/src/calculator.py" in result.diff

def test_builder_handles_thinking_trace_and_markdown_blocks():
    output_with_thinking = (
        "Thinking process:\n"
        "Looking at parts = {1: 'x'}\n"
        "Here is the result:\n"
        "```json\n"
        "{\n"
        '  "changed_files": ["src/calculator.py"],\n'
        '  "diff": "--- a/src/calculator.py\\n+++ b/src/calculator.py\\n@@ -1,2 +1,3 @@\\n-old\\n+new\\n context\\n"\n'
        "}\n"
        "```\n"
    )
    provider = MockProvider([output_with_thinking])
    builder = BuilderAgent(tools=None, model_provider=provider)
    task = TaskContract(task_id="t1", repository_id="r1", base_commit_or_snapshot="s1", task_description="d")
    plan = ArchitectPlan(objective="Fix bugs", files_to_modify=["src/calculator.py"], implementation_steps=["step 1"])

    patch = builder.build(task, plan)
    assert isinstance(patch, PatchCandidate)
    assert patch.changed_files == ["src/calculator.py"]
    assert "--- a/src/calculator.py" in patch.diff


# ---------------------------------------------------------------------------
# 6. Valid Unified Diff Application via Git Apply
# ---------------------------------------------------------------------------

def test_git_apply_cleanly_applies_normalized_diff(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    src_dir = repo / "src"
    src_dir.mkdir()
    calc_file = src_dir / "calculator.py"

    original_code = (
        "def parse_and_eval(expression: str) -> float:\n"
        "    parts = expression.strip().split()\n"
        "    a_str, op, b_str = parts\n"
        "    a = float(a_str)\n"
        "    b = float(b_str)\n"
        "    if op == \"+\":\n"
        "        return a + b\n"
        "    elif op == \"/\":\n"
        "        return a / b\n"
        "    else:\n"
        "        raise ValueError(f\"Unsupported operator: {op}\")\n"
    )
    calc_file.write_text(original_code, encoding="utf-8")

    # Initialize git repository
    subprocess.run(["git", "init"], cwd=str(repo), check=True, capture_output=True)
    subprocess.run(["git", "config", "core.autocrlf", "false"], cwd=str(repo), check=True, capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=str(repo), check=True, capture_output=True)

    patch_diff = (
        "--- a/src/calculator.py\n"
        "+++ b/src/calculator.py\n"
        "@@ -7,4 +7,6 @@\n"
        "     elif op == \"/\":\n"
        "-        return a / b\n"
        "+        if b == 0:\n"
        "+            raise ValueError(\"Division by zero is not allowed\")\n"
        "+        return a / b\n"
        "     else:\n"
    )

    norm_diff = SandboxClient._normalize_patch_diff(patch_diff)
    patch_path = repo / "repair.patch"
    patch_path.write_text(norm_diff, encoding="utf-8")

    proc = subprocess.run(["git", "apply", "repair.patch"], cwd=str(repo), capture_output=True, text=True)
    assert proc.returncode == 0, f"Git apply failed: {proc.stderr}"

    modified_code = calc_file.read_text(encoding="utf-8")
    assert "raise ValueError(\"Division by zero is not allowed\")" in modified_code
    # Verify Python syntax validity
    compile(modified_code, str(calc_file), "exec")

# ---------------------------------------------------------------------------
# 7. Calculator Contract & Regression Verification
# ---------------------------------------------------------------------------

def test_calculator_contract_and_counterexample_semantics():
    import importlib.util
    calc_path = os.path.join(os.path.dirname(__file__), "..", "data", "projects", "project-32965038cdd3", "src", "calculator.py")
    spec = importlib.util.spec_from_file_location("calculator", calc_path)
    calc_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(calc_mod)
    parse_and_eval = calc_mod.parse_and_eval

    # Valid arithmetic cases
    assert parse_and_eval("10 + 20") == 30.0
    assert parse_and_eval("20 - 5") == 15.0
    assert parse_and_eval("5 * 4") == 20.0
    assert parse_and_eval("10 / 2") == 5.0

    # Counterexample 1: Empty input
    with pytest.raises(ValueError, match="Expression cannot be empty"):
        parse_and_eval("")
    with pytest.raises(ValueError, match="Expression cannot be empty"):
        parse_and_eval("   ")

    # Counterexample 2: Malformed input (token count != 3)
    with pytest.raises(ValueError, match="Expression must have exactly 3 tokens"):
        parse_and_eval("10 +")
    with pytest.raises(ValueError, match="Expression must have exactly 3 tokens"):
        parse_and_eval("10 + 20 30")

    # Unsupported operator
    with pytest.raises(ValueError, match="Unsupported operator"):
        parse_and_eval("10 % 20")
