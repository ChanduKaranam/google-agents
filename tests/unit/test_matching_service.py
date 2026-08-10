"""The matching engine: deterministic, transparent, honest about gaps."""

from __future__ import annotations

from app.models import Evidence, Program, ProgramFact, StudentProfile
from app.services.matching_service import (
    calculate_match_score,
    categorize,
    gpa_on_4_scale,
)


def fact(value: str, domain: str = "utoronto.ca") -> ProgramFact:
    return ProgramFact(
        value=value, evidence=Evidence(source_domain=domain), status="verified"
    )


def strong_profile() -> StudentProfile:
    return StudentProfile.model_validate(
        {
            "education": {
                "major": "Computer Science and Engineering",
                "cgpa": 8.2,
                "grading_scale": "10",
            },
            "test_scores": {"ielts": 7.5},
            "target": {
                "degree": "MS",
                "country": "Canada",
                "specialization": "Computer Science",
            },
        }
    )


def toronto_cs() -> Program:
    return Program(
        university="University of Toronto",
        name="MSc Computer Science",
        country="Canada",
        facts={
            "gpa_requirement": fact("3.0/4.0 minimum"),
            "english_requirement": fact("IELTS 7.0"),
        },
    )


# --- GPA normalization ------------------------------------------------------


def test_gpa_scale_rules_are_deterministic() -> None:
    assert gpa_on_4_scale(8.2, "10") == 3.28
    assert gpa_on_4_scale(3.5, "4") == 3.5
    assert gpa_on_4_scale(85, "100") == 3.4
    assert gpa_on_4_scale(None, "10") is None
    # Without a scale: inferred from magnitude, still fixed rules.
    assert gpa_on_4_scale(3.2, None) == 3.2
    assert gpa_on_4_scale(8.0, None) == 3.2


def test_a_cgpa_above_its_scale_is_invalid_not_scored() -> None:
    assert gpa_on_4_scale(8.2, "4") is None


# --- The whole calculation --------------------------------------------------


def test_the_score_is_deterministic() -> None:
    a = calculate_match_score(strong_profile(), toronto_cs())
    b = calculate_match_score(strong_profile(), toronto_cs())
    assert a == b


def test_a_strong_profile_scores_well_with_reasons() -> None:
    result = calculate_match_score(strong_profile(), toronto_cs())
    assert result.match_score >= 80
    assert result.category in ("Target", "Strong Target")
    assert result.strengths
    assert result.missing_requirements == []
    # Every component explains itself in words.
    assert all(c.basis for c in result.components)


def test_missing_data_is_excluded_not_punished() -> None:
    """A profile with only academics must not be dragged down by unknowns."""
    minimal = StudentProfile.model_validate(
        {"education": {"cgpa": 9.0, "grading_scale": "10", "major": "CS"}}
    )
    result = calculate_match_score(minimal, toronto_cs())
    skipped = {c.name for c in result.components if c.score is None}
    assert "research_fit" in skipped
    assert "experience_fit" in skipped
    assert result.match_score >= 60  # renormalized, not zeroed
    assert any("renormalized" in line for line in result.reasoning)


def test_an_english_shortfall_lands_in_missing_requirements() -> None:
    profile = strong_profile()
    profile.test_scores.ielts = 6.0
    result = calculate_match_score(profile, toronto_cs())
    assert any("IELTS" in m for m in result.missing_requirements)
    assert result.risks


def test_an_empty_profile_scores_zero_with_nothing_invented() -> None:
    result = calculate_match_score(StudentProfile(), toronto_cs())
    assert result.match_score == 0
    assert all(c.score is None for c in result.components)


def test_categories_follow_the_configured_thresholds() -> None:
    assert categorize(95) == "Strong Target"
    assert categorize(85) == "Target"
    assert categorize(75) == "Moderate"
    assert categorize(65) == "Reach"
    assert categorize(30) == "Low Fit"


def test_no_admission_probability_language_anywhere() -> None:
    result = calculate_match_score(strong_profile(), toronto_cs())
    rendered = result.model_dump_json().lower()
    assert result.not_an_admission_estimate is True
    assert "chance" not in rendered
    assert "probability" not in rendered
    assert "admission rate" not in rendered
