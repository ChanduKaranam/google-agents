"""University resolution — aliases in, official names out, guesses never.

Static aliases are stable metadata (§4 allows them): "UBC" has meant the
University of British Columbia for a century. Current *facts* about these
universities still come only from research. An unknown name stays unknown,
and an ambiguous one returns its candidates as a question.
"""

from __future__ import annotations

from typing import Any

# alias (casefolded) → official name. Extend freely; never store facts here.
_ALIASES: dict[str, str] = {
    "ubc": "University of British Columbia",
    "university of british columbia": "University of British Columbia",
    "uoft": "University of Toronto",
    "u of t": "University of Toronto",
    "university of toronto": "University of Toronto",
    "toronto": "University of Toronto",
    "waterloo": "University of Waterloo",
    "uwaterloo": "University of Waterloo",
    "university of waterloo": "University of Waterloo",
    "mcgill": "McGill University",
    "mcgill university": "McGill University",
    "mcmaster": "McMaster University",
    "sfu": "Simon Fraser University",
    "simon fraser": "Simon Fraser University",
    "ualberta": "University of Alberta",
    "university of alberta": "University of Alberta",
    "mit": "Massachusetts Institute of Technology",
    "cmu": "Carnegie Mellon University",
    "carnegie mellon": "Carnegie Mellon University",
    "tum": "Technical University of Munich",
    "tu delft": "Delft University of Technology",
}

# Aliases that genuinely point at more than one institution.
_AMBIGUOUS: dict[str, tuple[str, ...]] = {
    "columbia": (
        "Columbia University",
        "University of British Columbia",
    ),
    "washington": (
        "University of Washington",
        "Washington University in St. Louis",
    ),
    "cambridge": (
        "University of Cambridge",
        "Massachusetts Institute of Technology (Cambridge, MA)",
        "Harvard University (Cambridge, MA)",
    ),
}


def resolve_university(name: str) -> dict[str, Any]:
    """Resolve a user-typed university name.

    Returns `resolved` with the official name, `ambiguous` with candidates
    (a question for the student), or `unknown` — research can still
    proceed on an unknown name, it just isn't normalized.
    """
    key = " ".join(str(name or "").casefold().split())
    if not key:
        return {"status": "unknown", "input": name}
    if key in _AMBIGUOUS:
        return {
            "status": "ambiguous",
            "input": name,
            "candidates": list(_AMBIGUOUS[key]),
        }
    official = _ALIASES.get(key)
    if official:
        return {"status": "resolved", "input": name, "official_name": official}
    # A full "University of X" style name we simply don't alias yet
    # resolves to itself as typed. Weaker markers (institute/college) do
    # not — they let fictional or garbled names slip through as resolved.
    if "university" in key:
        return {"status": "resolved", "input": name, "official_name": str(name).strip()}
    return {"status": "unknown", "input": name}
