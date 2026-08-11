"""The finance research planner — question in, research requirements out.

Deterministic (§5 of the Phase 7 brief): the model phrases questions and
narrates results; this code decides what a financial question actually
requires — which intents it carries, which facts are missing for them,
which calculation closes the loop, and the single next profile question
worth asking (§7). No fixed questionnaire, no search-everything.
"""

from __future__ import annotations

import re
from typing import Any

from app.models.finance import FinanceRecord
from app.models.program import Program
from app.models.student import StudentProfile

# Ordered markers; a question can carry several intents at once.
_INTENT_MARKERS: tuple[tuple[str, str], ...] = (
    ("tuition", r"tuition|course fee|program fee"),
    (
        "living_cost",
        r"living (cost|expense)|living expenses|cost of living|monthly expense",
    ),
    ("housing", r"housing|accommodation|\brent\b|dorm|hostel"),
    ("insurance", r"insurance"),
    ("transport", r"transport|commute"),
    ("food", r"\bfood\b|grocer|meal plan"),
    ("scholarship", r"scholarship|financial aid|fee waiver|\bgrant\b"),
    (
        "assistantship",
        r"assistantship|teaching assistant|research assistant|\bta\b|\bra\b",
    ),
    ("part_time_work", r"part[ -]?time|work (during|while|alongside)"),
    ("loan", r"\bloan\b|\bemi\b|borrow"),
    ("interest_rate", r"interest rate"),
    (
        "visa_financial_requirement",
        r"\bvisa\b|proof of funds|show (funds|money)|\bgic\b",
    ),
    ("application_cost", r"application fee"),
    ("deposit", r"deposit"),
    (
        "university_comparison",
        r"compare|cheaper|cheapest|\bvs\b|versus|which .*(university|option)",
    ),
    ("roi", r"\broi\b|worth (it|the)|return on investment"),
    ("payback", r"payback|pay back|break ?even|recover"),
    ("currency", r"exchange rate|convert"),
    (
        "financial_timeline",
        r"when (do|will|should) i (pay|need)|save before|before applying",
    ),
    ("budget_fit", r"afford|budget|enough (money|funds)|fund my|manage with"),
    (
        "total_cost",
        r"how much money|total cost|overall cost|entire program|whole program"
        r"|costs? of (doing|studying)|money do i need|hidden cost|expenses",
    ),
)

_TOTAL_COST_PROGRAM_FIELDS = (
    "tuition",
    "tuition_currency",
    "mandatory_fees",
    "billing_structure",
    "duration",
    "living_cost_estimate",
    "housing_cost",
    "health_insurance_cost",
)

# Intent → what answering it needs. Facts already stored are subtracted at
# plan time; nothing here triggers research for a category the question
# never raised.
INTENT_NEEDS: dict[str, dict[str, Any]] = {
    "tuition": {
        "program_fields": (
            "tuition",
            "tuition_currency",
            "mandatory_fees",
            "billing_structure",
            "duration",
        ),
        "calculations": ("calculate_total_cost",),
    },
    "living_cost": {
        "program_fields": ("living_cost_estimate",),
        "finance": (
            ("living_cost", "the university's city"),
            ("housing", "the university's city"),
            ("food", "the university's city"),
            ("transport", "the university's city"),
            ("utilities", "the university's city"),
        ),
    },
    "housing": {
        "program_fields": ("housing_cost",),
        "finance": (("housing", "the university's city"),),
    },
    "insurance": {
        "program_fields": ("health_insurance_cost",),
        "finance": (("health_insurance", "the university or its country"),),
    },
    "transport": {"finance": (("transport", "the university's city"),)},
    "food": {"finance": (("food", "the university's city"),)},
    "scholarship": {
        "program_fields": ("scholarships", "funding_evidence"),
        "finance": (("external_scholarships", "country or provider"),),
        "profile_paths": ("education.cgpa",),
        "notes": (
            "Scholarships are published eligibility criteria the student "
            "may meet — never a promised award.",
        ),
    },
    "assistantship": {
        "program_fields": ("assistantship_evidence", "funding_evidence"),
        "notes": (
            "Assistantships are opportunities with stated conditions — "
            "never assumed income.",
        ),
    },
    "part_time_work": {
        "finance": (("part_time_work_rules", "country — government source only"),),
        "notes": (
            "The legal work limit (government-sourced) and expected "
            "earnings are separate things; part-time work is never "
            "assumed to cover tuition.",
        ),
    },
    "loan": {
        "finance": (
            ("loan_terms", "the lender's official pages"),
            ("interest_rate", "the lender's official pages"),
        ),
        "calculations": ("calculate_loan_emi",),
        "profile_paths": ("preferences.funding_plan",),
    },
    "interest_rate": {
        "finance": (("interest_rate", "the lender's official pages"),),
    },
    "visa_financial_requirement": {
        "finance": (
            ("visa_financial_requirement", "country — government source only"),
        ),
    },
    "application_cost": {"program_fields": ("application_fee",)},
    "deposit": {"program_fields": ("deposit",)},
    "university_comparison": {
        "program_fields": _TOTAL_COST_PROGRAM_FIELDS,
        "calculations": ("calculate_total_cost",),
        "notes": (
            "Each university is researched separately; figures with "
            "different years or scopes are compared only with the "
            "difference stated.",
        ),
    },
    "roi": {
        "program_fields": ("tuition", "duration", "salary_evidence"),
        "calculations": ("calculate_total_cost", "calculate_payback"),
        "notes": (
            "Payback is assumption-bound; researched salary evidence "
            "keeps its scope and never becomes a personal projection.",
        ),
    },
    "payback": {
        "program_fields": ("tuition", "duration", "salary_evidence"),
        "calculations": ("calculate_total_cost", "calculate_payback"),
    },
    "currency": {
        "finance": (("exchange_rate", "a sourced market rate with its date"),),
        "calculations": ("convert_money",),
    },
    "financial_timeline": {
        "program_fields": ("application_deadline", "application_fee", "deposit"),
        "finance": (
            ("visa_financial_requirement", "country — government source only"),
        ),
    },
    "total_cost": {
        "program_fields": _TOTAL_COST_PROGRAM_FIELDS,
        "finance": (
            ("living_cost", "the university's city"),
            ("housing", "the university's city"),
        ),
        "calculations": ("calculate_total_cost",),
    },
    "budget_fit": {
        "program_fields": _TOTAL_COST_PROGRAM_FIELDS,
        "finance": (
            ("living_cost", "the university's city"),
            ("housing", "the university's city"),
        ),
        "calculations": (
            "convert_money",
            "calculate_total_cost",
            "calculate_budget_fit",
        ),
        "profile_paths": (
            "preferences.budget",
            "preferences.budget_currency",
            "preferences.funding_plan",
        ),
    },
}

# The one-question-at-a-time bank for financial gaps (§7), in ask order.
_GAP_QUESTIONS: dict[str, tuple[str, str]] = {
    "preferences.budget": (
        "What is your approximate total MS budget, including tuition and living?",
        "Every affordability answer is relative to it.",
    ),
    "preferences.budget_currency": (
        "Which currency is that budget in?",
        "Cross-currency comparisons need a sourced conversion.",
    ),
    "preferences.funding_plan": (
        "Is that amount from savings/family funds, or would you also "
        "consider an education loan?",
        "Changes which funding research and calculations matter.",
    ),
    "education.cgpa": (
        "What's your CGPA? Scholarship criteria usually state a minimum.",
        "Needed to read published eligibility criteria against the profile.",
    ),
}


def classify_financial_intents(question: str) -> list[str]:
    """Every financial intent the question's own words carry."""
    flat = " ".join(str(question or "").casefold().split())
    return [intent for intent, marker in _INTENT_MARKERS if re.search(marker, flat)]


def _profile_value(profile: StudentProfile, path: str) -> Any:
    section, field = path.split(".")
    return getattr(getattr(profile, section), field)


def plan_finance_research(
    question: str,
    profile: StudentProfile,
    programs: list[Program],
    finance_records: list[FinanceRecord],
) -> dict[str, Any]:
    """What this financial question requires that we do not yet have."""
    intents = classify_financial_intents(question)
    intent_note = None
    if not intents:
        intents = ["total_cost"]
        intent_note = (
            "No specific financial marker matched — planned as a general "
            "cost question."
        )

    program_fields: list[str] = []
    finance_needs: list[tuple[str, str]] = []
    calculations: list[str] = []
    profile_paths: list[str] = []
    notes: list[str] = []
    for intent in intents:
        needs = INTENT_NEEDS.get(intent, {})
        for field in needs.get("program_fields", ()):
            if field not in program_fields:
                program_fields.append(field)
        for pair in needs.get("finance", ()):
            if pair not in finance_needs:
                finance_needs.append(pair)
        for calc in needs.get("calculations", ()):
            if calc not in calculations:
                calculations.append(calc)
        for path in needs.get("profile_paths", ()):
            if path not in profile_paths:
                profile_paths.append(path)
        for note in needs.get("notes", ()):
            if note not in notes:
                notes.append(note)

    research_requirements = [
        {
            "target": f"{program.university} — {program.name}",
            "missing_program_fields": [
                f for f in program_fields if f not in program.facts
            ],
        }
        for program in programs
    ]
    stored_categories = {
        category for record in finance_records for category in record.facts
    }
    finance_research = [
        {"category": category, "scope_hint": hint}
        for category, hint in finance_needs
        if category not in stored_categories
    ]

    gaps = [p for p in profile_paths if _profile_value(profile, p) in (None, "", [])]
    next_question = None
    for path in gaps:
        if path in _GAP_QUESTIONS:
            text, why = _GAP_QUESTIONS[path]
            next_question = {"path": path, "question": text, "why": why}
            break

    return {
        "intents": intents,
        "intent_note": intent_note,
        "needs_discovery": bool(program_fields) and not programs,
        "research_requirements": research_requirements,
        "finance_research": finance_research,
        "profile_gaps": gaps,
        "next_question": next_question,
        "calculations": calculations,
        "notes": notes,
    }
