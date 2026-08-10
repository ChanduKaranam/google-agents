"""Phase 2 — the exams domain: reference, interpretation, comparison.

The load-bearing rule (§1 of the Phase 2 brief): **absence is unknown,
never not_required.** A missing fact, an unparseable sentence, or a
never-researched program must all surface as `unknown` — the six statuses
are an enum, and only evidence-backed text can select one.
"""

from __future__ import annotations

import pytest

from app.exams.reference import EXAMS, exam_info
from app.exams.requirements import (
    REQUIREMENT_STATUSES,
    compare_score,
    interpret_requirement,
)

# --- The exam reference (static metadata is legitimate; requirements are not)


def test_the_initial_exams_are_covered() -> None:
    for exam_id in ("ielts", "toefl", "pte", "duolingo", "gre", "gmat"):
        assert exam_id in EXAMS, exam_id


def test_exam_info_carries_structure_not_requirements() -> None:
    ielts = exam_info("ielts")
    assert ielts["category"] == "english"
    assert ielts["score_scale"]
    assert ielts["validity_years"] > 0
    # The reference must never claim acceptance or requirement — those are
    # program facts, researched per program.
    rendered = str(ielts).casefold()
    assert "required" not in rendered
    assert "accepted by" not in rendered


def test_unknown_exam_is_an_error_not_a_guess() -> None:
    with pytest.raises(KeyError):
        exam_info("sat")


# --- Requirement interpretation (§6): conservative, deterministic ------------


@pytest.mark.parametrize(
    ("text", "status"),
    [
        ("GRE is required for all applicants", "required"),
        ("GRE scores must be submitted", "required"),
        ("IELTS Academic 7.0 mandatory", "required"),
        ("GRE is optional", "optional"),
        ("GRE scores may be submitted but are not mandatory", "optional"),
        ("GRE recommended but not required", "optional"),
        ("GRE is not required", "not_required"),
        ("The program does not require the GRE", "not_required"),
        ("GRE waived for applicants with a Canadian degree", "conditional"),
        ("GRE required unless the applicant holds an accredited degree", "conditional"),
        ("The GRE requirement is waived", "waived"),
        ("Applicants are encouraged to review the admissions page", "unknown"),
        ("", "unknown"),
    ],
)
def test_status_classification(text: str, status: str) -> None:
    result = interpret_requirement(text)
    assert result["status"] == status
    assert result["status"] in REQUIREMENT_STATUSES


def test_not_required_never_collapses_into_optional() -> None:
    assert interpret_requirement("GRE is not required")["status"] == "not_required"
    assert interpret_requirement("GRE is optional")["status"] == "optional"


def test_minimum_scores_are_extracted_only_when_stated() -> None:
    result = interpret_requirement(
        "IELTS Academic with an overall band of 6.5 and no band below 6.0"
    )
    assert result["min_overall"] == 6.5
    assert result["min_section"] == 6.0

    bare = interpret_requirement("IELTS required")
    assert bare["min_overall"] is None
    assert bare["min_section"] is None


def test_interpretation_carries_its_basis() -> None:
    result = interpret_requirement("GRE is not required")
    assert result["basis"]  # the matched phrasing, for transparency


# --- Score comparison (§17): meets / below / unknown -------------------------


def test_score_meets_stated_minimum() -> None:
    requirement = interpret_requirement("IELTS overall 6.5 required")
    result = compare_score(requirement, overall=7.0, lowest_section=None)
    assert result["verdict"] == "meets_stated_minimum"


def test_score_below_minimum_is_flagged() -> None:
    requirement = interpret_requirement("IELTS overall 7.5 required")
    result = compare_score(requirement, overall=7.0, lowest_section=None)
    assert result["verdict"] == "below_stated_minimum"


def test_unknown_sections_block_a_full_eligibility_claim() -> None:
    requirement = interpret_requirement("IELTS overall 6.5 with no band below 6.0")
    result = compare_score(requirement, overall=7.0, lowest_section=None)
    assert result["verdict"] == "meets_overall_sections_unknown"
    assert "section" in result["note"].casefold()


def test_known_sections_complete_the_comparison() -> None:
    requirement = interpret_requirement("IELTS overall 6.5 with no band below 6.0")
    ok = compare_score(requirement, overall=7.0, lowest_section=6.5)
    low = compare_score(requirement, overall=7.0, lowest_section=5.5)
    assert ok["verdict"] == "meets_stated_minimum"
    assert low["verdict"] == "below_stated_minimum"


def test_no_stated_minimum_means_unknown_not_pass() -> None:
    requirement = interpret_requirement("IELTS required")
    result = compare_score(requirement, overall=7.0, lowest_section=None)
    assert result["verdict"] == "requirement_stated_without_minimum"


def test_no_score_yields_a_gap_when_required() -> None:
    requirement = interpret_requirement("IELTS overall 6.5 required")
    result = compare_score(requirement, overall=None, lowest_section=None)
    assert result["verdict"] == "score_missing"
