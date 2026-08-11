"""Strategy tools — the cross-domain layer, exposed to the orchestrator.

Read-only over everything the other domains stored: profile, programs,
finance records, alumni, tracked applications. The engine synthesizes;
these tools wrap it with honest empty-state errors. Research still flows
through the one research agent — `get_strategy_readiness` names what to
research, it never fetches (§23).
"""

from __future__ import annotations

from typing import Any

from google.adk.tools import ToolContext

from app.config.settings import (
    STATE_ALUMNI,
    STATE_APPLICATIONS,
    STATE_KNOWLEDGE,
)
from app.models.program import Program
from app.strategy.engine import (
    assess_coverage,
    build_plan,
    recommend_exams,
    synthesize_program,
)
from app.tools.finance_tools import _stored_records
from app.tools.profile_tools import _read_profile


def _programs(state: Any) -> list[Program]:
    knowledge = state.get(STATE_KNOWLEDGE)
    knowledge = knowledge if isinstance(knowledge, dict) else {}
    return [Program.model_validate(raw) for raw in knowledge.values()]


def _alumni(state: Any) -> dict[str, Any]:
    alumni = state.get(STATE_ALUMNI)
    return alumni if isinstance(alumni, dict) else {}


def _applications(state: Any) -> dict[str, Any]:
    store = state.get(STATE_APPLICATIONS)
    return store if isinstance(store, dict) else {}


def get_strategy_readiness(tool_context: ToolContext) -> dict:
    """What is known across every domain, and what to research before a plan.

    Call this FIRST when the student asks a whole-journey question ("which
    university is best for me?", "what should I do?", "build my plan").
    It returns the coverage picture and `research_needed` — research those
    gaps through the normal flows instead of asking the student things
    research can answer, then build the recommendations or the plan.

    Returns:
        Per-domain coverage, research needs with targets, and whether a
        full plan is already supportable.
    """
    profile = _read_profile(tool_context.state)
    coverage = assess_coverage(
        profile,
        _programs(tool_context.state),
        _stored_records(tool_context.state),
        _alumni(tool_context.state),
        _applications(tool_context.state),
    )
    return {
        "status": "success",
        "coverage": coverage,
        "note": (
            "Research the named gaps before finalizing recommendations; "
            "ask the student only what research cannot answer."
        ),
    }


def recommend_exam_plan(tool_context: ToolContext) -> dict:
    """Shortlist-specific exam recommendation from researched requirements.

    Returns:
        English and GRE guidance derived only from the stored shortlist's
        interpreted requirements and the student's scores — with the
        programs still unverified named. Never generic advice.
    """
    programs = _programs(tool_context.state)
    if not programs:
        return {
            "status": "error",
            "reason": "no_programs_researched",
            "message": "Research a shortlist first — exam advice is per program.",
        }
    profile = _read_profile(tool_context.state)
    return {"status": "success", **recommend_exams(profile, programs)}


def build_recommendations(tool_context: ToolContext) -> dict:
    """The cross-domain shortlist: every program, every dimension, ranked.

    Each entry carries its category (strong fit / reasonable fit /
    ambitious — fit language, never an admission estimate), tags,
    weighted dimensions with kinds and reasons, retained conflicts, and
    the deterministic strategy score. Explain the ranking; never adjust
    or reorder it.

    Returns:
        The ranked shortlist, or an honest error when nothing is stored.
    """
    profile = _read_profile(tool_context.state)
    if not profile.known():
        return {
            "status": "error",
            "reason": "empty_profile",
            "message": "Nothing is known about the student yet — interview first.",
        }
    programs = _programs(tool_context.state)
    if not programs:
        return {
            "status": "error",
            "reason": "no_programs_researched",
            "message": "No programs stored — research candidates first.",
        }
    finance = _stored_records(tool_context.state)
    alumni = _alumni(tool_context.state)
    applications = _applications(tool_context.state)
    shortlist = [
        synthesize_program(profile, program, finance, alumni, applications)
        for program in programs
    ]
    shortlist.sort(key=lambda r: r["strategy_score"], reverse=True)
    return {
        "status": "success",
        "shortlist": shortlist,
        "note": (
            "Deterministic synthesis over stored evidence — relay the "
            "dimensions and reasons; never a probability, never a promise."
        ),
    }


def build_action_plan(tool_context: ToolContext) -> dict:
    """The personalized MS plan of action from everything stored.

    Sections appear only where evidence supports them: profile snapshot,
    shortlist, exam plan, financial feasibility (computed by the calc
    tools' engine), funding, careers, alumni pointers, gaps with
    priorities, a 30-day sequence, and always the single next best
    action. Present it prioritized — the answer to "what should I do
    next?", not a data dump.

    Returns:
        The structured plan, or an honest error when no profile exists.
    """
    profile = _read_profile(tool_context.state)
    if not profile.known():
        return {
            "status": "error",
            "reason": "empty_profile",
            "message": (
                "Nothing is known about the student yet — the plan would "
                "be generic, which is exactly what it must not be."
            ),
        }
    plan = build_plan(
        profile,
        _programs(tool_context.state),
        _stored_records(tool_context.state),
        _alumni(tool_context.state),
        _applications(tool_context.state),
    )
    return {"status": "success", "plan": plan}
