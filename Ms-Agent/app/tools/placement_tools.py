"""Placement tool — the per-university career picture from stored evidence.

Aggregate career evidence lives in program facts (researched, gated);
individual people live in the alumni system with its own gate. This tool
analyzes the aggregates and points at the alumni signals — it never merges
the two semantics (§26), never invents a statistic from examples, and
never upgrades a scope.
"""

from __future__ import annotations

from typing import Any

from google.adk.tools import ToolContext

from app.config.settings import STATE_ALUMNI, STATE_KNOWLEDGE
from app.models.program import Program
from app.placement.analysis import (
    analyze_career_fit,
    classify_scope,
    extract_salary_attributes,
)
from app.tools.profile_tools import _read_profile

_CAREER_FIELDS = (
    "employment_outcomes",
    "career_signals",
    "salary_evidence",
    "employer_evidence",
    "career_locations",
    "industry_evidence",
)


def _cell(program: Program, field: str) -> dict[str, Any]:
    fact = program.facts.get(field)
    if fact is None:
        return {"status": "unknown", "note": "Not researched for this program."}
    cell: dict[str, Any] = {
        "status": fact.status,
        "value": fact.value,
        "scope": classify_scope(fact.value),
        "source_domain": fact.evidence.source_domain,
        "source_type": fact.evidence.source_type,
        "url": fact.evidence.url,
        "retrieved_at": fact.evidence.retrieved_at,
    }
    if fact.conflicts:
        cell["conflicts"] = fact.conflicts
    if field == "salary_evidence":
        cell["attributes"] = extract_salary_attributes(fact.value)
    return cell


def analyze_career_outcomes(tool_context: ToolContext) -> dict:
    """Analyze researched career evidence per university, profile-aligned.

    Reads only stored, evidence-graded career facts. Every aggregate
    carries its stated scope (program / faculty / university / market
    benchmark / unclear) — present it at that scope and never narrower.
    Salary evidence carries extracted attributes and, when it is a market
    benchmark, must be presented as one. Role evidence is aligned with the
    student's stated profile deterministically. Individual people are the
    alumni system's job — cite `get_alumni_signals` for examples and never
    turn examples into statistics.

    Returns:
        Per-university career analysis with scopes, sources, retrieval
        dates, profile fit, and unknowns stated as unknown.
    """
    knowledge = tool_context.state.get(STATE_KNOWLEDGE)
    knowledge = knowledge if isinstance(knowledge, dict) else {}
    programs = [Program.model_validate(raw) for raw in knowledge.values()]
    with_career = [p for p in programs if any(f in p.facts for f in _CAREER_FIELDS)]
    if not with_career:
        return {
            "status": "error",
            "reason": "no_career_evidence",
            "message": (
                "No career evidence is stored yet. Research the "
                "universities' employment reports and career pages first "
                "(employment_outcomes, career_signals, salary_evidence, "
                "employer_evidence, career_locations, industry_evidence)."
            ),
        }

    profile = _read_profile(tool_context.state)
    alumni_count = len(tool_context.state.get(STATE_ALUMNI) or {})

    universities = []
    for program in with_career:
        roles_text = (
            program.facts["career_signals"].value
            if "career_signals" in program.facts
            else ""
        )
        universities.append(
            {
                "university": program.university,
                "program": program.name,
                "employment_outcomes": _cell(program, "employment_outcomes"),
                "roles": _cell(program, "career_signals"),
                "salary_evidence": _cell(program, "salary_evidence"),
                "employers": _cell(program, "employer_evidence"),
                "locations": _cell(program, "career_locations"),
                "industries": _cell(program, "industry_evidence"),
                "career_fit": analyze_career_fit(profile, roles_text),
            }
        )
    return {
        "status": "success",
        "universities": universities,
        "verified_alumni_examples_available": alumni_count,
        "note": (
            "Aggregates only, each at its stated scope — never upgrade a "
            "faculty or market figure to program level, and never present "
            "a benchmark as a university salary. Individual career "
            "examples come from get_alumni_signals and are examples, "
            "never statistics. Nothing here expresses an employment "
            "likelihood of any kind."
        ),
    }
