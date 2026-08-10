"""Deterministic exam-requirement interpretation and score comparison.

Turns a researched requirement *sentence* (an evidence-graded program fact)
into a structured verdict. Conservative by construction:

* Negations are checked before affirmations, so "not required" can never
  match "required".
* Conditions ("waived if…", "unless…") outrank both — a conditional
  requirement presented as either absolute would mislead in one direction
  or the other.
* Anything unmatched is `unknown`. Absence of evidence is NEVER
  `not_required` (§1) — that inversion is the domain's classic failure.
* Numeric minimums are extracted only when literally present; a comparison
  against an unstated minimum returns "requirement stated without minimum",
  not a pass.
"""

from __future__ import annotations

import re
from typing import Any

REQUIREMENT_STATUSES = (
    "required",
    "optional",
    "not_required",
    "conditional",
    "waived",
    "unknown",
)

# Order matters: first match wins, most specific first. Compound optional
# phrasings ("recommended but not required") precede the bare negation so
# they classify as optional rather than not_required.
_STATUS_PATTERNS: tuple[tuple[str, str], ...] = (
    ("conditional", r"waived (?:if|for|when)|required (?:if|unless|only)|unless"),
    ("waived", r"\bwaiv(?:ed|er)\b"),
    (
        "optional",
        r"recommended but not required|\bencouraged but\b|\bmay be submitted\b",
    ),
    ("not_required", r"\bnot required\b|\bdoes not require\b|\bno (?:gre|gmat)\b"),
    ("optional", r"\boptional\b|\bnot mandatory\b"),
    (
        "required",
        r"\brequired\b|\bmust (?:be )?submit(?:ted)?\b|\bmandatory\b"
        r"|\bmust (?:be )?provide[d]?\b",
    ),
)

_OVERALL = re.compile(
    r"(?:overall|band of|minimum(?: score)? of|score of|at least)\s*(\d{1,3}(?:\.\d)?)"
    r"|(\d{1,3}(?:\.\d)?)\s*(?:overall|or (?:higher|above))",
    re.IGNORECASE,
)
_SECTION = re.compile(
    r"(?:no (?:band|section|score) (?:below|less than)|each (?:band|section|component)"
    r"(?: at least| of| minimum)?|minimum of)\s*(\d{1,3}(?:\.\d)?)"
    r"\s*(?:in each|per section)?",
    re.IGNORECASE,
)


def interpret_requirement(text: str) -> dict[str, Any]:
    """Classify one requirement sentence; extract minimums only if stated."""
    flat = " ".join(str(text or "").casefold().split())
    status, basis = "unknown", ""
    for candidate, pattern in _STATUS_PATTERNS:
        match = re.search(pattern, flat)
        if match:
            status, basis = candidate, match.group(0)
            break

    min_overall: float | None = None
    min_section: float | None = None
    overall_match = _OVERALL.search(flat)
    if overall_match:
        min_overall = float(overall_match.group(1) or overall_match.group(2))
    section_match = _SECTION.search(flat)
    if section_match:
        candidate_min = float(section_match.group(1))
        # "minimum of X" alone is an overall statement, not a per-section
        # one, unless the sentence says so explicitly.
        if re.search(r"band|section|component|each", flat):
            min_section = candidate_min
            if min_overall is None and "overall" not in flat:
                pass  # a pure per-section rule; overall stays unstated
    if min_overall is not None and min_section == min_overall and not section_match:
        min_section = None

    return {
        "status": status,
        "basis": basis,
        "min_overall": min_overall,
        "min_section": min_section,
        "text": str(text or ""),
    }


def compare_score(
    requirement: dict[str, Any],
    overall: float | None,
    lowest_section: float | None,
) -> dict[str, Any]:
    """Compare a student's score with one interpreted requirement.

    Verdicts: meets_stated_minimum · below_stated_minimum ·
    meets_overall_sections_unknown · requirement_stated_without_minimum ·
    score_missing. Unknown section scores never upgrade to a full pass.
    """
    min_overall = requirement.get("min_overall")
    min_section = requirement.get("min_section")

    if overall is None:
        return {
            "verdict": "score_missing",
            "note": "No score on the profile to compare.",
        }
    if min_overall is None and min_section is None:
        return {
            "verdict": "requirement_stated_without_minimum",
            "note": (
                "The source states the requirement without a numeric "
                "minimum; the program page decides."
            ),
        }
    if min_overall is not None and overall < min_overall:
        return {
            "verdict": "below_stated_minimum",
            "note": f"Overall {overall} is below the stated {min_overall}.",
            "gap": round(min_overall - overall, 2),
        }
    if min_section is not None:
        if lowest_section is None:
            return {
                "verdict": "meets_overall_sections_unknown",
                "note": (
                    "Overall meets the stated minimum, but the source also "
                    "sets per-section minimums and the section scores are "
                    "not on the profile — ask for the lowest band."
                ),
            }
        if lowest_section < min_section:
            return {
                "verdict": "below_stated_minimum",
                "note": (
                    f"Lowest section {lowest_section} is below the stated "
                    f"per-section minimum {min_section}."
                ),
                "section_gap": round(min_section - lowest_section, 2),
            }
    return {
        "verdict": "meets_stated_minimum",
        "note": "Meets every minimum the source stated.",
    }
