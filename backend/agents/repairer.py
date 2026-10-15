import json
import uuid
import hashlib
from typing import Optional
from backend.models.schemas import TaskContract, PatchCandidate, OperationalResult, RepairCandidate
from backend.models.provider import ModelProvider, ModelProviderError
from backend.orchestrator.events import EventRecorder

class RepairerAgent:
    def __init__(self, tools, model_provider: Optional[ModelProvider], events: Optional[EventRecorder] = None):
        self.tools = tools
        self.model_provider = model_provider
        self.events = events

    def repair(
        self,
        task: TaskContract,
        current_patch: PatchCandidate,
        counterexample_text: str,
        untrusted_context: str = "No file content loaded for Repairer stub yet."
    ) -> RepairCandidate | OperationalResult:
        if not self.model_provider:
            return OperationalResult.MODEL_FAILURE

        system_prompt = (
            "<TRUSTED_SYSTEM_POLICY>\n"
            "You are the REDLINE Repairer.\n"
            "Your objective is to produce a JSON payload representing a repair patch.\n"
            "You MUST output exactly valid JSON.\n"
            "Do NOT include any text outside the JSON block.\n"
            "Schema:\n"
            "{\n"
            "  \"changed_files\": [\"string\"],\n"
            "  \"diff\": \"string (valid unified diff format)\",\n"
            "  \"target_failure\": \"string (brief description of failure fixed)\",\n"
            "  \"reasoning_summary\": \"string (brief reasoning for the fix)\"\n"
            "}\n"
            "</TRUSTED_SYSTEM_POLICY>"
        )

        user_prompt = (
            "<TRUSTED_TASK>\n"
            f"Task ID: {task.task_id}\n"
            f"Allowed Scope: {task.allowed_scope}\n"
            f"Description: {task.task_description}\n"
            "</TRUSTED_TASK>\n"
            "\n"
            "<TRUSTED_CURRENT_PATCH>\n"
            f"Patch Hash: {current_patch.diff_sha256}\n"
            f"Diff:\n{current_patch.diff}\n"
            "</TRUSTED_CURRENT_PATCH>\n"
            "\n"
            "<UNTRUSTED_DETERMINISTIC_EVIDENCE>\n"
            f"{counterexample_text}\n"
            "</UNTRUSTED_DETERMINISTIC_EVIDENCE>\n"
            "\n"
            "<UNTRUSTED_REPOSITORY_CONTENT>\n"
            f"{untrusted_context}\n"
            "</UNTRUSTED_REPOSITORY_CONTENT>\n"
            "\n"
            "Return the JSON repair patch now."
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        if self.events:
            provider_name = getattr(self.model_provider, "provider_name", getattr(self.model_provider, "provider", "unknown"))
            self.events.record_event("MODEL_CALL_STARTED", {"agent": "RepairerAgent", "provider": provider_name})

        try:
            response = self.model_provider.generate(messages, temperature=0.0)
        except ModelProviderError as e:
            if self.events:
                self.events.record_event("MODEL_CALL_FAILED", {"agent": "RepairerAgent", "error": e.error_type.value})
            return OperationalResult.MODEL_FAILURE

        content = response.response_text
        output_hash = hashlib.sha256(content.encode('utf-8')).hexdigest()

        if self.events:
            self.events.record_event("MODEL_CALL_COMPLETED", {
                "agent": "RepairerAgent",
                "provider": response.provider,
                "model": response.model,
                "prompt_version": "repairer_prompt_v1",
                "request_id": response.provider_request_id or response.request_id,
                "latency": response.latency_ms,
                "input_tokens": response.input_tokens,
                "output_tokens": response.output_tokens,
                "output_hash": output_hash,
                "task_id": task.task_id
            })

        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            return OperationalResult.MODEL_FAILURE

        if not isinstance(data, dict):
            return OperationalResult.MODEL_FAILURE

        # Fail on extra forbidden fields
        allowed_keys = {"diff", "changed_files", "target_failure", "reasoning_summary"}
        if set(data.keys()) - allowed_keys:
            return OperationalResult.MODEL_FAILURE

        if not allowed_keys.issubset(set(data.keys())):
            return OperationalResult.MODEL_FAILURE

        return RepairCandidate(
            repair_id=f"REPAIR-{uuid.uuid4().hex[:8].upper()}",
            base_patch_hash=current_patch.diff_sha256,
            diff=data["diff"],
            changed_files=data["changed_files"],
            target_failure=data["target_failure"],
            reasoning_summary=data["reasoning_summary"]
        )
