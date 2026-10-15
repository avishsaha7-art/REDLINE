import json
import hashlib
from typing import Optional
from pydantic import ValidationError
from backend.models.schemas import TaskContract, ArchitectPlan, OperationalResult
from backend.models.provider import ModelProvider, ModelProviderError
from backend.orchestrator.events import EventRecorder

class ArchitectAgent:
    def __init__(self, tools, model_provider: Optional[ModelProvider], events: Optional[EventRecorder] = None):
        self.tools = tools
        self.model_provider = model_provider
        self.events = events

    def plan(self, task: TaskContract, untrusted_context: str = "No file content loaded for Architect stub yet.") -> ArchitectPlan | OperationalResult:
        if not self.model_provider:
            return OperationalResult.MODEL_FAILURE
            
        system_prompt = (
            "You are the REDLINE Architect.\n"
            "Your objective is to produce a JSON ArchitectPlan.\n"
            "You MUST output exactly valid JSON corresponding to the ArchitectPlan schema.\n"
            "Do NOT include any text outside the JSON block.\n"
            "Schema:\n"
            "{\n"
            "  \"objective\": \"string\",\n"
            "  \"files_to_inspect\": [\"string\"],\n"
            "  \"files_to_modify\": [\"string\"],\n"
            "  \"implementation_steps\": [\"string\"],\n"
            "  \"acceptance_criteria\": [\"string\"],\n"
            "  \"constraints\": [\"string\"],\n"
            "  \"risks\": [\"string\"],\n"
            "  \"expected_tests\": [\"string\"]\n"
            "}\n"
        )
        
        user_prompt = (
            "<TRUSTED_TASK>\n"
            f"Task ID: {task.task_id}\n"
            f"Description: {task.task_description}\n"
            f"Allowed Scope: {task.allowed_scope}\n"
            "</TRUSTED_TASK>\n"
            "\n"
            "<UNTRUSTED_REPOSITORY_CONTENT>\n"
            f"{untrusted_context}\n"
            "</UNTRUSTED_REPOSITORY_CONTENT>\n"
            "\n"
            "Return the JSON ArchitectPlan now."
        )
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        if self.events:
            self.events.record_event("MODEL_CALL_STARTED", {"agent": "ArchitectAgent", "provider": "nebius"})
        
        try:
            response = self.model_provider.generate(messages, temperature=0.0)
        except ModelProviderError as e:
            if self.events:
                self.events.record_event("MODEL_CALL_FAILED", {"agent": "ArchitectAgent", "error": e.error_type.value})
            return OperationalResult.MODEL_FAILURE
            
        content = response.response_text
        
        output_hash = hashlib.sha256(content.encode('utf-8')).hexdigest()
        
        if self.events:
            self.events.record_event("MODEL_CALL_COMPLETED", {
                "agent": "ArchitectAgent",
                "provider": response.provider,
                "model": response.model,
                "prompt_version": "architect_prompt_v1",
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
            plan = ArchitectPlan(**data)
        except (json.JSONDecodeError, ValidationError) as e:
            import traceback; traceback.print_exc()
            return OperationalResult.MODEL_FAILURE
            
        for path in plan.files_to_modify:
            if task.allowed_scope and path not in task.allowed_scope:
                return OperationalResult.POLICY_BLOCKED
                
        return plan
