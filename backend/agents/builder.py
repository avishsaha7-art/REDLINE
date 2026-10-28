import json
import uuid
import hashlib
import re
from typing import Optional, Tuple, Dict, Any
from backend.models.schemas import TaskContract, ArchitectPlan, PatchCandidate, OperationalResult
from backend.models.provider import ModelProvider, ModelProviderError
from backend.orchestrator.events import EventRecorder
from backend.sandbox.client import SandboxClient

class BuilderAgent:
    def __init__(self, tools, model_provider: Optional[ModelProvider], events: Optional[EventRecorder] = None):
        self.tools = tools
        self.model_provider = model_provider
        self.events = events

    def _parse_and_validate_builder_output(self, content: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        if not content or not isinstance(content, str):
            return None, "Empty or non-string model output"

        data = None
        # 1. Look for markdown code blocks (from last to first)
        code_blocks = re.findall(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", content)
        for block in reversed(code_blocks):
            try:
                candidate = json.loads(block)
                if isinstance(candidate, dict) and "diff" in candidate and "changed_files" in candidate:
                    data = candidate
                    break
            except Exception:
                pass

        # 2. Backward search for top-level JSON object using raw_decode
        if data is None:
            decoder = json.JSONDecoder()
            brace_indices = [i for i, c in enumerate(content) if c == '{']
            for idx in reversed(brace_indices):
                try:
                    candidate, _ = decoder.raw_decode(content, idx)
                    if isinstance(candidate, dict) and "diff" in candidate and "changed_files" in candidate:
                        data = candidate
                        break
                except Exception:
                    continue

        # 3. Direct parse fallback
        if data is None:
            text = content.strip()
            first_brace = text.find("{")
            last_brace = text.rfind("}")
            if first_brace != -1 and last_brace > first_brace:
                try:
                    candidate = json.loads(text[first_brace:last_brace + 1])
                    if isinstance(candidate, dict):
                        data = candidate
                except json.JSONDecodeError as err:
                    return None, f"JSON decode error: {err}"
            else:
                return None, "No JSON object found in model output"

        if data is None:
            return None, "No valid patch JSON object found in model output"

        if not isinstance(data, dict):
            return None, "Parsed JSON is not an object"

        allowed_keys = {"diff", "changed_files"}
        if set(data.keys()) - allowed_keys:
            return None, f"Forbidden extra fields: {set(data.keys()) - allowed_keys}"

        if not allowed_keys.issubset(set(data.keys())):
            return None, f"Missing required fields: {allowed_keys - set(data.keys())}"

        diff = data.get("diff", "")
        if not isinstance(diff, str) or not diff.strip():
            return None, "Diff is empty"

        norm_diff = SandboxClient._normalize_patch_diff(diff)

        if not norm_diff.startswith("--- "):
            return None, "Diff missing '--- a/<path>' header"
        if not any(l.startswith("+++ ") for l in norm_diff.splitlines()):
            return None, "Diff missing '+++ b/<path>' header"

        has_valid_hunk = any(
            re.match(r"^@@\s+-\d+(?:,\d+)?\s+\+\d+(?:,\d+)?\s+@@", l.strip())
            for l in norm_diff.splitlines()
        )
        if not has_valid_hunk:
            return None, "Diff missing valid hunks (format: @@ -<start>,<count> +<start>,<count> @@)"

        data["diff"] = norm_diff
        return data, None

    def build(self, task: TaskContract, plan: ArchitectPlan, untrusted_context: str = "No file content loaded for Builder stub yet.") -> PatchCandidate | OperationalResult:
        if not self.model_provider:
            return OperationalResult.MODEL_FAILURE

        # Select best candidate file: prefer files_to_modify from plan, then code files in allowed scope
        sample_file = "src/calculator.py"
        candidates = []
        if plan and plan.files_to_modify:
            candidates.extend(plan.files_to_modify)
        if task.allowed_scope and isinstance(task.allowed_scope, list):
            code_files = [f for f in task.allowed_scope if f != "**" and any(f.endswith(ext) for ext in (".py", ".js", ".ts", ".go", ".rs", ".c", ".cpp"))]
            candidates.extend(code_files)
            candidates.extend([f for f in task.allowed_scope if f != "**"])
        if candidates:
            sample_file = candidates[0]

        prompt = (
            "You are the REDLINE Builder.\n"
            "DO NOT include any thinking process, reasoning traces, or markdown explanations.\n"
            "Immediately output ONLY valid JSON matching this schema:\n"
            "{\n"
            f'  "changed_files": ["{sample_file}"],\n'
            f'  "diff": "--- a/{sample_file}\\n+++ b/{sample_file}\\n@@ -28,4 +28,6 @@\\n     elif op == \\\"/\\\":\\n-        return a / b\\n+        if b == 0:\\n+            raise ValueError(\\\"Division by zero is not allowed\\\")\\n+        return a / b\\n     else:\\n"\n'
            "}\n\n"
            "CRITICAL RULES:\n"
            "1. The 'diff' field MUST contain a real unified diff starting with '--- a/' and '+++ b/' with real hunks '@@ -start,count +start,count @@'.\n"
            "2. Copy context lines verbatim from the repository content preserving exact code indentation.\n"
            "3. Only modify files within the allowed scope. Do NOT output dummy or fake text.\n\n"
            f"Task ID: {task.task_id}\n"
            f"Allowed Scope: {task.allowed_scope}\n"
            f"Description: {task.task_description}\n\n"
            f"Plan Objective: {plan.objective}\n"
            f"Files to modify: {plan.files_to_modify}\n"
            f"Implementation steps: {plan.implementation_steps}\n\n"
            f"<UNTRUSTED_REPOSITORY_CONTENT>\n{untrusted_context}\n</UNTRUSTED_REPOSITORY_CONTENT>\n\n"
            "Generate the actual unified diff implementing the plan to fix the code.\n"
            "Output ONLY the JSON patch now starting with {"
        )

        messages = [
            {"role": "system", "content": "You are the REDLINE Builder."},
            {"role": "user", "content": prompt}
        ]

        if self.events:
            provider_name = getattr(self.model_provider, "provider_name", getattr(self.model_provider, "provider", "unknown"))
            self.events.record_event("MODEL_CALL_STARTED", {"agent": "BuilderAgent", "provider": provider_name})

        try:
            response = self.model_provider.generate(messages, temperature=0.0)
        except ModelProviderError as e:
            if self.events:
                self.events.record_event("MODEL_CALL_FAILED", {"agent": "BuilderAgent", "error": e.error_type.value})
            return OperationalResult.MODEL_FAILURE

        content = response.response_text
        output_hash = hashlib.sha256(content.encode('utf-8')).hexdigest()

        if self.events:
            self.events.record_event("MODEL_CALL_COMPLETED", {
                "agent": "BuilderAgent",
                "provider": response.provider,
                "model": response.model,
                "prompt_version": "builder_prompt_v2",
                "request_id": response.provider_request_id or response.request_id,
                "latency": response.latency_ms,
                "input_tokens": response.input_tokens,
                "output_tokens": response.output_tokens,
                "output_hash": output_hash,
                "task_id": task.task_id
            })

        data, err = self._parse_and_validate_builder_output(content)

        # Bounded retry if initial output was malformed
        if (data is None or err) and self.model_provider:
            if self.events:
                self.events.record_event("BUILD_RETRY_TRIGGERED", {"reason": err})
            retry_messages = [
                {"role": "user", "content": f"{prompt}\n\nIMPORTANT: The previous patch attempt was rejected: {err}.\nYou MUST return ONLY a valid JSON object matching the schema with a valid unified diff with real hunks '@@ -start,count +start,count @@'. Return ONLY the JSON now starting with {{"}
            ]
            try:
                retry_response = self.model_provider.generate(retry_messages, temperature=0.0)
                retry_content = retry_response.response_text
                data, retry_err = self._parse_and_validate_builder_output(retry_content)
                if self.events:
                    self.events.record_event("BUILD_RETRY_COMPLETED", {
                        "success": data is not None,
                        "error": retry_err
                    })
            except Exception as retry_exc:
                if self.events:
                    self.events.record_event("BUILD_RETRY_FAILED", {"error": str(retry_exc)})

        if not data:
            if self.events:
                self.events.record_event("BUILDER_OUTPUT_PARSE_FAILED", {"raw_output": content[:200], "error": err or "Validation failed"})
            return OperationalResult.MODEL_FAILURE

        return PatchCandidate(
            patch_id=f"PATCH-{uuid.uuid4().hex[:8].upper()}",
            task_id=task.task_id,
            base_commit_or_snapshot=task.base_commit_or_snapshot,
            diff=data["diff"],
            changed_files=data["changed_files"],
            patch_metadata={"agent": "Builder", "status": "generated"},
            generation_provenance={
                "model": response.model,
                "provider": response.provider,
                "prompt_version": "builder_prompt_v1",
                "output_hash": output_hash
            }
        )
