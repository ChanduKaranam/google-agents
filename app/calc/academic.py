"""Academic score calculations — explicit scales, honest methods.

No universal CGPA conversion exists (§3/§5 of the Phase 3 brief). Every
result therefore names its method and status:

* ``methodology_based`` — a researched/institutional methodology was
  supplied and parsed (e.g. "multiply by 9.5").
* ``estimate``          — the linear default, always warned as unofficial.
* ``exact``             — pure arithmetic with no interpretation
  (percentage↔scale identities, weighted GPA).
* ``invalid``           — refused input; nothing is silently "fixed".

Full precision internally; two decimals at the boundary.
"""

from __future__ import annotations

import re
from typing import Any

_NUMBER = re.compile(r"\d+(?:\.\d+)?")

_LINEAR_WARNING = (
    "Linear scaling is not an official equivalence; the target "
    "university's own methodology decides."
)


def _scale_of(raw: str) -> float | None:
    match = _NUMBER.fullmatch(str(raw or "").strip())
    if not match:
        return None
    value = float(match.group())
    return value if value > 0 else None


def _parse_methodology(text: str) -> tuple[float | None, str]:
    """Extract a multiply-by factor from a researched methodology sentence.

    Recognizes only the explicit multiplicative form ("multiply by 9.5",
    "CGPA × 10"). Anything else returns None — an unparseable methodology
    falls back to the labeled estimate rather than a guessed formula.
    """
    flat = str(text or "").casefold()
    match = re.search(r"(?:multiply(?:ing)?[^0-9]{0,20}|[x×]\s*)(\d+(?:\.\d+)?)", flat)
    if match:
        return float(match.group(1)), f"multiply by {match.group(1)} (researched)"
    return None, ""


def convert_academic_score(
    value: float,
    from_scale: str,
    to_scale: str,
    methodology: str = "",
) -> dict[str, Any]:
    """Convert one academic score between explicit scales."""
    inputs = {"value": value, "from_scale": from_scale, "to_scale": to_scale}
    source_max = _scale_of(from_scale)
    target_max = _scale_of(to_scale)
    if source_max is None or target_max is None:
        return {
            "calculation_type": "academic_conversion",
            "status": "invalid",
            "inputs": inputs,
            "message": "Both scales must be numeric maxima, e.g. '10', '4', '100'.",
        }
    if not 0 <= value <= source_max:
        return {
            "calculation_type": "academic_conversion",
            "status": "invalid",
            "inputs": inputs,
            "message": f"{value} is outside the 0-{source_max} scale.",
        }

    warnings: list[str] = []
    factor, method_label = _parse_methodology(methodology)
    if factor is not None:
        result = value * factor
        method, status = method_label, "methodology_based"
        if result > target_max:
            warnings.append(
                f"The methodology result {round(result, 2)} exceeds the "
                f"target scale maximum {target_max} — verify the method's "
                "intended target scale."
            )
    else:
        if methodology:
            warnings.append(
                "The supplied methodology could not be parsed into a "
                "formula; falling back to a linear estimate."
            )
        result = value / source_max * target_max
        method, status = (
            f"linear scaling ({source_max} → {target_max})",
            "estimate",
        )
        warnings.append(_LINEAR_WARNING)

    return {
        "calculation_type": "academic_conversion",
        "status": status,
        "inputs": inputs,
        "method": method,
        "result": round(result, 2),
        "unit": f"/{to_scale}",
        "warnings": warnings,
    }


def weighted_gpa(courses: list[tuple[float, float]]) -> dict[str, Any]:
    """Credit-weighted GPA: Σ(grade × credits) / Σ credits."""
    if not courses:
        return {
            "calculation_type": "weighted_gpa",
            "status": "invalid",
            "message": "At least one (grade, credits) pair is required.",
        }
    for grade, credits in courses:
        if credits <= 0:
            return {
                "calculation_type": "weighted_gpa",
                "status": "invalid",
                "message": f"Credits must be positive (got {credits}).",
            }
        if grade < 0:
            return {
                "calculation_type": "weighted_gpa",
                "status": "invalid",
                "message": f"Grades cannot be negative (got {grade}).",
            }
    total_credits = sum(credits for _, credits in courses)
    weighted = sum(grade * credits for grade, credits in courses)
    return {
        "calculation_type": "weighted_gpa",
        "status": "exact",
        "inputs": {"courses": courses},
        "method": "sum(grade × credits) / sum(credits)",
        "result": round(weighted / total_credits, 2),
        "unit": "same scale as the input grades",
        "warnings": [],
    }
