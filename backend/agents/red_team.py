import json
import uuid
import hashlib
from typing import List, Dict, Optional, Any
from pydantic import ValidationError

from backend.models.schemas import TaskContract, PatchCandidate
from backend.models.attack import AttackCandidate, AttackType, OracleType, RiskLevel, AttackResourceBudget
from backend.models.provider import ModelProvider, ModelProviderError
from backend.orchestrator.events import EventRecorder

class RedTeamAgent:
    def __init__(self, model_provider: Optional[ModelProvider] = None, events: Optional[EventRecorder] = None):
        self.model_provider = model_provider
        self.events = events

    def generate_attacks(
        self, 
        task: TaskContract, 
        patch: PatchCandidate, 
        untrusted_context: str = ""
    ) -> List[AttackCandidate]:
        candidates: List[AttackCandidate] = []
        
        # 1. Deterministic generation
        deterministic_candidates = self._generate_deterministic_attacks(task, patch)
        candidates.extend(deterministic_candidates)
        
        # 2. LLM generation (if available)
        if self.model_provider:
            model_candidates = self._generate_model_attacks(task, patch, untrusted_context)
            candidates.extend(model_candidates)
            
        # 3. Validation and Deduplication
        valid_attacks = []
        seen_fingerprints = set()
        for attack in candidates:
            # Validate resource limits
            if attack.resource_budget.max_runtime_ms > 60000 or attack.resource_budget.max_memory_mb > 1024:
                if self.events:
                    self.events.record_event("ATTACK_VALIDATION_FAILED", {"attack_id": attack.attack_id, "reason": "resource_budget"})
                continue
            
            # Deduplicate
            fingerprint = attack.deterministic_fingerprint
            if fingerprint not in seen_fingerprints:
                seen_fingerprints.add(fingerprint)
                valid_attacks.append(attack)
                
        # 4. Prioritization and Selection
        max_cases = task.resource_budget.max_attack_cases
        selected_attacks, metadata = self._prioritize_attacks(valid_attacks, max_cases)
        
        if self.events:
            self.events.record_event("ATTACKS_SELECTED", {"metadata": [m.model_dump() for m in metadata]})
            
        return selected_attacks

    def _generate_deterministic_attacks(self, task: TaskContract, patch: PatchCandidate) -> List[AttackCandidate]:
        attacks = []
        
        # 1. BOUNDARY attack
        attacks.append(AttackCandidate(
            attack_id=f"ATTACK-{uuid.uuid4().hex[:8].upper()}",
            attack_type=AttackType.BOUNDARY,
            objective="Test empty or null inputs",
            target=task.allowed_scope[0] if task.allowed_scope else "system",
            preconditions=[],
            input_specification="NULL_OR_EMPTY_INPUT",
            execution_strategy="FUNCTION_INPUT",
            expected_failure_signal="Crash or unhandled exception",
            oracle_type=OracleType.TASK_INVARIANT,
            risk_level=RiskLevel.LOW,
            rationale="Deterministic boundary test for null input handling",
            provenance={"generator": "deterministic", "generator_version": "1.0"}
        ))
        
        # 2. INPUT attack
        attacks.append(AttackCandidate(
            attack_id=f"ATTACK-{uuid.uuid4().hex[:8].upper()}",
            attack_type=AttackType.INPUT,
            objective="Test malformed inputs",
            target=task.allowed_scope[0] if task.allowed_scope else "system",
            preconditions=[],
            input_specification="MALFORMED_GARBAGE_DATA",
            execution_strategy="MALFORMED_INPUT",
            expected_failure_signal="Crash",
            oracle_type=OracleType.TASK_INVARIANT,
            risk_level=RiskLevel.LOW,
            rationale="Deterministic malformed input test",
            provenance={"generator": "deterministic", "generator_version": "1.0"}
        ))
        
        # 3. RESOURCE attack
        attacks.append(AttackCandidate(
            attack_id=f"ATTACK-{uuid.uuid4().hex[:8].upper()}",
            attack_type=AttackType.RESOURCE,
            objective="Test large inputs",
            target=task.allowed_scope[0] if task.allowed_scope else "system",
            preconditions=[],
            input_specification="A" * 10000,
            execution_strategy="MUTATION_CASE",
            expected_failure_signal="Timeout or OOM",
            oracle_type=OracleType.TASK_INVARIANT,
            risk_level=RiskLevel.MEDIUM,
            rationale="Deterministic resource exhaustion test",
            provenance={"generator": "deterministic", "generator_version": "1.0"}
        ))
        
        return attacks

    def _generate_model_attacks(self, task: TaskContract, patch: PatchCandidate, untrusted_context: str) -> List[AttackCandidate]:
        system_prompt = (
            "<TRUSTED_SYSTEM_POLICY>\n"
            "You are the REDLINE Autonomous Red Team Planner.\n"
            "Your objective is to produce adversarial attack hypotheses.\n"
            "You MUST output exactly a JSON array of AttackCandidate objects.\n"
            "Do NOT include any text outside the JSON array.\n"
            "Schema for each object:\n"
            "{\n"
            "  \"attack_id\": \"string\",\n"
            "  \"attack_type\": \"BOUNDARY|INPUT|STATE|REGRESSION|SECURITY|RESOURCE|INVARIANT|MUTATION_DERIVED\",\n"
            "  \"objective\": \"string\",\n"
            "  \"target\": \"string\",\n"
            "  \"preconditions\": [\"string\"],\n"
            "  \"input_specification\": \"string\",\n"
            "  \"execution_strategy\": \"string\",\n"
            "  \"expected_failure_signal\": \"string\",\n"
            "  \"oracle_type\": \"TASK_INVARIANT|TRUSTED_ACCEPTANCE_TEST|REGRESSION_TEST|REFERENCE_IMPLEMENTATION|METAMORPHIC_RELATION|DIFFERENTIAL_EXECUTION|MODEL_GENERATED\",\n"
            "  \"risk_level\": \"LOW|MEDIUM|HIGH\",\n"
            "  \"rationale\": \"string\",\n"
            "  \"metadata\": {\"relevance\": 0.5, \"novelty\": 0.5, \"confidence\": 0.5}\n"
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
            "<UNTRUSTED_REPOSITORY_CONTENT>\n"
            f"{untrusted_context}\n"
            "</UNTRUSTED_REPOSITORY_CONTENT>\n"
            "\n"
            "<UNTRUSTED_PATCH>\n"
            f"{patch.diff}\n"
            "</UNTRUSTED_PATCH>\n"
            "\n"
            "Generate JSON attack candidates now."
        )
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        if self.events:
            self.events.record_event("RED_TEAM_MODEL_CALL_STARTED", {"task_id": task.task_id})
            
        try:
            response = self.model_provider.generate(messages, temperature=0.7)
        except ModelProviderError as e:
            if self.events:
                self.events.record_event("RED_TEAM_MODEL_CALL_FAILED", {"error": e.error_type.value})
            return []
            
        content = response.response_text
        output_hash = hashlib.sha256(content.encode('utf-8')).hexdigest()
        
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
            if self.events:
                self.events.record_event("RED_TEAM_PARSE_FAILED", {"reason": "JSONDecodeError"})
            return []
            
        if not isinstance(data, list):
            if self.events:
                self.events.record_event("RED_TEAM_PARSE_FAILED", {"reason": "Not a JSON array"})
            return []
            
        attacks = []
        for item in data:
            if not isinstance(item, dict):
                continue
            item["provenance"] = {
                "generator": "LLM",
                "model": response.model,
                "provider": response.provider,
                "output_hash": output_hash,
                "patch_hash": patch.diff_sha256
            }
            # Provide defaults for missing mandatory fields if possible, or let pydantic raise ValidationError
            if "attack_id" not in item or not item["attack_id"]:
                item["attack_id"] = f"ATTACK-{uuid.uuid4().hex[:8].upper()}"
                
            try:
                candidate = AttackCandidate(**item)
                attacks.append(candidate)
            except ValidationError as e:
                if self.events:
                    self.events.record_event("RED_TEAM_VALIDATION_FAILED", {"errors": e.errors()})
                continue
                
        return attacks

    def _estimate_cost(self, attack: AttackCandidate) -> float:
        rt_norm = attack.resource_budget.max_runtime_ms / 60000.0
        mem_norm = attack.resource_budget.max_memory_mb / 1024.0
        return min(1.0, (rt_norm * 0.7) + (mem_norm * 0.3))

    def _compute_redundancy_group(self, attack: AttackCandidate) -> str:
        normalized = {
            "attack_type": attack.attack_type.value,
            "target": attack.target
        }
        encoded = json.dumps(normalized, sort_keys=True).encode('utf-8')
        return hashlib.sha256(encoded).hexdigest()

    def _score_attack(self, attack: AttackCandidate, redundancy_counts: Dict[str, int], category_counts: Dict[AttackType, int]) -> 'AttackScore':
        from backend.models.attack import AttackScore
        reasons = []
        
        oracle_map = {
            OracleType.TASK_INVARIANT: 1.0,
            OracleType.TRUSTED_ACCEPTANCE_TEST: 0.9,
            OracleType.METAMORPHIC_RELATION: 0.8,
            OracleType.DIFFERENTIAL_EXECUTION: 0.7,
            OracleType.REFERENCE_IMPLEMENTATION: 0.6,
            OracleType.REGRESSION_TEST: 0.5,
            OracleType.MODEL_GENERATED: 0.2
        }
        oracle_score = oracle_map.get(attack.oracle_type, 0.0)
        reasons.append(f"Oracle {attack.oracle_type.name} -> {oracle_score}")
        
        security_score = 0.0
        if attack.attack_type == AttackType.SECURITY:
            security_score = 1.0
            reasons.append("Security attack -> 1.0")
        elif attack.attack_type == AttackType.RESOURCE:
            security_score = 0.5
            reasons.append("Resource attack -> 0.5")
            
        if attack.risk_level == RiskLevel.HIGH:
            security_score = min(1.0, security_score + 0.3)
            reasons.append("High risk +0.3")
            
        boundary_score = 1.0 if attack.attack_type == AttackType.BOUNDARY else 0.0
        if boundary_score > 0:
            reasons.append("Boundary attack -> 1.0")
            
        relevance_score = attack.metadata.relevance
        novelty_score = attack.metadata.novelty
        
        cost = self._estimate_cost(attack)
        cost_penalty = min(0.2, cost * 0.2)
        reasons.append(f"Cost penalty -> {cost_penalty}")
        
        rg = self._compute_redundancy_group(attack)
        count = redundancy_counts.get(rg, 0)
        redundancy_penalty = min(0.8, count * 0.2)
        reasons.append(f"Redundancy penalty -> {redundancy_penalty}")
        
        cat_count = category_counts.get(attack.attack_type, 0)
        diversity_penalty = min(0.3, cat_count * 0.05)
        reasons.append(f"Diversity penalty -> {diversity_penalty}")
        
        total = (
            (relevance_score * 0.1) +
            (novelty_score * 0.1) +
            (oracle_score * 0.2) +
            (boundary_score * 0.1) +
            (security_score * 0.5) -
            redundancy_penalty -
            cost_penalty -
            diversity_penalty
        )
        total = max(0.0, min(1.0, total))
        
        return AttackScore(
            total_score=total,
            relevance_score=relevance_score,
            novelty_score=novelty_score,
            oracle_strength_score=oracle_score,
            boundary_score=boundary_score,
            security_score=security_score,
            redundancy_penalty=redundancy_penalty,
            cost_penalty=cost_penalty,
            reasons=reasons
        )

    def _prioritize_attacks(self, attacks: List[AttackCandidate], max_budget: int) -> tuple[List[AttackCandidate], list]:
        from backend.models.attack import SelectedAttack
        selected_candidates = []
        selected_metadata = []
        
        redundancy_counts: Dict[str, int] = {}
        category_counts: Dict[AttackType, int] = {}
        
        remaining = list(attacks)
        
        while remaining and len(selected_candidates) < max_budget:
            scored = []
            for a in remaining:
                score_breakdown = self._score_attack(a, redundancy_counts, category_counts)
                scored.append((score_breakdown.total_score, a, score_breakdown))
                
            def sort_key(item):
                total, a, breakdown = item
                cat_priority = 1 if a.attack_type == AttackType.SECURITY else 0
                return (
                    -total,
                    -breakdown.oracle_strength_score,
                    -breakdown.relevance_score,
                    -breakdown.novelty_score,
                    -cat_priority,
                    a.deterministic_fingerprint
                )
                
            scored.sort(key=sort_key)
            
            top_score, best_attack, best_breakdown = scored[0]
            
            selected_candidates.append(best_attack)
            remaining.remove(best_attack)
            
            rg = self._compute_redundancy_group(best_attack)
            redundancy_counts[rg] = redundancy_counts.get(rg, 0) + 1
            category_counts[best_attack.attack_type] = category_counts.get(best_attack.attack_type, 0) + 1
            
            meta = SelectedAttack(
                attack_fingerprint=best_attack.deterministic_fingerprint,
                rank=len(selected_candidates),
                score=top_score,
                category=best_attack.attack_type,
                redundancy_group=rg,
                estimated_cost=self._estimate_cost(best_attack),
                selection_reason="Highest deterministic value",
                score_breakdown=best_breakdown
            )
            selected_metadata.append(meta)
            
        return selected_candidates, selected_metadata
