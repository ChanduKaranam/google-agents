"""Merging is code: existing information survives, updates land, gaps rank."""

from __future__ import annotations

from app.models.student import StudentProfile
from app.services.profile_service import merge_update, missing_important_fields


def lendi_profile() -> StudentProfile:
    return StudentProfile.model_validate(
        {
            "education": {
                "major": "Computer Science and Engineering",
                "institution": "Lendi",
                "cgpa": 8.2,
            },
            "target": {"degree": "MS", "country": "Canada"},
        }
    )


def test_scenario_2_update_keeps_existing_information_intact() -> None:
    """'I graduated in 2026 and I'm targeting Fall 2027.'"""
    update = StudentProfile.model_validate(
        {"education": {"graduation_year": 2026}, "target": {"intake": "Fall 2027"}}
    )
    merged, changed = merge_update(lendi_profile(), update)

    assert merged.education.graduation_year == 2026
    assert merged.target.intake == "Fall 2027"
    # Everything already known survives untouched.
    assert merged.education.cgpa == 8.2
    assert merged.education.institution == "Lendi"
    assert merged.target.country == "Canada"
    assert sorted(changed) == ["education.graduation_year", "target.intake"]


def test_none_in_an_update_never_erases_a_value() -> None:
    merged, changed = merge_update(lendi_profile(), StudentProfile())
    assert merged.education.cgpa == 8.2
    assert changed == []


def test_a_correction_wins_and_is_reported() -> None:
    update = StudentProfile.model_validate({"education": {"cgpa": 8.4}})
    merged, changed = merge_update(lendi_profile(), update)
    assert merged.education.cgpa == 8.4
    assert changed == ["education.cgpa"]


def test_lists_union_without_duplicates() -> None:
    base = StudentProfile.model_validate(
        {"research": {"research_interests": ["ML", "NLP"]}}
    )
    update = StudentProfile.model_validate(
        {"research": {"research_interests": ["nlp", "Systems"]}}
    )
    merged, changed = merge_update(base, update)
    assert merged.research.research_interests == ["ML", "NLP", "Systems"]
    assert changed == ["research.research_interests"]


def test_missing_fields_rank_most_valuable_first() -> None:
    missing = missing_important_fields(StudentProfile())
    assert missing[0]["field"] == "education.cgpa"
    assert all("why" in entry and entry["why"] for entry in missing)


def test_known_fields_drop_out_of_missing() -> None:
    fields = [m["field"] for m in missing_important_fields(lendi_profile())]
    assert "education.cgpa" not in fields
    assert "target.country" not in fields
    assert "education.grading_scale" in fields  # cgpa without scale is ambiguous


def test_a_toefl_score_satisfies_the_english_slot() -> None:
    profile = StudentProfile.model_validate({"test_scores": {"toefl": 100}})
    fields = [m["field"] for m in missing_important_fields(profile)]
    assert "test_scores.ielts" not in fields
