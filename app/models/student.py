"""The student profile — typed, sectioned, everything optional.

Every field is optional because the profile is built progressively from
conversation; a missing value is a fact ("we don't know yet"), never a
default. `extra="forbid"` everywhere so a typo'd field name is an error at
the boundary instead of silently vanishing data.

`Target.country` is canonical for "where they're applying"; `Preferences`
holds the softer constraints (cities, budget, structure). Keeping one home
per fact avoids the two-copies-drift problem.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid")

    def known_fields(self) -> dict[str, object]:
        """Field name → value, for everything actually provided."""
        return {k: v for k, v in self.model_dump().items() if v not in (None, [], {})}


class Personal(_Section):
    name: str | None = None


class Education(_Section):
    degree: str | None = Field(None, description="e.g. Bachelor's")
    major: str | None = Field(None, description="e.g. Computer Science and Engineering")
    institution: str | None = None
    graduation_year: int | None = Field(None, ge=1980, le=2100)
    cgpa: float | None = Field(None, ge=0)
    grading_scale: str | None = Field(
        None, description="e.g. '10' for CGPA/10, '4' for GPA/4"
    )


class TestScores(_Section):
    ielts: float | None = Field(None, ge=0, le=9)
    toefl: int | None = Field(None, ge=0, le=120)
    gre: int | None = Field(None, ge=260, le=340)


class Experience(_Section):
    work_experience_months: int | None = Field(None, ge=0)
    internships: list[str] = Field(default_factory=list)


class Research(_Section):
    publications: int | None = Field(None, ge=0)
    research_interests: list[str] = Field(default_factory=list)


class Projects(_Section):
    projects: list[str] = Field(default_factory=list)


class Technical(_Section):
    skills: list[str] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)


class Preferences(_Section):
    cities: list[str] = Field(default_factory=list)
    budget: float | None = Field(None, ge=0)
    budget_currency: str | None = None
    university_size: str | None = None
    program_type: str | None = Field(None, description="thesis / course-based / co-op")
    thesis_preference: bool | None = None
    coop_preference: bool | None = None
    scholarship_required: bool | None = None
    funding_plan: str | None = Field(
        None, description="e.g. family / loan / scholarship / mixed"
    )


class Target(_Section):
    degree: str | None = Field(None, description="e.g. MS")
    country: str | None = None
    intake: str | None = Field(None, description="e.g. Fall 2027")
    specialization: str | None = None
    career_goal: str | None = Field(
        None, description="e.g. industry SWE / ML engineer / research / PhD"
    )


class StudentProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    personal: Personal = Field(default_factory=Personal)
    education: Education = Field(default_factory=Education)
    test_scores: TestScores = Field(default_factory=TestScores)
    technical: Technical = Field(default_factory=Technical)
    experience: Experience = Field(default_factory=Experience)
    research: Research = Field(default_factory=Research)
    projects: Projects = Field(default_factory=Projects)
    preferences: Preferences = Field(default_factory=Preferences)
    target: Target = Field(default_factory=Target)

    def known(self) -> dict[str, dict[str, object]]:
        """Section → known fields, empty sections omitted."""
        out: dict[str, dict[str, object]] = {}
        for section_name in type(self).model_fields:
            section: _Section = getattr(self, section_name)
            fields = section.known_fields()
            if fields:
                out[section_name] = fields
        return out


class DomainInference(BaseModel):
    """A specialization the evidence *suggests* — never a stated fact.

    Inference lives in its own channel so it can never be mistaken for
    something the student said (§49 of the V2 brief: the categories must
    not blur). It becomes a profile fact only when the student confirms it.
    """

    model_config = ConfigDict(extra="forbid")

    domain: str = Field(description="e.g. AI/ML, NLP, Data Science")
    confidence: float = Field(ge=0.0, le=1.0)
    basis: list[str] = Field(
        default_factory=list, description="The evidence, e.g. '3 ML projects'"
    )


class ProfileUpdate(BaseModel):
    """What an extractor proposes: stated facts, doubts, and inferences —
    in three separate channels.

    The agent extracts; it never writes. `update_profile` merges this into
    the stored profile deterministically. Anything the agent was unsure
    about goes in `ambiguities` — a question for the student, not a guess.
    `inferred_domains` carries what a resume *suggests*; those never enter
    profile fields until confirmed.
    """

    model_config = ConfigDict(extra="forbid")

    profile: StudentProfile = Field(default_factory=StudentProfile)
    ambiguities: list[str] = Field(default_factory=list)
    inferred_domains: list[DomainInference] = Field(default_factory=list)
