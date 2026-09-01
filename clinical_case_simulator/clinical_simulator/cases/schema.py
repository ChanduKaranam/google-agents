"""Pydantic models for the hidden case state (research doc, section 5).

The whole point of these models is the split between what the *patient* knows
and what the *simulator* knows.  `Case.patient_view()` returns only the subset a
real patient could plausibly report; examination findings, investigation
results, the rubric and the final diagnosis never enter the patient agent's
prompt.  That separation is what stops the simulator from answer-dumping.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class Patient(BaseModel):
    name: str
    age: int
    sex: str
    occupation: str = ""
    background: str = ""


class Persona(BaseModel):
    """Behavioural rules for the virtual patient (research doc, section 16)."""

    speech_style: str = "Plain, everyday language. Short sentences."
    emotional_state: str = "Mildly worried but cooperative."
    education_level: str = "Lay person with no medical training."
    knows_not: list[str] = Field(
        default_factory=list,
        description="Things this patient genuinely does not know if asked.",
    )
    volunteers_only_if_asked: bool = True
    quirks: list[str] = Field(default_factory=list)


class PresentIllness(BaseModel):
    onset: str = ""
    site: str = ""
    character: str = ""
    radiation: str = ""
    duration: str = ""
    severity: str = ""
    timing: str = ""
    aggravating: str = ""
    relieving: str = ""
    associated: list[str] = Field(default_factory=list)
    progression: str = ""


class History(BaseModel):
    present_illness: PresentIllness = Field(default_factory=PresentIllness)
    past_medical: list[str] = Field(default_factory=list)
    medications: list[str] = Field(default_factory=list)
    allergies: list[str] = Field(default_factory=list)
    family: list[str] = Field(default_factory=list)
    social: list[str] = Field(default_factory=list)
    review_of_systems_positive: list[str] = Field(default_factory=list)
    review_of_systems_negative: list[str] = Field(default_factory=list)


class Finding(BaseModel):
    """One examination manoeuvre or one investigation."""

    id: str
    label: str
    aliases: list[str] = Field(default_factory=list)
    result: str
    # Investigations only: used to teach cost/appropriateness of ordering.
    tier: Literal["bedside", "first-line", "second-line", "specialist", ""] = ""
    appropriate: bool = True
    note: str = ""


class DifferentialItem(BaseModel):
    dx: str
    status: Literal["correct", "plausible", "must-exclude", "incorrect"]
    aliases: list[str] = Field(default_factory=list)
    why: str = ""
    excluded_by: list[str] = Field(
        default_factory=list,
        description=(
            "Ids of examinations or investigations in THIS case that let a "
            "student actually act on this diagnosis. Required for must-exclude "
            "items: telling a student to rule something out while giving them "
            "no way to do it marks them down for the case author's omission."
        ),
    )


class RubricItem(BaseModel):
    id: str
    label: str
    keywords: list[str] = Field(default_factory=list)
    weight: int = 1
    critical: bool = False
    teaching_note: str = ""


class Rubric(BaseModel):
    history: list[RubricItem] = Field(default_factory=list)
    examination: list[RubricItem] = Field(default_factory=list)
    investigations: list[RubricItem] = Field(default_factory=list)


class Provenance(BaseModel):
    author: str = ""
    reviewed_by: str = ""
    review_date: str = ""
    status: Literal["draft", "expert-reviewed", "retired"] = "draft"
    references: list[str] = Field(default_factory=list)


class Case(BaseModel):
    case_id: str
    title: str
    specialty: str = "Internal Medicine"
    difficulty: int = Field(ge=1, le=4)
    setting: str = ""
    opening_brief: str

    patient: Patient
    persona: Persona = Field(default_factory=Persona)
    chief_complaint: str
    history: History = Field(default_factory=History)

    examination: list[Finding] = Field(default_factory=list)
    investigations: list[Finding] = Field(default_factory=list)

    differentials: list[DifferentialItem] = Field(default_factory=list)
    final_diagnosis: str
    diagnosis_reasoning: str = ""
    critical_clues: list[str] = Field(default_factory=list)
    red_flags: list[str] = Field(default_factory=list)

    rubric: Rubric = Field(default_factory=Rubric)
    hints: list[str] = Field(default_factory=list)
    teaching_points: list[str] = Field(default_factory=list)
    revision_topics: list[str] = Field(default_factory=list)

    # Level 4 cases only: information that appears after N student turns or
    # after a specific action, so the case evolves with the student's decisions.
    evolution: list[dict[str, Any]] = Field(default_factory=list)

    provenance: Provenance = Field(default_factory=Provenance)

    # ------------------------------------------------------------------
    # Views
    # ------------------------------------------------------------------
    def patient_view(self) -> dict[str, Any]:
        """Everything the virtual patient is allowed to know about itself.

        Deliberately excludes: examination findings, investigation results,
        differentials, final diagnosis, critical clues, red flags, rubric,
        hints and teaching points.
        """
        h = self.history
        return {
            "who_you_are": self.patient.model_dump(),
            "how_you_speak": self.persona.model_dump(),
            "why_you_came": self.chief_complaint,
            "your_current_problem": h.present_illness.model_dump(),
            "your_past_illnesses": h.past_medical,
            "your_medicines": h.medications,
            "your_allergies": h.allergies,
            "your_family": h.family,
            "your_daily_life": h.social,
            "other_things_you_have_noticed": h.review_of_systems_positive,
            "things_you_have_NOT_noticed": h.review_of_systems_negative,
        }

    def educator_view(self) -> dict[str, Any]:
        """Full state, for the evaluator and for `reveal` after the case ends."""
        return self.model_dump()

    def rubric_items(self) -> list[tuple[str, RubricItem]]:
        return (
            [("history", i) for i in self.rubric.history]
            + [("examination", i) for i in self.rubric.examination]
            + [("investigations", i) for i in self.rubric.investigations]
        )
