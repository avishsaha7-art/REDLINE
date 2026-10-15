from typing import Dict
from backend.models.schemas import ResourceBudget

class GovernanceController:
    def __init__(self, budget: ResourceBudget):
        self.budget = budget
        self.iteration_count = 0
        self.tool_call_count = 0
        self.failed_attempts = 0
        self.attack_cases_count = 0
        self.runtime_seconds = 0

    def is_exhausted(self) -> bool:
        if self.iteration_count >= self.budget.max_iterations:
            return True
        if self.tool_call_count >= self.budget.max_tool_calls:
            return True
        if self.failed_attempts >= self.budget.max_failed_attempts:
            return True
        if self.attack_cases_count >= self.budget.max_attack_cases:
            return True
        return False

    def increment_iteration(self) -> None:
        self.iteration_count += 1

    def increment_tool_calls(self) -> None:
        self.tool_call_count += 1

    def record_failed_attempt(self) -> None:
        self.failed_attempts += 1

    def record_attack_case(self) -> None:
        self.attack_cases_count += 1

    def get_usage(self) -> Dict[str, int]:
        return {
            "iterations": self.iteration_count,
            "tool_calls": self.tool_call_count,
            "failed_attempts": self.failed_attempts,
            "attack_cases": self.attack_cases_count,
        }

    def get_remaining(self) -> Dict[str, int]:
        return {
            "iterations": max(0, self.budget.max_iterations - self.iteration_count),
            "tool_calls": max(0, self.budget.max_tool_calls - self.tool_call_count),
            "failed_attempts": max(0, self.budget.max_failed_attempts - self.failed_attempts),
            "attack_cases": max(0, self.budget.max_attack_cases - self.attack_cases_count),
        }