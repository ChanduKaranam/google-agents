"""Phase 10 — the MS strategy engine: coverage, synthesis, plan of action.

The rules pinned before implementation:

* **Cross-domain, not concatenated**: a program's strategy row combines
  the deterministic match score, the finance cost model + calc verdict,
  application readiness and alumni presence — each dimension with weight,
  kind and reason (§14). Weights are configurable; scores are never
  hidden.
* **Six kinds, never blurred** (§22): profile_fact / researched_fact /
  calculated_result / inference / recommendation / unknown.
* **No admission probability, ever** (§27): categories are fit language
  with reasons; a rendered plan contains no percentage chance and no
  "admission probability".
* **Missing data shrinks the plan** (§26): sections appear only when the
  evidence behind them exists; missing stays missing, stale is flagged
  for refresh, unknown says verify.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from app.config.settings import (
    STATE_PROFILE,
    STRATEGY_WEIGHTS,
)
from app.models.program import Program
from app.models.student import StudentProfile
from app.strategy.engine import (
    FACT_KINDS,
    assess_coverage,
    build_plan,
    profile_gaps,
    recommend_exams,
    synthesize_program,
)
from app.tools.strategy_tools import (
    build_action_plan,
    build_recommendations,
    get_strategy_readiness,
)


class StubToolContext:
    def __init__(self) -> None:
        self.state: dict[str, Any] = {}
        self.invocation_id = "test"
        self.session = SimpleNamespace(events=[])


def student() -> StudentProfile:
    return StudentProfile.model_validate(
        {
            "education": {
                "degree": "Bachelor's",
                "major": "Computer Science and Engineering",
                "cgpa": 8.2,
                "grading_scale": "10",
            },
            "test_scores": {"ielts": 7.0},
            "technical": {"skills": ["Python", "TensorFlow"]},
            "preferences": {"budget": 100000, "budget_currency": "CAD"},
            "target": {
                "country": "Canada",
                "intake": "Fall 2027",
                "specialization": "AI/ML",
                "career_goal": "ML Engineer",
            },
        }
    )


def program(name: str, facts: dict[str, str], university: str = "") -> Program:
    return Program.model_validate(
        {
            "university": university or f"University of {name}",
            "name": "MSc Computer Science",
            "country": "Canada",
            "city": name,
            "facts": {
                field: {
                    "value": value,
                    "status": "verified",
                    "evidence": {
                        "source_domain": f"{name.lower()}.ca",
                        "source_type": "official",
                        "retrieved_at": "2026-08-11T00:00:00+00:00",
                    },
                }
                for field, value in facts.items()
            },
        }
    )


AFFORDABLE = {
    "tuition": "CAD 30,000 per year (2026)",
    "duration": "2 years",
    "curriculum": "machine learning, artificial intelligence, computer vision",
    "english_requirement": "IELTS overall 6.5 required",
    "gre_requirement": "GRE is not required",
    "application_deadline": "December 15, 2026",
    "sop_requirement": "A statement of purpose is required",
}

EXPENSIVE = {
    "tuition": "CAD 70,000 per year (2026)",
    "duration": "2 years",
    "curriculum": "machine learning, data systems",
    "english_requirement": "IELTS overall 7.0 required",
    "gre_requirement": "GRE required for all applicants",
}


# --- Coverage (§23) -----------------------------------------------------------


def test_missing_deadlines_become_research_needs_not_questions() -> None:
    coverage = assess_coverage(student(), [program("Alpha", EXPENSIVE)], [], {}, {})
    needs = {(n["domain"], n["target"]) for n in coverage["research_needed"]}
    assert ("deadlines", "University of Alpha — MSc Computer Science") in needs


def test_stale_costs_are_flagged_for_refresh() -> None:
    stale = dict(AFFORDABLE, tuition="CAD 28,000 per year (2023-2024)")
    coverage = assess_coverage(student(), [program("Alpha", stale)], [], {}, {})
    needs = [n for n in coverage["research_needed"] if n["domain"] == "costs"]
    assert needs
    assert "refresh" in needs[0]["need"].casefold()


def test_no_programs_means_discovery_first() -> None:
    coverage = assess_coverage(student(), [], [], {}, {})
    assert coverage["ready_for_plan"] is False
    assert any(n["domain"] == "universities" for n in coverage["research_needed"])


# --- Program synthesis (§14, §16) ---------------------------------------------


def test_synthesis_carries_weighted_dimensions_with_kinds() -> None:
    row = synthesize_program(student(), program("Alpha", AFFORDABLE), [], {}, {})
    assert row["category"] in ("strong fit", "reasonable fit", "ambitious")
    dimensions = {d["dimension"]: d for d in row["dimensions"]}
    assert "profile_alignment" in dimensions
    assert "financial_fit" in dimensions
    for dimension in dimensions.values():
        assert dimension["kind"] in FACT_KINDS
        assert dimension["reason"]
    assert abs(sum(d["weight"] for d in row["dimensions"] if d["score"] is not None)) > 0


def test_affordability_is_computed_by_calc_never_assumed() -> None:
    row = synthesize_program(student(), program("Alpha", AFFORDABLE), [], {}, {})
    financial = next(d for d in row["dimensions"] if d["dimension"] == "financial_fit")
    # budget 100k CAD vs 30k×2 → within budget, computed not asserted
    assert financial["verdict"] == "within_budget"
    assert financial["kind"] == "calculated_result"
    row = synthesize_program(student(), program("Beta", EXPENSIVE), [], {}, {})
    financial = next(d for d in row["dimensions"] if d["dimension"] == "financial_fit")
    assert financial["verdict"] == "shortfall"
    assert "financially challenging" in row["tags"]


def test_unknown_costs_stay_unknown_not_scored() -> None:
    no_money = {k: v for k, v in AFFORDABLE.items() if k != "tuition"}
    row = synthesize_program(student(), program("Alpha", no_money), [], {}, {})
    financial = next(d for d in row["dimensions"] if d["dimension"] == "financial_fit")
    assert financial["score"] is None
    assert financial["verdict"] == "unknown"


def test_no_probability_language_anywhere() -> None:
    row = synthesize_program(student(), program("Alpha", AFFORDABLE), [], {}, {})
    rendered = str(row).casefold()
    assert "probability" not in rendered
    assert "admission chance" not in rendered
    assert "chance of admission" not in rendered


def test_weights_are_configurable_and_reorder() -> None:
    affordable = program("Alpha", AFFORDABLE)
    expensive = program("Beta", EXPENSIVE)
    default_rows = [
        synthesize_program(student(), p, [], {}, {}) for p in (affordable, expensive)
    ]
    finance_heavy = {**STRATEGY_WEIGHTS, "financial_fit": 0.9, "profile_alignment": 0.05, "application_readiness": 0.05}
    heavy_rows = [
        synthesize_program(student(), p, [], {}, {}, weights=finance_heavy)
        for p in (affordable, expensive)
    ]
    assert heavy_rows[0]["strategy_score"] != default_rows[0]["strategy_score"] or (
        heavy_rows[1]["strategy_score"] != default_rows[1]["strategy_score"]
    )


def test_conflicting_facts_surface_never_vanish() -> None:
    conflicted = program("Alpha", AFFORDABLE)
    conflicted.facts["tuition"].conflicts.append(
        {"value": "CAD 35,000 per year", "source_domain": "other.ca", "retrieved_at": "x"}
    )
    row = synthesize_program(student(), conflicted, [], {}, {})
    assert row["conflicts"]
    assert row["conflicts"][0]["field"] == "tuition"


# --- Exam recommendation (§15) ------------------------------------------------


def test_exam_recommendation_is_shortlist_specific() -> None:
    programs = [program("Alpha", AFFORDABLE), program("Beta", EXPENSIVE)]
    result = recommend_exams(student(), programs)
    gre = result["gre"]
    assert "University of Beta" in gre["required_for"]
    assert "University of Alpha" in gre["not_required_for"]
    assert gre["recommendation"]
    english = result["english"]
    assert english["rows"]
    for row in english["rows"]:
        assert row["source_domain"]


def test_unverified_exam_requirements_are_named_not_assumed() -> None:
    bare = program("Gamma", {"tuition": "CAD 20,000 per year"})
    result = recommend_exams(student(), [bare])
    assert "University of Gamma" in result["gre"]["unknown_for"]
    assert "verify" in result["gre"]["recommendation"].casefold()


# --- Gaps (§19) ---------------------------------------------------------------


def test_gaps_are_prioritized_with_reasons() -> None:
    gaps = profile_gaps(student(), [program("Beta", EXPENSIVE)], {})
    by_gap = {g["gap"]: g for g in gaps}
    gre_gap = next(g for g in gaps if "gre" in g["gap"].casefold())
    assert gre_gap["priority"] == "high"
    assert gre_gap["why"]
    assert all(g["priority"] in ("high", "medium", "low") for g in by_gap.values())


# --- The plan (§20, §26) ------------------------------------------------------


def full_context() -> StubToolContext:
    context = StubToolContext()
    context.state[STATE_PROFILE] = student().model_dump()
    context.state["user:program_knowledge"] = {
        p.key: p.model_dump()
        for p in (program("Alpha", AFFORDABLE), program("Beta", EXPENSIVE))
    }
    return context


def test_plan_sections_appear_only_when_supported() -> None:
    plan = build_plan(student(), [program("Alpha", AFFORDABLE)], [], {}, {})
    assert "shortlist" in plan["sections"]
    assert "financial_feasibility" in plan["sections"]
    assert "alumni_paths" not in plan["sections"]  # nothing stored
    bare_plan = build_plan(student(), [], [], {}, {})
    assert "shortlist" not in bare_plan["sections"]
    assert "financial_feasibility" not in bare_plan["sections"]
    assert bare_plan["next_best_action"]


def test_the_plan_computes_money_through_calc() -> None:
    plan = build_plan(student(), [program("Alpha", AFFORDABLE)], [], {}, {})
    financial = plan["sections"]["financial_feasibility"][0]
    assert financial["total"]["result"] == 60000  # 30,000 × 2 years, from app.calc
    assert financial["budget_fit"]["verdict"] == "within_budget"
    assert financial["kind"] == "calculated_result"


def test_the_plan_always_names_the_next_best_action() -> None:
    plan = build_plan(student(), [program("Beta", EXPENSIVE)], [], {}, {})
    action = plan["next_best_action"]
    assert action["action"]
    assert action["why"]
    assert action["kind"] == "recommendation"


def test_the_plan_never_promises_outcomes() -> None:
    plan = build_plan(student(), [program("Alpha", AFFORDABLE)], [], {}, {})
    rendered = str(plan).casefold()
    assert "you will get" not in rendered
    assert "probability" not in rendered
    assert "guaranteed" not in rendered


# --- The tools ----------------------------------------------------------------


def test_strategy_readiness_reads_the_session() -> None:
    result = get_strategy_readiness(full_context())
    assert result["status"] == "success"
    assert "research_needed" in result["coverage"]


def test_recommendations_require_programs() -> None:
    context = StubToolContext()
    context.state[STATE_PROFILE] = student().model_dump()
    result = build_recommendations(context)
    assert result["status"] == "error"
    assert result["reason"] == "no_programs_researched"


def test_recommendations_rank_and_explain() -> None:
    result = build_recommendations(full_context())
    assert result["status"] == "success"
    assert len(result["shortlist"]) == 2
    top = result["shortlist"][0]
    assert top["strategy_score"] >= result["shortlist"][1]["strategy_score"]
    assert top["dimensions"]


def test_the_action_plan_tool_needs_a_profile() -> None:
    result = build_action_plan(StubToolContext())
    assert result["status"] == "error"
    assert result["reason"] == "empty_profile"


def test_the_action_plan_tool_builds_from_state() -> None:
    result = build_action_plan(full_context())
    assert result["status"] == "success"
    assert result["plan"]["next_best_action"]
    assert "exam_plan" in result["plan"]["sections"]
