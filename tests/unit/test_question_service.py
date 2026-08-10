"""The question priority engine: one question, intent-aware, gap-honest."""

from __future__ import annotations

from app.models.student import StudentProfile
from app.services.question_service import choose_next_question, readiness


def profile(**sections) -> StudentProfile:
    return StudentProfile.model_validate(sections)


def test_an_empty_profile_starts_with_the_country() -> None:
    question = choose_next_question(StudentProfile())
    assert question["field"] == "target.country"
    assert question["why"]
    assert question["suggested_phrasing"]


def test_known_fields_are_never_asked_again() -> None:
    p = profile(target={"country": "Canada"})
    assert choose_next_question(p)["field"] != "target.country"


def test_affordability_intent_promotes_budget_to_the_front() -> None:
    p = profile(target={"country": "Canada"})
    generic = choose_next_question(p, "")
    affordable = choose_next_question(p, "FIND_AFFORDABLE")
    assert generic["field"].startswith("education.")
    assert affordable["field"] == "preferences.budget"


def test_eligibility_intent_promotes_scores() -> None:
    p = profile(
        education={"cgpa": 8.2, "grading_scale": "10"},
        target={"country": "Canada"},
    )
    assert choose_next_question(p, "CHECK_ELIGIBILITY")["field"] == (
        "test_scores.ielts"
    )


def test_research_intent_promotes_research_interests() -> None:
    assert (
        choose_next_question(StudentProfile(), "FIND_RESEARCH_PROGRAMS")["field"]
        == "research.research_interests"
    )


def test_an_unknown_intent_falls_back_to_the_generic_order() -> None:
    assert choose_next_question(StudentProfile(), "MAKE_ME_COFFEE")["field"] == (
        "target.country"
    )


def test_toefl_satisfies_the_english_question() -> None:
    """With everything before the English slot known and a TOEFL on file,
    the engine must skip straight past the IELTS question."""
    p = profile(
        education={
            "degree": "B.Tech",
            "major": "CSE",
            "cgpa": 8.2,
            "grading_scale": "10",
        },
        test_scores={"toefl": 100},
        target={
            "country": "Canada",
            "specialization": "AI/ML",
            "intake": "Fall 2027",
        },
        preferences={"budget": 4000000},
    )
    question = choose_next_question(p)
    assert question["field"] == "test_scores.gre"


def test_readiness_tiers_grow_with_the_profile() -> None:
    empty = readiness(StudentProfile())
    assert empty["level"] == "insufficient"

    basic = readiness(
        profile(
            education={"major": "CSE", "cgpa": 8.2, "grading_scale": "10"},
            target={"country": "Canada", "specialization": "AI/ML"},
        )
    )
    assert basic["level"] == "basic"
    assert basic["basic_recommendations"]["complete"] is True
    assert basic["strong_recommendations"]["complete"] is False
    assert 0 < basic["percent"] < 100


def test_readiness_names_what_is_missing() -> None:
    tier = readiness(StudentProfile())["basic_recommendations"]
    assert "target.country" in tier["missing"]
    assert "education.cgpa" in tier["missing"]
