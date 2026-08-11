"""Placement analysis — scope discipline, salary attributes, career fit.

Deterministic interpretation over researched career evidence. The
load-bearing rule (§13 of the Phase 5 brief): **scope is read from the
text and never upgraded** — a faculty-level figure cannot become a
program statistic, a national benchmark cannot become a university salary,
and text stating no scope is `scope_unclear`, never assumed specific.
"""

from __future__ import annotations

import re
from typing import Any

from app.alumni.analysis import role_family
from app.models.student import StudentProfile

# Ordered most-specific-first; the first matching scope wins so "MSc
# graduates in the Faculty of Engineering" reads as program-specific.
_SCOPE_MARKERS: tuple[tuple[str, str], ...] = (
    (
        "program_specific",
        r"\b(msc|master|ms\b|mmath|meng|graduate program|this program|program graduates)\b",
    ),
    ("faculty_level", r"\bfaculty of\b|\bfaculty-level\b|\bfaculty graduates\b"),
    (
        "university_level",
        r"\buniversity[- ]wide\b|\ball graduates\b|\bacross the university\b",
    ),
    (
        "market_benchmark",
        r"\bin canada\b|\blabou?r market\b|\bnational\b|\bbenchmark\b|\bstatistics canada\b",
    ),
)

_CURRENCY = re.compile(r"\b(CAD|USD|EUR|GBP|INR|AUD)\b", re.IGNORECASE)
_AMOUNT = re.compile(
    r"(?:CAD|USD|EUR|GBP|INR|AUD|\$|€|£|₹)\s*([\d,]{4,12})", re.IGNORECASE
)
_PERIOD = re.compile(
    r"\bper\s+(year|annum|month|hour)\b|\b(annual|yearly|monthly|hourly)\b",
    re.IGNORECASE,
)
_YEAR = re.compile(r"\b(20\d{2})\b")


def classify_scope(text: str) -> dict[str, Any]:
    """What population does this career statement actually cover?"""
    flat = " ".join(str(text or "").casefold().split())
    for scope, pattern in _SCOPE_MARKERS:
        match = re.search(pattern, flat)
        if match:
            return {
                "scope": scope,
                "basis": match.group(0),
                "note": (
                    "Scope as the source states it — never presented at a "
                    "narrower scope than this."
                ),
            }
    return {
        "scope": "scope_unclear",
        "basis": "",
        "note": (
            "The text states no population scope; verify before relying on "
            "it, and never present it as program-specific."
        ),
    }


def extract_salary_attributes(text: str) -> dict[str, Any]:
    """Currency/amount/period/year — only what the text literally states."""
    raw = str(text or "")
    currency = _CURRENCY.search(raw)
    amount = _AMOUNT.search(raw)
    period = _PERIOD.search(raw)
    year = _YEAR.search(raw)
    period_value = None
    if period:
        token = (period.group(1) or period.group(2) or "").casefold()
        period_value = {
            "annual": "year",
            "yearly": "year",
            "monthly": "month",
            "hourly": "hour",
        }.get(token, token or None)
    return {
        "currency": currency.group(1).upper() if currency else None,
        "amount": int(amount.group(1).replace(",", "")) if amount else None,
        "period": period_value,
        "year": int(year.group(1)) if year else None,
    }


def analyze_career_fit(profile: StudentProfile, roles_text: str) -> dict[str, Any]:
    """Align researched role evidence with the student's stated profile.

    Roles are read from the evidence text; alignment is role-family and
    token overlap against stated skills, interests and the career goal —
    each with its basis. No probabilities, no percentages.
    """
    if not str(roles_text or "").strip():
        return {
            "aligned": [],
            "other_roles": [],
            "note": "No role evidence researched yet — nothing to align.",
        }
    student_terms = {
        t
        for source in (
            profile.technical.skills,
            profile.research.research_interests,
            [profile.target.specialization or ""],
            [profile.target.career_goal or ""],
        )
        for item in source
        for t in re.findall(r"[a-z]+", str(item).casefold())
    } - {"and", "the", "of"}
    goal_family = role_family(profile.target.career_goal or "")

    # Candidate role phrases: capitalized multi-word spans ending in a role
    # noun, plus anything the role-family table recognizes.
    candidates = set(
        re.findall(
            r"\b([A-Z][A-Za-z]+(?:\s+[A-Za-z]+){0,3}?\s"
            r"(?:Engineer|Scientist|Developer|Analyst|Researcher|Manager))\b",
            str(roles_text),
        )
    )
    aligned, other = [], []
    for role in sorted(candidates):
        family = role_family(role)
        overlap = student_terms & set(re.findall(r"[a-z]+", role.casefold()))
        reasons = []
        if goal_family != "Other" and family == goal_family:
            reasons.append(f"matches your stated career goal family ({family})")
        if overlap:
            reasons.append(
                "overlaps your stated skills/interests: " + ", ".join(sorted(overlap))
            )
        if reasons:
            aligned.append({"role": role, "basis": "; ".join(reasons)})
        else:
            other.append(role)
    return {
        "aligned": aligned,
        "other_roles": other,
        "note": (
            "Alignment of published role evidence with the student's stated "
            "profile — never a hiring likelihood."
        ),
    }
