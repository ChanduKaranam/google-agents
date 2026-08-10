"""Match scoring contracts — the shapes; the arithmetic lives in the service.

`MatchWeights` must sum to 1.0 and is configurable in one place
(`app.config.settings.MATCH_WEIGHTS`). `MatchResult.match_score` is always
produced by deterministic code — the model may explain it, never mint it.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator


class MatchWeights(BaseModel):
    model_config = ConfigDict(extra="forbid")

    academic_fit: float = 0.25
    program_fit: float = 0.20
    research_fit: float = 0.15
    career_fit: float = 0.10
    experience_fit: float = 0.05
    requirements_fit: float = 0.10
    financial_fit: float = 0.10
    preference_fit: float = 0.05

    @model_validator(mode="after")
    def _sums_to_one(self) -> MatchWeights:
        total = sum(self.model_dump().values())
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"match weights must sum to 1.0, got {total}")
        return self


# (minimum score, category) — checked top-down, first hit wins.
DEFAULT_CATEGORY_THRESHOLDS: tuple[tuple[int, str], ...] = (
    (90, "Strong Target"),
    (80, "Target"),
    (70, "Moderate"),
    (60, "Reach"),
    (0, "Low Fit"),
)


class ComponentScore(BaseModel):
    """One weighted dimension, fully transparent.

    `score` is None when the dimension cannot be evaluated (missing data on
    either side). An unevaluable dimension is excluded and renormalized,
    never scored 0 — missing information is not evidence of weakness.
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    score: int | None = Field(None, ge=0, le=100)
    weight: float
    basis: str = Field(description="What was compared, in words")


class MatchResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    university: str
    program: str
    match_score: int = Field(ge=0, le=100)
    category: str
    components: list[ComponentScore]
    strengths: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    missing_requirements: list[str] = Field(default_factory=list)
    reasoning: list[str] = Field(default_factory=list)
    not_an_admission_estimate: bool = Field(
        True,
        description="Always true: a fit score is a planning aid, never an "
        "admission probability.",
    )
