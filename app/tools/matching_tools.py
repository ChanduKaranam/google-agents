"""Matching tool — the deterministic engine, exposed to the orchestrator."""

from __future__ import annotations

from google.adk.tools import ToolContext

from app.config.settings import STATE_KNOWLEDGE
from app.models.program import Program
from app.services.matching_service import calculate_match_score
from app.tools.profile_tools import _read_profile


def match_programs(tool_context: ToolContext) -> dict:
    """Score every researched program against the stored student profile.

    The scores are computed deterministically from structured fields —
    explain them using the components and reasoning returned; never adjust
    a number or reorder the ranking.

    Returns:
        Results sorted best-first, each with match_score, category,
        per-component breakdown, strengths, risks and missing requirements.
        Unevaluable dimensions are excluded and named, never scored 0.
    """
    profile = _read_profile(tool_context.state)
    if not profile.known():
        return {
            "status": "error",
            "reason": "empty_profile",
            "message": (
                "Nothing is known about the student yet. Build the profile "
                "first — at minimum the CGPA and its scale."
            ),
        }

    knowledge = tool_context.state.get(STATE_KNOWLEDGE)
    knowledge = knowledge if isinstance(knowledge, dict) else {}
    if not knowledge:
        return {
            "status": "error",
            "reason": "no_programs_researched",
            "message": (
                "No programs are in the knowledge store yet. Research "
                "programs first, then match."
            ),
        }

    results = [
        calculate_match_score(profile, Program.model_validate(raw)).model_dump()
        for raw in knowledge.values()
    ]
    results.sort(key=lambda r: r["match_score"], reverse=True)
    return {
        "status": "success",
        "count": len(results),
        "results": results,
        "note": (
            "Fit scores are planning aids computed from the profile and "
            "researched facts — never admission probabilities."
        ),
    }
