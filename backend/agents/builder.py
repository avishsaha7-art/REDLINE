import json
import uuid
import hashlib
from typing import Optional
from backend.models.schemas import TaskContract, ArchitectPlan, PatchCandidate, OperationalResult
from backend.models.provider import ModelProvider, ModelProviderError
from backend.orchestrator.events import EventRecorder

class BuilderAgent:
    def __init__(self, tools, model_provider: Optional[ModelProvider], events: Optional[EventRecorder] = None):
        self.tools = tools
        self.model_provider = model_provider
        self.events = events

    def build(self, task: TaskContract, plan: ArchitectPlan, untrusted_context: str = "No file content loaded for Builder stub yet.") -> PatchCandidate | OperationalResult:
        if not self.model_provider:
            return OperationalResult.MODEL_FAILURE
            
        system_prompt = (
            "<TRUSTED_SYSTEM_POLICY>\n"
            "You are the REDLINE Builder.\n"
            "Your objective is to produce a JSON payload representing a patch.\n"
            "You MUST output exactly valid JSON.\n"
            "Do NOT include any text outside the JSON block.\n"
            "Schema:\n"
            "{\n"
            "  \"changed_files\": [\"string\"],\n"
            "  \"diff\": \"string (valid unified diff format)\"\n"
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
            "<TRUSTED_ARCHITECT_PLAN>\n"
            f"Objective: {plan.objective}\n"
            f"Files to modify: {plan.files_to_modify}\n"
            f"Implementation steps: {plan.implementation_steps}\n"
            "</TRUSTED_ARCHITECT_PLAN>\n"
            "\n"
            "<UNTRUSTED_REPOSITORY_CONTENT>\n"
            f"{untrusted_context}\n"
            "</UNTRUSTED_REPOSITORY_CONTENT>\n"
            "\n"
            "Return the JSON patch now."
        )
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        if self.events:
            self.events.record_event("MODEL_CALL_STARTED", {"agent": "BuilderAgent", "provider": "nebius"})
        
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
                "prompt_version": "builder_prompt_v1",
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
        allowed_keys = {"diff", "changed_files"}
        if set(data.keys()) - allowed_keys:
            return OperationalResult.MODEL_FAILURE
            
        if "diff" not in data or "changed_files" not in data:
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
