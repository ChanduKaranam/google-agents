"""University analysis — deadline freshness and faculty matching, in code.

Both are deterministic interpretations over researched facts:

* Freshness compares the years a deadline sentence actually states with
  the student's target intake. No year → `cycle_unclear`, never "current".
* Faculty matching is token overlap between the student's *stated*
  interests and the researched faculty-research text, with the overlap
  named. No overlap → no match; supervision availability is never implied.
"""

from __future__ import annotations

import re
from typing import Any

_YEAR = re.compile(r"\b(20\d{2})\b")

_STOP = {
    "and",
    "the",
    "of",
    "in",
    "with",
    "prof",
    "dr",
    "professor",
    "research",
    "learning",  # so "deep learning"/"machine learning" match on their
    # distinctive token rather than on "learning" alone
}


def assess_deadline_freshness(deadline_text: str, target_intake: str) -> dict[str, Any]:
    """Is this deadline plausibly for the student's target cycle?"""
    stated_years = [int(y) for y in _YEAR.findall(str(deadline_text or ""))]
    target_years = [int(y) for y in _YEAR.findall(str(target_intake or ""))]
    if not stated_years:
        return {
            "status": "cycle_unclear",
            "note": (
                "The deadline text states no year, so its admissions cycle "
                "cannot be confirmed — verify against the current cycle "
                "before relying on it."
            ),
        }
    if not target_years:
        return {
            "status": "cycle_unclear",
            "note": "No target intake on the profile to compare the cycle to.",
        }
    latest_stated = max(stated_years)
    target = max(target_years)
    # A Fall-2027 intake is served by deadlines dated 2026 or 2027.
    if latest_stated >= target - 1:
        return {
            "status": "appears_current",
            "note": f"The stated cycle ({latest_stated}) matches the "
            f"target intake ({target}).",
        }
    return {
        "status": "stale",
        "note": (
            f"The stated cycle ({latest_stated}) predates the target intake "
            f"({target}) — a historical deadline, not the student's."
        ),
    }


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z]+", str(text).casefold()) if t not in _STOP}


def match_faculty(student_interests: list[str], faculty_text: str) -> dict[str, Any]:
    """Match stated interests against researched faculty-research text.

    The faculty fact is free text ("Prof X: computer vision, imaging.
    Prof Y: NLP"). Each sentence-ish segment is matched separately so the
    overlap names *which* faculty line matched, with the shared terms.
    """
    interests = [i for i in (student_interests or []) if str(i).strip()]
    if not interests:
        return {
            "status": "no_interests",
            "note": "No stated research interests to match against.",
        }
    interest_tokens = _tokens(" ".join(interests))
    matched: list[dict[str, Any]] = []
    segments = re.split(r"(?<=[.;])\s+", str(faculty_text or ""))
    for segment in segments:
        if not segment.strip():
            continue
        overlap = interest_tokens & _tokens(segment)
        if overlap:
            matched.append(
                {
                    "faculty_line": segment.strip(),
                    "overlap": sorted(overlap),
                    "basis": (
                        "shared terms between the student's stated interests "
                        f"and this profile line: {', '.join(sorted(overlap))}"
                    ),
                }
            )
    return {
        "status": "success",
        "matched": matched,
        "note": (
            "Alignment of published research areas only — never an "
            "indication of supervision availability."
            if matched
            else "No overlap between the stated interests and the "
            "researched faculty lines."
        ),
    }
