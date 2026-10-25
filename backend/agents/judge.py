import json
from typing import List
from backend.models.evidence import EvidenceReceipt, JudgeExplanation
from backend.models.provider import ModelProvider
from backend.models.schemas import TaskContract, PatchCandidate

class JudgeAgent:
    def __init__(self, model_provider: ModelProvider):
        self.model_provider = model_provider
        
    def generate_explanation(
        self,
        receipt: EvidenceReceipt,
        task_contract: TaskContract,
        patch: PatchCandidate
    ) -> JudgeExplanation:
        
        system_prompt = f"""<TRUSTED_SYSTEM_POLICY>
You are the REDLINE Judge. Your only role is to explain the provided Evidence Receipt.
You CANNOT change the verdict. The verdict is already decided by the deterministic verification policy.
The evidence is immutable.
You MUST output a JudgeExplanation JSON object adhering exactly to this schema:
{{
  "summary": "<concise factual summary of the verification outcome>",
  "verified_claims": ["<factual claim directly supported by receipt>", ...],
  "failed_claims": ["<factual claim that failed or was not satisfied>", ...],
  "evidence_references": ["<valid ID from execution_ids or attack_fingerprints, or empty list>"],
  "limitations": "<any known bounds, caveats, or unevaluated scopes>",
  "confidence": "<HIGH, MEDIUM, or LOW>"
}}
Do NOT include a "verdict" field; the verdict is already finalized.
Your claims MUST be supported by the evidence in the receipt.
Do not invent evidence IDs. Only reference valid IDs present in execution_ids or attack_fingerprints.
</TRUSTED_SYSTEM_POLICY>

<EVIDENCE_RECEIPT>
{receipt.model_dump_json(indent=2)}
</EVIDENCE_RECEIPT>

<TASK>
{task_contract.task_description}
</TASK>

Output the JudgeExplanation JSON object now:
"""
        messages = [{"role": "system", "content": system_prompt}]
        response = self.model_provider.generate(messages, temperature=0.0)
        
        try:
            content = response.response_text.strip()
            data = None
            try:
                data = json.loads(content)
            except Exception:
                # Fallback 1: Extract from markdown code blocks
                if "```" in content:
                    for block in content.split("```"):
                        block_stripped = block.strip()
                        if block_stripped.startswith("json"):
                            block_stripped = block_stripped[4:].strip()
                        try:
                            data = json.loads(block_stripped)
                            break
                        except Exception:
                            continue
                # Fallback 2: Extract outermost balanced braces
                if data is None:
                    start = content.find("{")
                    end = content.rfind("}")
                    if start != -1 and end != -1 and end > start:
                        try:
                            data = json.loads(content[start:end+1])
                        except Exception:
                            pass

            if data is None or not isinstance(data, dict):
                raise ValueError("No valid JSON object found in model response")

            # Safely normalize single strings into lists for list fields
            for list_field in ("verified_claims", "failed_claims", "evidence_references"):
                if list_field in data and isinstance(data[list_field], str):
                    val = data[list_field].strip()
                    data[list_field] = [val] if val else []

            explanation = JudgeExplanation(**data)
            
            # Additional logic to reject unsupported explanations (e.g. hallucinated IDs)
            if not self._verify_explanation_consistency(receipt, explanation):
                raise ValueError("Explanation consistency check failed. Claims are unsupported or hallucinated.")
                
            return explanation
        except Exception as e:
            raise ValueError(f"Judge output invalid: {e}")
            
    def _verify_explanation_consistency(self, receipt: EvidenceReceipt, explanation: JudgeExplanation) -> bool:
        # Check that all evidence_references exist in the receipt
        valid_ids = set()
        if receipt.structured_observation:
            valid_ids.add(receipt.structured_observation.execution_id)
        if receipt.test_summary:
            for obs in receipt.test_summary.observations:
                valid_ids.add(obs.test_id)
        for inv in receipt.invariant_summary:
            valid_ids.add(inv.invariant_id)
        for sec in receipt.security_summary:
            valid_ids.add(sec.hook_id)
        for ce in receipt.counterexamples:
            valid_ids.add(ce.counterexample_id)
            
        for ref in explanation.evidence_references:
            if ref not in valid_ids and ref not in receipt.attack_fingerprints and ref not in receipt.execution_ids:
                # Reject fake evidence IDs
                return False
                
        # For simplicity, we just do a basic check here.
        # In a real system, you might do deeper NLP checking or strict claim mapping.
        # A simple check: if verdict is not VERIFIED, but the judge says "successfully verified" in summary, we can't easily catch that deterministically without another LLM, but we can check if it explicitly conflicts with scopes.
        
        return True
