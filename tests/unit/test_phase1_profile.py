"""Phase 1 — profile hardening: precedence, backlogs, enrichment.

The behaviors pinned here (updated by the conversational-intelligence
refactor):

* **Precedence resolves cross-source differences silently.** A resume
  CGPA of 8.2 arriving after a conversation CGPA of 8.5 keeps the
  student's value and reports it as `retained` history — the student is
  never asked to reconcile. `user_confirmed` still overrides anything.
  Same-source corrections still win immediately.
* **Backlogs distinguish zero from unknown.** `backlogs=0` is a fact;
  `backlogs=None` is a gap. They must never collapse into each other.
* **Skill/project enrichment is derived, based, and never stated.**
  Derived skills live in provenance metadata with the evidence that
  produced them — they never enter `technical.skills`, and nothing is
  derived without a matching keyword in the text.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.models.student import StudentProfile
from app.services.profile_enrichment import analyze_projects, derive_skills
from app.tools.profile_tools import get_profile, update_profile


class StubToolContext:
    def __init__(self) -> None:
        self.state: dict[str, Any] = {}
        self.invocation_id = "test"
        self.session = SimpleNamespace(events=[])


@pytest.fixture
def context() -> StubToolContext:
    return StubToolContext()


def put(context, source: str, **sections) -> dict:
    return update_profile({"profile": sections}, source, context)


# --- Cross-source precedence (refactor §2-§4) --------------------------------


def test_a_lower_authority_source_is_retained_not_asked_about(
    context: StubToolContext,
) -> None:
    put(context, "user_explicit", education={"cgpa": 8.5})
    result = put(context, "resume", education={"cgpa": 8.2})

    assert result["status"] == "success"
    kept = result["retained"][0]
    assert kept["field"] == "education.cgpa"
    assert kept["kept_value"] == 8.5
    assert kept["kept_source"] == "user_explicit"
    assert kept["incoming_value"] == 8.2
    assert kept["incoming_source"] == "resume"
    # The student's value stands; nothing asks them to reconcile.
    assert get_profile(context)["profile"]["education"]["cgpa"] == 8.5
    assert "conflicts" not in result


def test_a_same_source_correction_still_wins(context: StubToolContext) -> None:
    put(context, "user_explicit", education={"cgpa": 8.5})
    result = put(context, "user_explicit", education={"cgpa": 8.6})
    assert result["retained"] == []
    assert get_profile(context)["profile"]["education"]["cgpa"] == 8.6


def test_user_confirmed_overrides_anything(context: StubToolContext) -> None:
    put(context, "user_explicit", education={"cgpa": 8.5})
    put(context, "resume", education={"cgpa": 8.2})
    result = put(context, "user_confirmed", education={"cgpa": 8.2})
    assert result["retained"] == []
    assert get_profile(context)["profile"]["education"]["cgpa"] == 8.2
    assert get_profile(context)["provenance"]["education.cgpa"]["source"] == (
        "user_confirmed"
    )


def test_resume_filling_a_gap_is_not_retained_history(
    context: StubToolContext,
) -> None:
    put(context, "user_explicit", target={"country": "Canada"})
    result = put(context, "resume", education={"cgpa": 8.2})
    assert result["retained"] == []
    profile = get_profile(context)["profile"]
    assert profile["target"]["country"] == "Canada"  # §5: both survive
    assert profile["education"]["cgpa"] == 8.2


def test_a_differing_institution_is_also_precedence_resolved(
    context: StubToolContext,
) -> None:
    put(context, "user_explicit", education={"institution": "Lendi"})
    result = put(context, "resume", education={"institution": "LIET"})
    assert result["retained"][0]["field"] == "education.institution"
    assert get_profile(context)["profile"]["education"]["institution"] == "Lendi"


# --- Backlogs (§7) -----------------------------------------------------------


def test_backlogs_zero_is_a_fact_not_a_gap(context: StubToolContext) -> None:
    put(context, "user_explicit", education={"backlogs": 0})
    profile = get_profile(context)["profile"]
    assert profile["education"]["backlogs"] == 0


def test_backlogs_unknown_stays_unknown() -> None:
    assert StudentProfile().education.backlogs is None
    known = StudentProfile.model_validate(
        {"education": {"backlogs": 0}}
    ).education.known_fields()
    assert known.get("backlogs") == 0  # zero must survive known() rendering


# --- Deterministic skill derivation (§8) -------------------------------------


def test_skills_are_derived_only_with_a_basis() -> None:
    text = "Built an image classification model using Python, TensorFlow and CNNs."
    derived = derive_skills(text)
    names = {d["skill"] for d in derived}
    assert "Python" in names
    assert "TensorFlow" in names
    assert "Computer Vision" in names  # implied by CNN, with basis
    assert all(d["basis"] for d in derived)
    cv = next(d for d in derived if d["skill"] == "Computer Vision")
    assert "cnn" in " ".join(cv["basis"]).casefold()


def test_unsupported_skills_are_never_derived() -> None:
    text = "Built an image classification model using Python and TensorFlow."
    names = {d["skill"] for d in derive_skills(text)}
    assert "PyTorch" not in names
    assert "AWS" not in names
    assert "Kubernetes" not in names


def test_empty_text_derives_nothing() -> None:
    assert derive_skills("") == []
    assert derive_skills("I enjoy hiking and cooking.") == []


# --- Project analysis (§9) ---------------------------------------------------


def test_projects_are_analyzed_with_evidence() -> None:
    analyses = analyze_projects(
        [
            "Crop Recommendation using machine learning and Python",
            "Personal portfolio website in HTML and CSS",
        ]
    )
    crop, site = analyses
    assert crop["ai_ml_relevant"] is True
    assert "Python" in crop["technologies"]
    assert site["ai_ml_relevant"] is False
    assert crop["research_relevant"] is False  # no research markers → not claimed


def test_research_relevance_needs_research_markers() -> None:
    [analysis] = analyze_projects(
        ["Published a paper on medical image segmentation research"]
    )
    assert analysis["research_relevant"] is True


# --- Enrichment lands in provenance, never in stated skills ------------------


def test_derived_skills_stay_out_of_the_stated_profile(
    context: StubToolContext,
) -> None:
    put(
        context,
        "resume",
        technical={"skills": ["Python"]},
        projects={"projects": ["Image classification with TensorFlow and CNNs"]},
    )
    state = get_profile(context)
    assert state["profile"]["technical"]["skills"] == ["Python"]  # stated only
    derived = {d["skill"] for d in state["derived_skills"]}
    assert "TensorFlow" in derived
    assert all(d["basis"] for d in state["derived_skills"])
