"""Alumni analysis: career patterns, company ecosystems, and student
similarity — counted, never estimated.

Every aggregate here carries its denominator ("among the N public profiles
found"), and pattern language is gated on a minimum group size — "2 of 2
work in data" invites exactly the generalization a convenience sample
cannot support (§51). Similarity is anchor overlap in words, never a
probability of anything (§13, §32).
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from app.alumni.models import AlumniRecord
from app.models.student import StudentProfile

# Below this many resolved profiles, report counts only — no "commonly",
# no "typically", no patterns.
MIN_PATTERN_N = 5

COMPANY_CATEGORIES: dict[str, tuple[str, ...]] = {
    "big_tech": (
        "google",
        "microsoft",
        "amazon",
        "meta",
        "apple",
        "nvidia",
        "netflix",
        "ibm",
        "oracle",
        "intel",
    ),
    "ai_companies": (
        "openai",
        "anthropic",
        "deepmind",
        "cohere",
        "hugging face",
        "databricks",
        "scale ai",
    ),
    "consulting": (
        "mckinsey",
        "bain",
        "bcg",
        "deloitte",
        "accenture",
        "kpmg",
        "ey",
        "pwc",
    ),
    "finance": (
        "goldman",
        "morgan",
        "jpmorgan",
        "citadel",
        "two sigma",
        "rbc",
        "td bank",
        "scotiabank",
        "bloomberg",
    ),
}

_ROLE_FAMILIES: dict[str, tuple[str, ...]] = {
    "ML Engineer": (
        "ml engineer",
        "machine learning engineer",
        "ai engineer",
        "machine learning scientist",
        "applied scientist",
    ),
    "Software Engineer": (
        "software engineer",
        "software developer",
        "swe",
        "backend",
        "full stack",
        "systems engineer",
    ),
    "Data Scientist": ("data scientist",),
    "Data Engineer": ("data engineer",),
    "Research": (
        "research scientist",
        "research engineer",
        "researcher",
        "phd",
        "postdoc",
        "research assistant",
    ),
    "Product": ("product manager",),
    "Security": ("security", "cybersecurity"),
}


def _tokens(text: str) -> set[str]:
    stop = {"and", "the", "of", "in", "with", "using"}
    return {t for t in re.findall(r"[a-z+#]+", str(text).casefold()) if t not in stop}


def _claim(record: AlumniRecord, field: str) -> str:
    claim = record.claims.get(field)
    return claim.value if claim else ""


def categorize_company(company: str) -> str:
    lowered = company.casefold()
    for category, names in COMPANY_CATEGORIES.items():
        if any(name in lowered for name in names):
            return category
    return "other"


def role_family(role: str) -> str:
    lowered = role.casefold()
    for family, markers in _ROLE_FAMILIES.items():
        if any(marker in lowered for marker in markers):
            return family
    return "Other"


def analyze_group(records: list[AlumniRecord]) -> dict[str, Any]:
    """Counts with denominators over one university's resolved alumni."""
    n = len(records)
    companies = Counter(_claim(r, "company") for r in records if _claim(r, "company"))
    roles = Counter(
        role_family(_claim(r, "role")) for r in records if _claim(r, "role")
    )
    locations = Counter(_claim(r, "location") for r in records if _claim(r, "location"))
    research_active = sum(
        1 for r in records if _claim(r, "research_area") or _claim(r, "publication")
    )
    startup = sum(1 for r in records if _claim(r, "startup"))
    phd = sum(1 for r in records if _claim(r, "phd_institution"))
    categories = Counter(categorize_company(c) for c in companies.elements())
    return {
        "profiles_found": n,
        "may_use_pattern_language": n >= MIN_PATTERN_N,
        "pattern_threshold": MIN_PATTERN_N,
        "companies": dict(companies.most_common(10)),
        "company_categories": dict(categories),
        "role_families": dict(roles.most_common(10)),
        "locations": dict(locations.most_common(10)),
        "research_active": {"count": research_active, "of": n},
        "startup_signals": {"count": startup, "of": n},
        "phd_transitions": {"count": phd, "of": n},
        "coverage_note": (
            "Counts describe only the publicly discoverable profiles that "
            "were verified — never the full graduate population."
        ),
    }


# --- Student ↔ alumni similarity (§13) --------------------------------------

_SIMILARITY_BANDS = ("strong", "moderate", "weak", "none")


def similarity(profile: StudentProfile, record: AlumniRecord) -> dict[str, Any]:
    """Anchor overlap between the student and one alumnus, in words."""
    anchors: list[dict[str, str]] = []

    student_skills = _tokens(" ".join(profile.technical.skills))
    alumni_skills = _tokens(_claim(record, "skills"))
    shared_skills = student_skills & alumni_skills
    if shared_skills:
        anchors.append(
            {
                "kind": "technical",
                "detail": "shared skills: " + ", ".join(sorted(shared_skills)[:6]),
            }
        )

    interest = (profile.target.specialization or "").casefold()
    research = _claim(record, "research_area").casefold()
    if interest and research and (_tokens(interest) & _tokens(research)):
        anchors.append(
            {
                "kind": "research",
                "detail": f"research area overlaps your interest ({interest})",
            }
        )

    goal = profile.target.career_goal or ""
    role = _claim(record, "role")
    if goal and role and role_family(role) == role_family(goal):
        anchors.append(
            {
                "kind": "career",
                "detail": f"works in your target role family ({role_family(role)})",
            }
        )

    if profile.education.major and _claim(record, "program"):
        if _tokens(profile.education.major) & _tokens(_claim(record, "program")):
            anchors.append(
                {
                    "kind": "academic",
                    "detail": "similar academic background",
                }
            )

    band = (
        "strong"
        if len(anchors) >= 3
        else "moderate"
        if len(anchors) == 2
        else "weak"
        if len(anchors) == 1
        else "none"
    )
    return {
        "alumnus": record.name,
        "band": band,
        "anchors": anchors,
        "note": "Profile similarity is a signal, never an admission or "
        "employment probability.",
    }
