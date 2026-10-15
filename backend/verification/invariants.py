import hashlib
from typing import Callable, Dict, Tuple, Optional
from backend.verification.models import InvariantResultStatus, InvariantEvaluation

class DeterministicInvariantEngine:
    def __init__(self):
        self._evaluators: Dict[str, Callable] = {}
        
    def register_evaluator(self, invariant_id: str, evaluator: Callable[..., Tuple[InvariantResultStatus, str, str]]):
        self._evaluators[invariant_id] = evaluator

    def evaluate(self, invariant_id: str, description: str, **kwargs) -> InvariantEvaluation:
        if invariant_id not in self._evaluators:
            return InvariantEvaluation(
                invariant_id=invariant_id,
                description=description,
                result=InvariantResultStatus.NOT_EVALUATED,
                failure_reason="No deterministic evaluator registered",
                evidence_hash=""
            )
            
        try:
            result, reason, evidence = self._evaluators[invariant_id](**kwargs)
            ev_hash = hashlib.sha256(evidence.encode('utf-8')).hexdigest()
            return InvariantEvaluation(
                invariant_id=invariant_id,
                description=description,
                result=result,
                failure_reason=reason,
                evidence_hash=ev_hash
            )
        except Exception as e:
            return InvariantEvaluation(
                invariant_id=invariant_id,
                description=description,
                result=InvariantResultStatus.INCONCLUSIVE,
                failure_reason=f"Evaluator crashed: {str(e)}",
                evidence_hash=""
            )
