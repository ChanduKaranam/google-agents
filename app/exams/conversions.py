"""English test score comparison — a linking table, never an equivalence.

The IELTS↔TOEFL bands below follow the commonly used ETS linking ranges.
They are a *comparison* aid: programs set their own equivalences, and the
result says so on every use (§7 of the Phase 3 brief). Scores outside the
table stay unknown rather than extrapolated.
"""

from __future__ import annotations

from typing import Any

# IELTS overall band → commonly linked TOEFL iBT total range.
_IELTS_TO_TOEFL: dict[float, str] = {
    9.0: "118-120",
    8.5: "115-117",
    8.0: "110-114",
    7.5: "102-109",
    7.0: "94-101",
    6.5: "79-93",
    6.0: "60-78",
    5.5: "46-59",
    5.0: "35-45",
}

_SUPPORTED = {("ielts", "toefl")}

_WARNINGS = [
    "A commonly used linking-table comparison — not an official score "
    "conversion, and not any program's own equivalence.",
    "Programs publish their own accepted scores per test; the program page decides.",
]


def compare_english_scores(
    from_exam: str, score: float, to_exam: str
) -> dict[str, Any]:
    """Compare a score across English tests via the linking table."""
    pair = (str(from_exam).casefold(), str(to_exam).casefold())
    inputs = {"from_exam": pair[0], "score": score, "to_exam": pair[1]}
    if pair not in _SUPPORTED:
        return {
            "calculation_type": "english_score_comparison",
            "status": "invalid",
            "inputs": inputs,
            "message": (
                "Only IELTS→TOEFL comparison is supported in this table; "
                "other pairs have no commonly used linking."
            ),
        }
    linked = _IELTS_TO_TOEFL.get(round(float(score) * 2) / 2)
    if linked is None:
        return {
            "calculation_type": "english_score_comparison",
            "status": "unknown",
            "inputs": inputs,
            "message": (
                f"No linking-table entry covers IELTS {score}; no "
                "comparison is offered rather than an extrapolation."
            ),
        }
    return {
        "calculation_type": "english_score_comparison",
        "status": "comparison",
        "inputs": inputs,
        "method": "commonly used IELTS↔TOEFL linking table",
        "result": linked,
        "unit": "TOEFL iBT total (range)",
        "warnings": list(_WARNINGS),
    }
