"""The MS strategy engine — cross-domain synthesis, deterministically.

This is the layer that turns eight domains into one recommendation, and it
is code, not prompt: every dimension carries its weight, its kind and its
reason (§14 of the Phase 10 brief); every number comes from app.calc or a
stored graded fact; and the six fact kinds (§22) are never blurred:

    profile_fact       — the student said it (or confirmed it)
    researched_fact    — a stored, evidence-graded claim
    calculated_result  — app.calc or a deterministic derivation over facts
    inference          — a suggested reading of facts, labeled
    recommendation     — what we advise doing about it
    unknown            — absent, and said to be absent

Categories are fit language — strong fit / reasonable fit / ambitious —
never an admission probability (§27). Missing data shrinks the output;
stale data becomes a research need, not a stale answer (§23).
"""

from __future__ import annotations

from typing import Any

from app.application.analysis import (
    APPLICATION_REQUIREMENT_FIELDS,
    application_readiness,
)
from app.calc.finance import budget_fit, total_cost
from app.config.settings import STRATEGY_WEIGHTS
from app.exams.requirements import compare_score, interpret_requirement
from app.finance.analysis import assess_money_freshness, build_cost_model
from app.models.finance import FinanceRecord
from app.models.program import Program
from app.models.student import StudentProfile
from app.placement.analysis import analyze_career_fit
from app.services.matching_service import calculate_match_score
from app.services.question_service import readiness as profile_readiness
from app.university.analysis import assess_deadline_freshness

FACT_KINDS = (
    "profile_fact",
    "researched_fact",
    "calculated_result",
    "inference",
    "recommendation",
    "unknown",
)

_CAREER_FIELDS = ("employment_outcomes", "career_signals", "salary_evidence")
_FUNDING_FIELDS = ("scholarships", "assistantship_evidence", "funding_evidence")


# --- Coverage (§23): what we know vs what the plan needs ---------------------


def assess_coverage(
    profile: StudentProfile,
    programs: list[Program],
    finance_records: list[FinanceRecord],
    alumni: dict[str, Any],
    applications: dict[str, Any],
) -> dict[str, Any]:
    """What is already known, what must be researched before a full plan."""
    intake = profile.target.intake or ""
    needed: list[dict[str, str]] = []

    if not programs:
        needed.append(
            {
                "domain": "universities",
                "target": profile.target.country or "the target country",
                "need": (
                    "discover and research candidate programs — nothing is "
                    "stored to plan over yet"
                ),
            }
        )
    for program in programs:
        target = f"{program.university} — {program.name}"
        deadline = program.facts.get("application_deadline")
        if deadline is None:
            needed.append(
                {
                    "domain": "deadlines",
                    "target": target,
                    "need": "research the application deadline for the target cycle",
                }
            )
        elif assess_deadline_freshness(deadline.value, intake)["status"] == "stale":
            needed.append(
                {
                    "domain": "deadlines",
                    "target": target,
                    "need": "the stored deadline is from a past cycle — refresh it",
                }
            )
        tuition = program.facts.get("tuition")
        if tuition is None:
            needed.append(
                {
                    "domain": "costs",
                    "target": target,
                    "need": "research tuition and mandatory fees",
                }
            )
        elif assess_money_freshness(tuition.value, intake)["status"] == "stale":
            needed.append(
                {
                    "domain": "costs",
                    "target": target,
                    "need": (
                        "refresh the tuition — the stored figure's stated "
                        "year predates the target intake"
                    ),
                }
            )
        if not any(f in program.facts for f in _CAREER_FIELDS):
            needed.append(
                {
                    "domain": "careers",
                    "target": target,
                    "need": "research employment outcomes and career signals",
                }
            )
        if not any(f in program.facts for f in APPLICATION_REQUIREMENT_FIELDS):
            needed.append(
                {
                    "domain": "applications",
                    "target": target,
                    "need": "research the application requirements",
                }
            )
    if programs and not any(
        f in p.facts for p in programs for f in _FUNDING_FIELDS
    ):
        needed.append(
            {
                "domain": "funding",
                "target": "shortlist",
                "need": "research scholarships and assistantships",
            }
        )
    if programs and not alumni:
        needed.append(
            {
                "domain": "alumni",
                "target": "shortlist",
                "need": (
                    "optional: research alumni paths for real-world examples"
                ),
            }
        )

    ready = profile_readiness(profile)
    return {
        "profile": ready,
        "programs_stored": len(programs),
        "finance_scopes_stored": len(finance_records),
        "alumni_stored": len(alumni),
        "applications_tracked": len(applications),
        "research_needed": needed,
        "ready_for_plan": bool(programs)
        and ready["basic_recommendations"]["complete"],
    }


# --- Per-program synthesis (§14, §16) ----------------------------------------


def _financial_dimension(
    profile: StudentProfile,
    program: Program,
    finance_records: list[FinanceRecord],
    weight: float,
) -> dict[str, Any]:
    model = build_cost_model(program, finance_records, profile.target.intake or "")
    inputs = model["calculation_inputs"]
    budget = profile.preferences.budget
    budget_currency = (profile.preferences.budget_currency or "").strip().upper()
    base = {"dimension": "financial_fit", "weight": weight}
    if not inputs["items_low"] or not inputs["years"] or not inputs["currency"]:
        return {
            **base,
            "score": None,
            "verdict": "unknown",
            "kind": "unknown",
            "reason": (
                "No computable cost picture yet — "
                + (
                    "; ".join(e["reason"] for e in inputs["excluded"][:2])
                    or "tuition/duration not researched"
                )
            ),
        }
    if budget is None:
        return {
            **base,
            "score": None,
            "verdict": "unknown",
            "kind": "unknown",
            "reason": "No budget on the profile to compare against.",
        }
    if budget_currency and budget_currency != inputs["currency"]:
        return {
            **base,
            "score": None,
            "verdict": "unknown",
            "kind": "unknown",
            "reason": (
                f"Budget is in {budget_currency}, costs in "
                f"{inputs['currency']} — convert with a sourced rate first."
            ),
        }
    total = total_cost(inputs["items_low"], inputs["years"], inputs["currency"])
    if total.get("status") == "invalid":
        return {
            **base,
            "score": None,
            "verdict": "unknown",
            "kind": "unknown",
            "reason": total.get("message", "cost inputs invalid"),
        }
    fit = budget_fit(budget, total["result"], inputs["currency"])
    verdict = fit["verdict"]
    return {
        **base,
        "score": 100 if verdict == "within_budget" else 25,
        "verdict": verdict,
        "kind": "calculated_result",
        "reason": (
            f"Low-scenario estimated total {total['result']} "
            f"{inputs['currency']} over {inputs['years']} years vs budget "
            f"{budget} — {verdict.replace('_', ' ')} by {fit['result']} "
            f"{inputs['currency']} (assumptions: "
            f"{'; '.join(total['assumptions'][:1])})"
        ),
    }


def synthesize_program(
    profile: StudentProfile,
    program: Program,
    finance_records: list[FinanceRecord],
    alumni: dict[str, Any],
    applications: dict[str, Any],
    weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    """One program, every domain, one transparent strategy row."""
    weights = weights or STRATEGY_WEIGHTS
    match = calculate_match_score(profile, program)
    dimensions: list[dict[str, Any]] = [
        {
            "dimension": "profile_alignment",
            "weight": weights.get("profile_alignment", 0.5),
            "score": match.match_score,
            "kind": "calculated_result",
            "reason": "; ".join(match.strengths[:2] or match.reasoning[:2])
            or f"deterministic match score {match.match_score}",
        },
        _financial_dimension(
            profile, program, finance_records, weights.get("financial_fit", 0.3)
        ),
    ]

    tracked = applications.get(program.key) or {}
    ready = application_readiness(
        profile, program, dict(tracked.get("documents") or {})
    )
    readiness_score = {"ready": 100, "in_progress": 70, "not_ready": 40}.get(
        ready["overall"]
    )
    blockers = [r["requirement"] for r in ready["rows"] if r["verdict"] == "missing"]
    dimensions.append(
        {
            "dimension": "application_readiness",
            "weight": weights.get("application_readiness", 0.2),
            "score": readiness_score,
            "kind": "calculated_result" if readiness_score is not None else "unknown",
            "reason": (
                f"readiness: {ready['overall']}"
                + (f"; blocking: {', '.join(blockers)}" if blockers else "")
                if readiness_score is not None
                else "application requirements not researched yet"
            ),
        }
    )

    roles_text = (
        program.facts["career_signals"].value
        if "career_signals" in program.facts
        else ""
    )
    if roles_text:
        fit = analyze_career_fit(profile, roles_text)
        aligned = ", ".join(r["role"] for r in fit["aligned"][:3])
        dimensions.append(
            {
                "dimension": "career_evidence",
                "weight": 0.0,
                "score": None,
                "kind": "researched_fact",
                "reason": (
                    f"published roles aligned with the profile: {aligned}"
                    if aligned
                    else "career evidence stored; no stated role aligns yet"
                ),
            }
        )
    university_alumni = [
        entry
        for entry in alumni.values()
        if str(entry.get("university", "")).casefold()
        == program.university.casefold()
    ]
    if university_alumni:
        dimensions.append(
            {
                "dimension": "alumni_examples",
                "weight": 0.0,
                "score": None,
                "kind": "researched_fact",
                "reason": (
                    f"{len(university_alumni)} verified public alumni "
                    "profile(s) available as examples — examples, never "
                    "statistics"
                ),
            }
        )

    scored = [d for d in dimensions if d["score"] is not None and d["weight"] > 0]
    total_weight = sum(d["weight"] for d in scored)
    strategy_score = (
        round(sum(d["score"] * d["weight"] for d in scored) / total_weight)
        if total_weight
        else 0
    )
    category = (
        "strong fit"
        if match.match_score >= 80
        else "reasonable fit"
        if match.match_score >= 65
        else "ambitious"
    )
    tags: list[str] = []
    financial = next(d for d in dimensions if d["dimension"] == "financial_fit")
    if financial["verdict"] == "within_budget":
        tags.append("financially attractive")
    elif financial["verdict"] == "shortfall":
        tags.append("financially challenging")
    for component in match.components:
        if component.score is not None and component.score >= 80:
            if component.name == "research_fit":
                tags.append("research-focused")
            if component.name == "career_fit":
                tags.append("career-focused")

    conflicts = [
        {"field": field, **conflict}
        for field, fact in program.facts.items()
        for conflict in fact.conflicts
    ]
    return {
        "university": program.university,
        "program": program.name,
        "category": category,
        "tags": tags,
        "strategy_score": strategy_score,
        "match": {
            "score": match.match_score,
            "category": match.category,
            "strengths": match.strengths,
            "risks": match.risks,
            "missing_requirements": match.missing_requirements,
        },
        "dimensions": dimensions,
        "conflicts": conflicts,
        "note": (
            "A planning fit, never an admission estimate — categories "
            "describe alignment with the profile and constraints, with "
            "each dimension's reason above."
        ),
    }


# --- Exam recommendation (§15) ------------------------------------------------


def recommend_exams(
    profile: StudentProfile, programs: list[Program]
) -> dict[str, Any]:
    """Shortlist-specific exam guidance from researched requirements only."""
    english_rows: list[dict[str, Any]] = []
    gre_lists: dict[str, list[str]] = {
        "required_for": [],
        "optional_for": [],
        "not_required_for": [],
        "conditional_for": [],
        "unknown_for": [],
    }
    score = profile.test_scores.ielts or profile.test_scores.toefl
    for program in programs:
        english = program.facts.get("english_requirement")
        if english is not None:
            interp = interpret_requirement(english.value)
            english_rows.append(
                {
                    "university": program.university,
                    "status": interp["status"],
                    "stated": english.value,
                    "comparison": compare_score(interp, score, None),
                    "source_domain": english.evidence.source_domain,
                    "kind": "researched_fact",
                }
            )
        gre = program.facts.get("gre_requirement")
        if gre is None:
            gre_lists["unknown_for"].append(program.university)
        else:
            status = interpret_requirement(gre.value)["status"]
            bucket = {
                "required": "required_for",
                "optional": "optional_for",
                "not_required": "not_required_for",
                "waived": "not_required_for",
                "conditional": "conditional_for",
                "unknown": "unknown_for",
            }[status]
            gre_lists[bucket].append(program.university)

    english_unverified = [
        p.university for p in programs if "english_requirement" not in p.facts
    ]
    meets = [
        r["university"]
        for r in english_rows
        if r["comparison"]["verdict"] == "meets_stated_minimum"
    ]
    below = [
        r["university"]
        for r in english_rows
        if r["comparison"]["verdict"] == "below_stated_minimum"
    ]
    if score is None:
        english_recommendation = (
            "No English score on the profile yet — book IELTS or TOEFL; "
            "the researched programs state English requirements."
        )
    else:
        english_recommendation = (
            f"Your score meets the stated minimums where verified"
            f" ({', '.join(meets)})" if meets else "Your score is on file"
        )
        if below:
            english_recommendation += f"; below the stated minimum for {', '.join(below)}"
        if english_unverified:
            english_recommendation += (
                f"; still unverified for {', '.join(english_unverified)} — verify"
            )
        english_recommendation += "."

    if gre_lists["required_for"]:
        gre_recommendation = (
            "Plan for the GRE if you keep "
            + ", ".join(gre_lists["required_for"])
            + " on the shortlist — their researched requirements state it."
        )
    elif gre_lists["conditional_for"]:
        gre_recommendation = (
            "GRE is conditional for "
            + ", ".join(gre_lists["conditional_for"])
            + " — the source's own condition decides; quote it."
        )
    else:
        gre_recommendation = (
            "GRE does not appear necessary for the current shortlist based "
            "on the researched requirements."
        )
    if gre_lists["unknown_for"]:
        gre_recommendation += (
            " Verify " + ", ".join(gre_lists["unknown_for"]) + " before deciding."
        )

    return {
        "english": {
            "rows": english_rows,
            "unverified_for": english_unverified,
            "recommendation": english_recommendation,
            "kind": "recommendation",
        },
        "gre": {
            **gre_lists,
            "recommendation": gre_recommendation,
            "kind": "recommendation",
        },
        "note": (
            "Derived only from the shortlist's researched requirements and "
            "the stored scores — programs set requirements, not countries."
        ),
    }


# --- Gaps (§19) ---------------------------------------------------------------


def profile_gaps(
    profile: StudentProfile,
    programs: list[Program],
    applications: dict[str, Any],
) -> list[dict[str, Any]]:
    """What stands between the student and ready applications, prioritized."""
    gaps: list[dict[str, Any]] = []

    def add(gap: str, priority: str, why: str) -> None:
        if not any(g["gap"] == gap for g in gaps):
            gaps.append(
                {"gap": gap, "priority": priority, "why": why, "kind": "inference"}
            )

    has_english = (
        profile.test_scores.ielts is not None or profile.test_scores.toefl is not None
    )
    for program in programs:
        for field, label, has_score in (
            ("english_requirement", "English test", has_english),
            ("gre_requirement", "GRE", profile.test_scores.gre is not None),
        ):
            fact = program.facts.get(field)
            if fact is None:
                continue
            if interpret_requirement(fact.value)["status"] == "required" and not has_score:
                add(
                    f"{label} score missing for {program.university}",
                    "high",
                    f"The researched requirement states it: {fact.value} "
                    f"({fact.evidence.source_domain})",
                )
        tracked = applications.get(program.key) or {}
        ready = application_readiness(
            profile, program, dict(tracked.get("documents") or {})
        )
        for row in ready["rows"]:
            if row["verdict"] == "missing" and row["requirement"] not in (
                "english_requirement",
                "gre_requirement",
            ):
                add(
                    f"{row['requirement'].replace('_requirement', '').upper()} "
                    f"not started for {program.university}",
                    "medium",
                    row["action"],
                )
    if profile.preferences.budget is None:
        add(
            "Total budget unknown",
            "medium",
            "Every affordability comparison needs it.",
        )
    ready_state = profile_readiness(profile)
    for path in ready_state["deep_recommendations"]["missing"][:3]:
        add(
            f"Profile field missing: {path}",
            "low",
            "Sharpens research alignment and recommendations.",
        )
    priority_rank = {"high": 0, "medium": 1, "low": 2}
    gaps.sort(key=lambda g: priority_rank[g["priority"]])
    return gaps


# --- The plan of action (§20, §26) --------------------------------------------


def build_plan(
    profile: StudentProfile,
    programs: list[Program],
    finance_records: list[FinanceRecord],
    alumni: dict[str, Any],
    applications: dict[str, Any],
    weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    """The personalized plan — sections only where evidence supports them."""
    sections: dict[str, Any] = {}
    coverage = assess_coverage(
        profile, programs, finance_records, alumni, applications
    )

    known = profile.known()
    if known:
        sections["profile_snapshot"] = {
            "facts": known,
            "kind": "profile_fact",
            "note": "As stated by the student or confirmed from the resume.",
        }

    shortlist = [
        synthesize_program(
            profile, program, finance_records, alumni, applications, weights
        )
        for program in programs
    ]
    shortlist.sort(key=lambda r: r["strategy_score"], reverse=True)
    if shortlist:
        sections["shortlist"] = shortlist
        sections["exam_plan"] = recommend_exams(profile, programs)

    financial = []
    for row in shortlist:
        dimension = next(
            d for d in row["dimensions"] if d["dimension"] == "financial_fit"
        )
        if dimension["kind"] != "calculated_result":
            continue
        program = next(p for p in programs if p.university == row["university"])
        model = build_cost_model(
            program, finance_records, profile.target.intake or ""
        )
        inputs = model["calculation_inputs"]
        total = total_cost(inputs["items_low"], inputs["years"], inputs["currency"])
        fit = budget_fit(
            profile.preferences.budget or 0, total["result"], inputs["currency"]
        )
        financial.append(
            {
                "university": row["university"],
                "program": row["program"],
                "total": total,
                "budget_fit": fit,
                "excluded": inputs["excluded"],
                "assumptions": inputs["assumptions"],
                "kind": "calculated_result",
            }
        )
    if financial:
        sections["financial_feasibility"] = financial

    funding = [
        {
            "university": program.university,
            "field": field,
            "value": program.facts[field].value,
            "source_domain": program.facts[field].evidence.source_domain,
            "kind": "researched_fact",
        }
        for program in programs
        for field in _FUNDING_FIELDS
        if field in program.facts
    ]
    if funding:
        sections["funding"] = funding

    careers = [
        {
            "university": program.university,
            "field": field,
            "value": program.facts[field].value,
            "source_domain": program.facts[field].evidence.source_domain,
            "kind": "researched_fact",
        }
        for program in programs
        for field in _CAREER_FIELDS
        if field in program.facts
    ]
    if careers:
        sections["career_alignment"] = careers

    if alumni:
        sections["alumni_paths"] = {
            "count": len(alumni),
            "kind": "researched_fact",
            "note": (
                "Real public profiles as examples — present via "
                "get_alumni_signals; examples, never statistics."
            ),
        }

    if applications:
        sections["application_tracker"] = {
            "tracked": len(applications),
            "kind": "calculated_result",
            "note": "Detail lives in get_application_dashboard.",
        }

    gaps = profile_gaps(profile, programs, applications)
    if gaps:
        sections["gaps"] = gaps

    if shortlist or gaps or coverage["research_needed"]:
        weeks: dict[str, list[str]] = {
            "week_1": [g["why"] for g in gaps if g["priority"] == "high"][:3],
            "week_2": [
                f"{n['need']} ({n['target']})"
                for n in coverage["research_needed"][:3]
            ],
            "week_3": [g["why"] for g in gaps if g["priority"] == "medium"][:3],
            "week_4": [
                "Re-check application readiness and submit what is ready "
                "ahead of the verified deadlines."
            ],
        }
        sections["next_30_days"] = {
            k: v for k, v in weeks.items() if v
        }

    if gaps and gaps[0]["priority"] == "high":
        action = {"action": gaps[0]["gap"], "why": gaps[0]["why"]}
    elif coverage["research_needed"]:
        need = coverage["research_needed"][0]
        action = {
            "action": f"{need['need']} ({need['target']})",
            "why": (
                "It is the first missing piece the recommendation depends "
                "on, and it can be researched rather than asked."
            ),
        }
    elif gaps:
        action = {"action": gaps[0]["gap"], "why": gaps[0]["why"]}
    else:
        action = {
            "action": (
                "Re-verify the unknowns on the program pages, then submit "
                "the ready applications."
            ),
            "why": "Everything researched is covered; verification is what remains.",
        }
    sections_present = sorted(sections)
    return {
        "sections": sections,
        "sections_present": sections_present,
        "coverage": coverage,
        "next_best_action": {**action, "kind": "recommendation"},
        "note": (
            "Sections appear only where stored evidence supports them. "
            "Nothing here is a promise of admission, funding or outcomes — "
            "fit language with reasons, unknowns said as unknown."
        ),
    }
