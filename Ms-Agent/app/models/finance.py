"""Financial facts that are not program facts — scoped, gated, uniform.

Tuition belongs to a program and lives on `Program`. A city's rent, a
country's work rules, a lender's interest rate do not — forcing them into a
program record would fake a scope the source never stated (§29 of the
Phase 7 brief). A `FinanceRecord` holds them at their real scope, reusing
`ProgramFact` (value + evidence + status + conflicts) so every financial
fact in the system has the same evidence shape.

The category set is closed for the same reason `PROGRAM_FIELDS` is: a
hallucinated category name is a validation error, not silently stored data.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.program import ProgramFact

# The financial fact categories research may fill, per scope.
FINANCE_FIELDS: frozenset[str] = frozenset(
    {
        "living_cost",
        "housing",
        "food",
        "transport",
        "utilities",
        "health_insurance",
        "part_time_work_rules",
        "visa_financial_requirement",
        "loan_terms",
        "interest_rate",
        "exchange_rate",
        "external_scholarships",
        "travel_cost",
    }
)

FINANCE_SCOPE_LEVELS = ("city", "country", "provider", "market")


class FinanceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope_level: str = Field(description="city / country / provider / market")
    scope_name: str = Field(description="e.g. 'Toronto', 'Canada', a lender name")
    facts: dict[str, ProgramFact] = Field(default_factory=dict)

    @field_validator("scope_level")
    @classmethod
    def _valid_scope(cls, level: str) -> str:
        if level not in FINANCE_SCOPE_LEVELS:
            raise ValueError(
                f"unknown scope level '{level}'; allowed: {FINANCE_SCOPE_LEVELS}"
            )
        return level

    @field_validator("facts")
    @classmethod
    def _only_allowed_fields(
        cls, facts: dict[str, ProgramFact]
    ) -> dict[str, ProgramFact]:
        unknown = set(facts) - FINANCE_FIELDS
        if unknown:
            raise ValueError(
                f"unknown finance fields {sorted(unknown)}; "
                f"allowed: {sorted(FINANCE_FIELDS)}"
            )
        return facts

    @property
    def key(self) -> str:
        return f"{self.scope_level}::{self.scope_name.strip().lower()}"
