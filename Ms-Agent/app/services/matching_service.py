"""The matching engine — every number here is deterministic.

`calculate_match_score(profile, program)` produces the weighted fit score
from structured fields. The LLM narrates the result; it cannot alter it.

Two rules shape everything:

* **Missing data is excluded, never punished.** A dimension that cannot be
  evaluated (no CGPA, no research interests, requirement unknown) returns
  `score=None`, drops out, and the remaining weights renormalize. Scoring
  an unknown as 0 would make "tell me less" change the number dishonestly.
* **A fit score is not an admission probability.** The result says so on
  every instance, and no language here may imply chances.
"""

from __future__ import annotations

import re

from app.config.settings import CATEGORY_THRESHOLDS, MATCH_WEIGHTS
from app.models.matching import ComponentScore, MatchResult, MatchWeights
from app.models.program import Program
from app.models.student import StudentProfile

_NUMBER = re.compile(r"\d+(?:\.\d+)?")


def _first_number(text: str | None) -> float | None:
    match = _NUMBER.search(str(text or ""))
    return float(match.group()) if match else None


def gpa_on_4_scale(cgpa: float | None, grading_scale: str | None) -> float | None:
    """Deterministic linear normalization, explicit rules only.

    Linear conversion is an approximation and callers must present it as
    one — but it must also be *predictable*, hence fixed rules instead of
    guessing per-institution tables in V1.
    """
    if cgpa is None:
        return None
    scale = _first_number(grading_scale)
    if scale is None:
        scale = 4.0 if cgpa <= 4.0 else (10.0 if cgpa <= 10.0 else 100.0)
    if scale <= 0 or cgpa > scale:
        return None
    return round(cgpa / scale * 4.0, 2)


def _tokens(text: str) -> set[str]:
    stop = {"of", "in", "and", "the", "ms", "msc", "master", "masters", "science"}
    return {t for t in re.findall(r"[a-z]+", text.casefold()) if t not in stop}


def _academic_fit(profile: StudentProfile, program: Program) -> ComponentScore:
    weight = MATCH_WEIGHTS.academic_fit
    student_gpa = gpa_on_4_scale(
        profile.education.cgpa, profile.education.grading_scale
    )
    if student_gpa is None:
        return ComponentScore(
            name="academic_fit",
            score=None,
            weight=weight,
            basis="No CGPA (or an inconsistent scale) on the profile.",
        )
    requirement = _first_number(
        program.facts["gpa_requirement"].value
        if "gpa_requirement" in program.facts
        else None
    )
    if requirement is None:
        requirement, req_basis = 3.0, "a generic 3.0/4.0 baseline (no stated minimum)"
    else:
        if requirement > 4.0:  # requirement stated on another scale
            requirement = round(
                requirement / (10.0 if requirement <= 10 else 100.0) * 4.0, 2
            )
        req_basis = f"the program's stated minimum ({requirement}/4.0)"
    delta = student_gpa - requirement
    if delta >= 0:
        score = min(100, 80 + int(delta * 50))
    else:
        score = max(0, 80 + int(delta * 160))
    return ComponentScore(
        name="academic_fit",
        score=score,
        weight=weight,
        basis=f"GPA {student_gpa}/4.0 against {req_basis}.",
    )


def _program_fit(profile: StudentProfile, program: Program) -> ComponentScore:
    weight = MATCH_WEIGHTS.program_fit
    interest = profile.target.specialization or profile.education.major
    if not interest:
        return ComponentScore(
            name="program_fit",
            score=None,
            weight=weight,
            basis="No specialization or major on the profile.",
        )
    interest_tokens = _tokens(interest)
    program_tokens = _tokens(program.name)
    overlap = interest_tokens & program_tokens
    if interest.casefold() in program.name.casefold() or (
        interest_tokens and interest_tokens <= program_tokens
    ):
        score, note = 90, "direct alignment"
    elif overlap:
        score, note = 70, f"partial overlap ({', '.join(sorted(overlap))})"
    else:
        score, note = 40, "different field"
    return ComponentScore(
        name="program_fit",
        score=score,
        weight=weight,
        basis=f"'{interest}' vs '{program.name}': {note}.",
    )


def _research_fit(profile: StudentProfile, program: Program) -> ComponentScore:
    weight = MATCH_WEIGHTS.research_fit
    interests = profile.research.research_interests
    publications = profile.research.publications
    if not interests and publications is None:
        return ComponentScore(
            name="research_fit",
            score=None,
            weight=weight,
            basis="No research information on the profile.",
        )
    score = 50
    notes = []
    if interests:
        overlap = _tokens(" ".join(interests)) & _tokens(program.name)
        if overlap:
            score += 25
            notes.append(
                f"interests overlap the program ({', '.join(sorted(overlap))})"
            )
        else:
            notes.append("interests recorded, none overlap the program name")
    if publications:
        score += min(25, publications * 10)
        notes.append(f"{publications} publication(s)")
    return ComponentScore(
        name="research_fit",
        score=min(100, score),
        weight=weight,
        basis="; ".join(notes) or "publications only",
    )


def _experience_fit(profile: StudentProfile, program: Program) -> ComponentScore:
    weight = MATCH_WEIGHTS.experience_fit
    months = profile.experience.work_experience_months
    internships = len(profile.experience.internships)
    if months is None and internships == 0:
        return ComponentScore(
            name="experience_fit",
            score=None,
            weight=weight,
            basis="No experience information on the profile.",
        )
    months = months or 0
    if months >= 24:
        score = 90
    elif months >= 12:
        score = 75
    elif months >= 6:
        score = 60
    else:
        score = 45
    score = min(100, score + internships * 5)
    return ComponentScore(
        name="experience_fit",
        score=score,
        weight=weight,
        basis=f"{months} months work experience, {internships} internship(s).",
    )


def _requirements_fit(
    profile: StudentProfile, program: Program
) -> tuple[ComponentScore, list[str]]:
    weight = MATCH_WEIGHTS.requirements_fit
    missing: list[str] = []
    ielts, toefl = profile.test_scores.ielts, profile.test_scores.toefl
    fact = program.facts.get("english_requirement")
    if fact is None:
        if ielts is None and toefl is None:
            return (
                ComponentScore(
                    name="requirements_fit",
                    score=None,
                    weight=weight,
                    basis="Requirement unknown and no English score on file.",
                ),
                ["English test score (IELTS/TOEFL)"],
            )
        return (
            ComponentScore(
                name="requirements_fit",
                score=70,
                weight=weight,
                basis="English score on file; the program's exact requirement "
                "has not been verified yet.",
            ),
            [],
        )
    required = _first_number(fact.value)
    if ielts is None and toefl is None:
        # A known requirement and no score is a gap to close, not a grade:
        # scoring it would punish missing data, which the engine never does.
        return (
            ComponentScore(
                name="requirements_fit",
                score=None,
                weight=weight,
                basis=f"The program states '{fact.value}' and no English "
                "score is on file yet.",
            ),
            ["English test score (IELTS/TOEFL)"],
        )
    if required is None or ielts is None:
        score = 60
        basis = f"Stated requirement '{fact.value}' could not be compared numerically."
    elif ielts >= required:
        score = 95
        basis = f"IELTS {ielts} meets the stated {required}."
    else:
        score = 35
        basis = f"IELTS {ielts} is below the stated {required}."
        missing.append(f"IELTS {required} (currently {ielts})")
    return (
        ComponentScore(
            name="requirements_fit", score=score, weight=weight, basis=basis
        ),
        missing,
    )


def _financial_fit(profile: StudentProfile, program: Program) -> ComponentScore:
    """Budget against researched tuition — currencies never converted.

    There is no exchange rate in this system; inventing one would be a
    fabricated number a student plans money around. Different currencies →
    unevaluable, with the reason stated.
    """
    weight = MATCH_WEIGHTS.financial_fit
    budget = profile.preferences.budget
    tuition_fact = program.facts.get("tuition")
    if budget is None or tuition_fact is None:
        return ComponentScore(
            name="financial_fit",
            score=None,
            weight=weight,
            basis=(
                "No budget on the profile."
                if budget is None
                else "Tuition has not been researched for this program."
            ),
        )
    tuition = _first_number(tuition_fact.value)
    if tuition is None:
        return ComponentScore(
            name="financial_fit",
            score=None,
            weight=weight,
            basis=f"Stated tuition '{tuition_fact.value}' is not numeric.",
        )
    budget_currency = (profile.preferences.budget_currency or "").strip().upper()
    tuition_currency = (
        program.facts["tuition_currency"].value.strip().upper()
        if "tuition_currency" in program.facts
        else ""
    )
    if budget_currency and tuition_currency and budget_currency != tuition_currency:
        return ComponentScore(
            name="financial_fit",
            score=None,
            weight=weight,
            basis=(
                f"Budget is in {budget_currency}, tuition in "
                f"{tuition_currency} — no conversion exists here, so this "
                "needs the student's own comparison."
            ),
        )
    if tuition <= budget:
        score, note = 90, "researched tuition fits the stated budget"
    elif tuition <= budget * 1.2:
        score, note = 55, "tuition runs up to ~20% over the stated budget"
    else:
        score, note = 25, "tuition is well above the stated budget"
    return ComponentScore(
        name="financial_fit",
        score=score,
        weight=weight,
        basis=f"Tuition {tuition_fact.value} vs budget {budget}: {note}. "
        "Living costs not included unless researched.",
    )


_RESEARCH_GOALS = ("research", "phd", "professor", "academia", "thesis")
_INDUSTRY_GOALS = (
    "industry",
    "engineer",
    "swe",
    "developer",
    "job",
    "data scientist",
    "product",
    "startup",
)


def _career_fit(profile: StudentProfile, program: Program) -> ComponentScore:
    weight = MATCH_WEIGHTS.career_fit
    goal = (profile.target.career_goal or "").casefold()
    if not goal:
        return ComponentScore(
            name="career_fit",
            score=None,
            weight=weight,
            basis="No career goal on the profile yet.",
        )
    structure = (
        program.facts["structure"].value.casefold()
        if "structure" in program.facts
        else ""
    )
    coop = (
        program.facts["coop_available"].value.casefold()
        if "coop_available" in program.facts
        else ""
    )
    research_goal = any(k in goal for k in _RESEARCH_GOALS)
    industry_goal = any(k in goal for k in _INDUSTRY_GOALS)
    if research_goal and "thesis" in structure:
        score, note = 90, "thesis-based structure suits a research/PhD goal"
    elif industry_goal and coop.startswith(("yes", "true", "available")):
        score, note = 90, "co-op availability suits an industry goal"
    elif research_goal and "course" in structure:
        score, note = 45, "course-based structure is a weaker path to research"
    elif not structure and not coop:
        score, note = 60, "program structure/co-op not researched yet"
    else:
        score, note = 65, "no strong signal either way"
    return ComponentScore(
        name="career_fit",
        score=score,
        weight=weight,
        basis=f"Goal '{profile.target.career_goal}': {note}.",
    )


def _preference_fit(profile: StudentProfile, program: Program) -> ComponentScore:
    weight = MATCH_WEIGHTS.preference_fit
    country = profile.target.country
    if not country:
        return ComponentScore(
            name="preference_fit",
            score=None,
            weight=weight,
            basis="No target country on the profile.",
        )
    if program.country and country.casefold() == program.country.casefold():
        score, note = 90, f"in the target country ({program.country})"
    elif program.country:
        score, note = 30, f"outside the target country ({program.country})"
    else:
        score, note = 50, "program country unknown"
    return ComponentScore(name="preference_fit", score=score, weight=weight, basis=note)


def categorize(score: int) -> str:
    for minimum, category in CATEGORY_THRESHOLDS:
        if score >= minimum:
            return category
    return CATEGORY_THRESHOLDS[-1][1]


def calculate_match_score(
    profile: StudentProfile,
    program: Program,
    weights: MatchWeights | None = None,
) -> MatchResult:
    """Weighted deterministic fit of one profile against one program."""
    del weights  # V1 uses the configured weights; parameter reserved.
    requirements_component, missing = _requirements_fit(profile, program)
    components = [
        _academic_fit(profile, program),
        _program_fit(profile, program),
        _research_fit(profile, program),
        _career_fit(profile, program),
        _experience_fit(profile, program),
        requirements_component,
        _financial_fit(profile, program),
        _preference_fit(profile, program),
    ]

    evaluable = [c for c in components if c.score is not None]
    if evaluable:
        total_weight = sum(c.weight for c in evaluable)
        raw = sum(c.score * c.weight for c in evaluable) / total_weight
        match_score = round(raw)
    else:
        match_score = 0

    strengths = [c.basis for c in evaluable if c.score >= 80]
    risks = [c.basis for c in evaluable if c.score <= 50]
    reasoning = [
        f"{c.name}: {'n/a — ' + c.basis if c.score is None else f'{c.score} ({c.basis})'}"
        for c in components
    ]
    skipped = [c.name for c in components if c.score is None]
    if skipped:
        reasoning.append(
            "Unevaluated dimensions were excluded and weights renormalized: "
            + ", ".join(skipped)
        )

    return MatchResult(
        university=program.university,
        program=program.name,
        match_score=match_score,
        category=categorize(match_score),
        components=components,
        strengths=strengths,
        risks=risks,
        missing_requirements=missing,
        reasoning=reasoning,
    )
