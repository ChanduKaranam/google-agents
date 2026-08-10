"""Phase 3 — academic and exam-score calculations.

The first principle (§3): no universal conversion exists. Every result
names its method, its inputs, and its status (`methodology_based` when a
researched methodology backs it, `estimate` otherwise) — and an estimate
can never masquerade as an official equivalence.
"""

from __future__ import annotations

from app.calc.academic import convert_academic_score, weighted_gpa
from app.exams.conversions import compare_english_scores
from app.exams.requirements import compare_score, interpret_requirement

# --- GPA / scale conversion (§4-5, §11) --------------------------------------


def test_linear_conversion_is_labeled_an_estimate() -> None:
    result = convert_academic_score(8.2, "10", "4")
    assert result["status"] == "estimate"
    assert result["result"] == 3.28
    assert "linear" in result["method"].casefold()
    assert any("not an official" in w.casefold() for w in result["warnings"])


def test_percentage_conversions_work_both_ways() -> None:
    to_pct = convert_academic_score(8.2, "10", "100")
    assert to_pct["result"] == 82.0
    back = convert_academic_score(82, "100", "10")
    assert back["result"] == 8.2


def test_a_researched_methodology_changes_method_and_status() -> None:
    result = convert_academic_score(
        8.2,
        "10",
        "100",
        methodology="Multiply CGPA by 9.5 per the university's notice",
    )
    assert result["status"] == "methodology_based"
    assert result["result"] == 77.9
    assert "9.5" in result["method"]


def test_an_unparseable_methodology_falls_back_honestly() -> None:
    result = convert_academic_score(
        8.2, "10", "100", methodology="See the registrar for details"
    )
    assert result["status"] == "estimate"  # fallback, clearly labeled
    assert any("methodology" in w.casefold() for w in result["warnings"])


def test_invalid_inputs_are_refused_not_fixed() -> None:
    assert convert_academic_score(-1, "10", "4")["status"] == "invalid"
    assert convert_academic_score(11, "10", "4")["status"] == "invalid"
    assert convert_academic_score(8.2, "banana", "4")["status"] == "invalid"


def test_inputs_and_scales_are_always_visible() -> None:
    result = convert_academic_score(8.2, "10", "4")
    assert result["inputs"] == {"value": 8.2, "from_scale": "10", "to_scale": "4"}


# --- Weighted GPA (§12) ------------------------------------------------------


def test_weighted_gpa_is_credit_weighted() -> None:
    result = weighted_gpa([(9.0, 4), (7.0, 2)])
    assert result["status"] == "exact"
    assert result["result"] == round((9.0 * 4 + 7.0 * 2) / 6, 2)


def test_weighted_gpa_refuses_zero_or_negative_credits() -> None:
    assert weighted_gpa([(9.0, 0)])["status"] == "invalid"
    assert weighted_gpa([(9.0, -2)])["status"] == "invalid"
    assert weighted_gpa([])["status"] == "invalid"


# --- English test comparison (§7) --------------------------------------------


def test_ielts_to_toefl_uses_the_linking_table_with_caveats() -> None:
    result = compare_english_scores("ielts", 7.0, "toefl")
    assert result["status"] == "comparison"
    assert result["result"] == "94-101"
    assert "not an official" in " ".join(result["warnings"]).casefold()


def test_unmapped_scores_stay_unknown() -> None:
    result = compare_english_scores("ielts", 4.0, "toefl")
    assert result["status"] == "unknown"


def test_unsupported_pairs_are_refused() -> None:
    result = compare_english_scores("ielts", 7.0, "gre")
    assert result["status"] == "invalid"


# --- Score gaps (§9, extends Phase 2) ----------------------------------------


def test_the_overall_gap_is_quantified() -> None:
    requirement = interpret_requirement("IELTS overall 7.5 required")
    result = compare_score(requirement, overall=7.0, lowest_section=None)
    assert result["verdict"] == "below_stated_minimum"
    assert result["gap"] == 0.5


def test_the_section_gap_is_quantified_separately() -> None:
    requirement = interpret_requirement("IELTS overall 6.5 with no band below 6.5")
    result = compare_score(requirement, overall=7.0, lowest_section=6.0)
    assert result["verdict"] == "below_stated_minimum"
    assert result["section_gap"] == 0.5


def test_meeting_the_requirement_has_no_gap() -> None:
    requirement = interpret_requirement("IELTS overall 6.5 required")
    result = compare_score(requirement, overall=7.0, lowest_section=None)
    assert result.get("gap") in (None, 0)
