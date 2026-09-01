"""Progressive hints and the explicit reveal (research doc, sections 13-14).

Hints are authored per case, so scaffolding is faculty-controlled rather than
whatever the model feels like saying. Both tools cost the student marks, and
the cost is applied deterministically in the scorer.
"""

from __future__ import annotations

from typing import Any

from google.adk.tools import ToolContext

from .. import session as S
from ..config import MAX_HINT_LEVEL
from ..cases import get_case


def give_hint(tool_context: ToolContext) -> dict[str, Any]:
    """Gives the next progressive hint for the active case.

    Each hint is more directive than the last; the third is the last one
    available. Hints reduce the final score, so tell the student the cost
    before using this if they have not already been told.

    Returns:
        The hint text and how many remain.
    """
    enc = S.get(tool_context.state)
    case = get_case(enc.get("case_id") or "")
    if case is None:
        return {"status": "no_active_case"}

    level = int(enc.get("hints_used", 0)) + 1
    if level > min(MAX_HINT_LEVEL, len(case.hints)):
        return {
            "status": "exhausted",
            "message": (
                "No hints left. Offer reveal_answer, and say it ends the case "
                "with a substantially reduced score."
            ),
        }

    enc["hints_used"] = level
    S.put(tool_context.state, enc)
    return {
        "status": "ok",
        "hint_level": level,
        "hint": case.hints[level - 1],
        "hints_remaining": min(MAX_HINT_LEVEL, len(case.hints)) - level,
        "score_effect": f"Hint level {level} applied to the final score.",
        "reminder": (
            "Give the hint and nothing more. Do not expand it, do not add an "
            "example, do not narrow it to one diagnosis."
        ),
    }


def reveal_answer(confirmed_by_student: bool, tool_context: ToolContext) -> dict[str, Any]:
    """Ends Practice Mode and reveals the diagnosis and full reasoning.

    Only call this when the student has explicitly asked for the answer AND
    confirmed they want the case ended. This caps the final score.

    Args:
        confirmed_by_student: True only if the student has explicitly confirmed
            they want the answer now.

    Returns:
        The diagnosis, the reasoning and the teaching points.
    """
    enc = S.get(tool_context.state)
    case = get_case(enc.get("case_id") or "")
    if case is None:
        return {"status": "no_active_case"}
    if not confirmed_by_student:
        return {
            "status": "not_confirmed",
            "message": (
                "Ask the student to confirm. Offer give_hint as the alternative "
                "and state that revealing caps the score."
            ),
        }

    enc["revealed"] = True
    S.put(tool_context.state, enc)
    return {
        "status": "ok",
        "final_diagnosis": case.final_diagnosis,
        "reasoning": case.diagnosis_reasoning,
        "critical_clues": case.critical_clues,
        "red_flags": case.red_flags,
        "teaching_points": case.teaching_points,
        "revision_topics": case.revision_topics,
        "next": (
            "Still run clinical_evaluator so the student sees where their "
            "process broke down, not just the answer."
        ),
    }
