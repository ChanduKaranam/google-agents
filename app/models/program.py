"""Universities, programs, and the facts research attaches to them.

A `Program` carries a fixed set of allowed fact slots (`PROGRAM_FIELDS`).
An allowlist rather than a free dict, so a hallucinated field name is a
validation error at the boundary — the same reason the profile forbids
extras. Every fact is a `ProgramFact`: value + evidence + status. There is
no way to represent "a deadline with no source" in this model, which is the
point.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.evidence import Evidence, VerificationStatus

# The fact slots research may fill. Adding a capability later = adding a
# slot here, in one place.
PROGRAM_FIELDS: frozenset[str] = frozenset(
    {
        "tuition",
        "tuition_currency",
        "duration",
        "intake",
        "application_deadline",
        "gpa_requirement",
        "english_requirement",
        "gre_requirement",
        "structure",  # thesis / course-based
        "coop_available",
        "scholarships",
        "career_signals",
        "employment_outcomes",
        "salary_evidence",
        "employer_evidence",
        "career_locations",
        "industry_evidence",
        "curriculum",
        "faculty_research",
        "research_labs",
        "location",
        "grading_methodology",
        "other_requirements",
    }
)


class ProgramFact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str
    evidence: Evidence
    status: VerificationStatus = "unverified"
    # A differing prior value from another source is retained here, never
    # silently erased (§31 of the Phase 4 brief).
    conflicts: list[dict] = Field(default_factory=list)


class Program(BaseModel):
    model_config = ConfigDict(extra="forbid")

    university: str
    name: str = Field(description="e.g. 'MSc Computer Science'")
    degree_type: str = ""
    country: str = ""
    city: str = ""
    program_url: str = ""
    facts: dict[str, ProgramFact] = Field(default_factory=dict)

    @field_validator("facts")
    @classmethod
    def _only_allowed_fields(
        cls, facts: dict[str, ProgramFact]
    ) -> dict[str, ProgramFact]:
        unknown = set(facts) - PROGRAM_FIELDS
        if unknown:
            raise ValueError(
                f"unknown program fields {sorted(unknown)}; "
                f"allowed: {sorted(PROGRAM_FIELDS)}"
            )
        return facts

    @property
    def key(self) -> str:
        return f"{self.university.strip().lower()}::{self.name.strip().lower()}"

    def unknown_fields(self) -> list[str]:
        """Fact slots nothing has filled — named, never silently omitted."""
        return sorted(PROGRAM_FIELDS - set(self.facts))
