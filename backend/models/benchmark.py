from pydantic import BaseModel, Field
from typing import List
from backend.models.attack import AttackCandidate

class BenchmarkResult(BaseModel):
    strategy_name: str
    total_budget: int
    selected_count: int
    category_coverage: int
    redundancy_rate: float
    average_oracle_strength: float
    total_estimated_cost: float
