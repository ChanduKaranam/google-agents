"""The question priority engine — which single question is worth asking now.

Deterministic (§10 of the V2 brief): the *model* decides how to phrase a
question and when the student changed the subject; *this code* decides what
information is worth asking for next, given what is already known and what
the student is trying to do. One question at a time is a product rule, so
the engine returns exactly one candidate plus the readiness picture.

Intent shifts priority, it does not invent new questions: "find affordable
universities" promotes budget to the front; "can I get in" promotes scores.
"""

from __future__ import annotations

from typing import Any

from app.models.student import StudentProfile

# (path, why it matters, ask-phrasing hint). Baseline order = the generic
# interview: country → academics → specialization → intake → budget →
# English → GRE → experience/research → career goal → preferences.
QUESTION_BANK: tuple[tuple[str, str, str], ...] = (
    (
        "target.country",
        "Scopes every search and recommendation.",
        "Which country or countries are you considering?",
    ),
    (
        "education.degree",
        "MS programs state required academic backgrounds.",
        "What's your undergraduate degree?",
    ),
    ("education.major", "Decides which programs are relevant.", "What was your major?"),
    (
        "education.cgpa",
        "Needed to evaluate academic fit for any program.",
        "What's your CGPA?",
    ),
    (
        "education.grading_scale",
        "A CGPA means nothing without its scale.",
        "What scale is that CGPA on — 10, 4, or percentage?",
    ),
    (
        "target.specialization",
        "Focuses discovery on the right programs.",
        "What area interests you most — AI/ML, software engineering, data "
        "science, cybersecurity, systems, or something else?",
    ),
    (
        "target.intake",
        "Deadlines and planning hang off the intake.",
        "Which intake are you targeting — e.g. Fall 2027?",
    ),
    (
        "preferences.budget",
        "Filters out programs the student would never take.",
        "What's your approximate total budget, including tuition and living?",
    ),
    (
        "test_scores.ielts",
        "Most programs require an English test score.",
        "Have you taken IELTS or TOEFL yet? If so, what score?",
    ),
    (
        "test_scores.gre",
        "Some programs require or recommend the GRE.",
        "Have you taken the GRE, or are you planning to?",
    ),
    (
        "experience.work_experience_months",
        "Experience strengthens many applications.",
        "Do you have internships or work experience I should factor in?",
    ),
    (
        "research.research_interests",
        "Drives research-fit and faculty alignment.",
        "Any research experience, publications, or research interests?",
    ),
    (
        "target.career_goal",
        "Industry vs research goals change the right programs.",
        "What do you want to do after the MS — industry, research, a PhD?",
    ),
    (
        "preferences.thesis_preference",
        "Thesis vs course-based changes the list.",
        "Do you prefer a thesis-based or course-based program?",
    ),
    (
        "preferences.coop_preference",
        "Co-op availability matters for industry goals.",
        "Is co-op / internship during the program important to you?",
    ),
)

# Intent → paths promoted to the front, in order. Everything else keeps the
# baseline order behind them.
INTENT_PRIORITIES: dict[str, tuple[str, ...]] = {
    "FIND_AFFORDABLE": (
        "preferences.budget",
        "target.country",
        "preferences.scholarship_required",
    ),
    "ESTIMATE_COST": ("preferences.budget", "target.country"),
    "FIND_SCHOLARSHIPS": ("preferences.budget", "education.cgpa"),
    "FIND_RESEARCH_PROGRAMS": (
        "research.research_interests",
        "target.specialization",
        "target.career_goal",
    ),
    "CHECK_ELIGIBILITY": (
        "education.cgpa",
        "education.grading_scale",
        "test_scores.ielts",
        "test_scores.gre",
    ),
    "CAREER_ORIENTED_SEARCH": (
        "target.career_goal",
        "preferences.coop_preference",
        "target.specialization",
    ),
    "FIND_COOP_PROGRAMS": ("preferences.coop_preference", "target.career_goal"),
    "FIND_THESIS_PROGRAMS": (
        "preferences.thesis_preference",
        "research.research_interests",
    ),
}

# Readiness tiers (§28): what "enough" means, per level.
BASIC_PATHS = (
    "target.country",
    "education.major",
    "education.cgpa",
    "education.grading_scale",
    "target.specialization",
)
STRONG_PATHS = BASIC_PATHS + (
    "target.intake",
    "preferences.budget",
    "test_scores.ielts",
)
DEEP_PATHS = STRONG_PATHS + (
    "research.research_interests",
    "experience.work_experience_months",
    "target.career_goal",
)


def _known(profile: StudentProfile, path: str) -> bool:
    section, field = path.split(".")
    value = getattr(getattr(profile, section), field)
    if path == "test_scores.ielts" and profile.test_scores.toefl is not None:
        return True
    return value is not None and value != []


def readiness(profile: StudentProfile) -> dict[str, Any]:
    """How ready the profile is, per tier — never a demand for 100%."""

    def tier(paths: tuple[str, ...]) -> dict[str, Any]:
        missing = [p for p in paths if not _known(profile, p)]
        return {"complete": not missing, "missing": missing}

    basic = tier(BASIC_PATHS)
    strong = tier(STRONG_PATHS)
    deep = tier(DEEP_PATHS)
    known_count = sum(1 for p, _, _ in QUESTION_BANK if _known(profile, p))
    return {
        "percent": int(round(known_count / len(QUESTION_BANK) * 100)),
        "basic_recommendations": basic,
        "strong_recommendations": strong,
        "deep_recommendations": deep,
        "level": (
            "deep"
            if deep["complete"]
            else "strong"
            if strong["complete"]
            else "basic"
            if basic["complete"]
            else "insufficient"
        ),
    }


def choose_next_question(
    profile: StudentProfile, intent: str = ""
) -> dict[str, Any] | None:
    """The one question worth asking now, or None when nothing high-value
    is missing. Skipped fields (the student said "I don't know" / declined)
    are handled by the caller passing them in state, not re-asked here —
    V2 keeps that in the conversation layer.
    """
    promoted = INTENT_PRIORITIES.get(intent.strip().upper(), ())
    by_path = {path: (why, hint) for path, why, hint in QUESTION_BANK}
    ordered = [p for p in promoted if p in by_path]
    ordered += [p for p, _, _ in QUESTION_BANK if p not in ordered]
    for path in ordered:
        if not _known(profile, path):
            why, hint = by_path[path]
            return {"field": path, "why": why, "suggested_phrasing": hint}
    return None
