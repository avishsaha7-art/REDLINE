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
            "All list fields MUST be JSON arrays of strings (e.g. [\"item 1\", \"item 2\"]). Do NOT output single strings for list fields.\n"
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
            provider_name = getattr(self.model_provider, "provider_name", getattr(self.model_provider, "provider", "unknown"))
            self.events.record_event("MODEL_CALL_STARTED", {"agent": "ArchitectAgent", "provider": provider_name})
        
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
        
        content = content.strip()
        if "```json" in content:
            start = content.find("```json") + 7
            end = content.find("```", start)
            if end != -1:
                content = content[start:end].strip()
        elif "```" in content:
            start = content.find("```") + 3
            end = content.find("```", start)
            if end != -1:
                content = content[start:end].strip()

        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            first_brace = content.find("{")
            last_brace = content.rfind("}")
            if first_brace != -1 and last_brace > first_brace:
                try:
                    data = json.loads(content[first_brace:last_brace + 1])
                except json.JSONDecodeError as err:
                    if self.events:
                        self.events.record_event("ARCHITECT_OUTPUT_PARSE_FAILED", {"error": str(err)})
                    return OperationalResult.MODEL_FAILURE
            else:
                if self.events:
                    self.events.record_event("ARCHITECT_OUTPUT_PARSE_FAILED", {"error": "No JSON object found in response"})
                return OperationalResult.MODEL_FAILURE

        if not isinstance(data, dict):
            if self.events:
                self.events.record_event("ARCHITECT_SCHEMA_VALIDATION_FAILED", {"error": "Root JSON must be an object"})
            return OperationalResult.MODEL_FAILURE

        try:
            plan = ArchitectPlan(**data)
        except ValidationError as e:
            if self.events:
                self.events.record_event("ARCHITECT_SCHEMA_VALIDATION_FAILED", {"error": str(e)})
            return OperationalResult.MODEL_FAILURE
            
        for path in plan.files_to_modify:
            if task.allowed_scope and path not in task.allowed_scope:
                return OperationalResult.POLICY_BLOCKED
                
        return plan
