"""Examination and investigation gating.

Findings exist only in the case file. If the student asks for something the
case does not define, the tool says so — the model is never in a position to
invent a heart sound or a troponin value.
"""

from __future__ import annotations

from typing import Any

from google.adk.tools import ToolContext

from .. import session as S
from ..cases import get_case
from ..cases.matching import match_all


def _require_case(tool_context: ToolContext):
    enc = S.get(tool_context.state)
    case = get_case(enc.get("case_id") or "")
    return enc, case


def _check_evolution(enc: dict, case, tool_context: ToolContext) -> list[str]:
    """Level-4 cases can change as the encounter proceeds."""
    fired = []
    for step in case.evolution:
        sid = step.get("id")
        if sid in enc["evolution_fired"]:
            continue
        after = int(step.get("after_turn", 0))
        trigger = step.get("after_action", "")
        done_ids = {
            i
            for entry in enc["exams_requested"] + enc["investigations_ordered"]
            for i in (entry.get("matched_all") or ([entry["matched"]] if entry.get("matched") else []))
        }
        if (after and enc["turn"] >= after) or (trigger and trigger in done_ids):
            enc["evolution_fired"].append(sid)
            fired.append(step.get("update", ""))
    return [f for f in fired if f]


def perform_examination(request: str, tool_context: ToolContext) -> dict[str, Any]:
    """Performs a physical examination the student has asked for.

    Args:
        request: What the student wants to examine, in their own words, e.g.
            "check the vitals", "auscultate the chest", "JVP".

    Returns:
        The finding, or a request to be more specific. Never invents findings.
    """
    enc, case = _require_case(tool_context)
    if case is None:
        return {"status": "no_active_case", "message": "Start a case first."}

    S.bump_turn(enc)
    S.advance(enc, "examination")
    findings, suggestions = match_all(request, case.examination)
    enc["exams_requested"].append(
        {
            "turn": enc["turn"],
            "query": request,
            "matched": findings[0].id if findings else None,
            "matched_all": [f.id for f in findings],
        }
    )
    updates = _check_evolution(enc, case, tool_context)
    S.put(tool_context.state, enc)

    if not findings:
        return {
            "status": "not_available",
            "message": (
                "That examination is not defined for this case. Ask the student "
                "to be more specific — do not describe a finding yourself."
            ),
            "did_you_mean": suggestions,
            "examinations_defined_for_this_case": [e.label for e in case.examination],
        }

    return {
        "status": "ok",
        "findings": [{"examination": f.label, "finding": f.result} for f in findings],
        "case_update": updates or None,
        "reminder": "Report the findings only. Do not interpret them for the student.",
    }


def order_investigation(request: str, tool_context: ToolContext) -> dict[str, Any]:
    """Orders an investigation and returns its result.

    Args:
        request: The test the student wants, e.g. "ECG", "chest X-ray",
            "troponin", "CBC".

    Returns:
        The result, or a note that the test is not part of this case.
    """
    enc, case = _require_case(tool_context)
    if case is None:
        return {"status": "no_active_case", "message": "Start a case first."}

    S.bump_turn(enc)
    S.advance(enc, "investigations")
    findings, suggestions = match_all(request, case.investigations)
    enc["investigations_ordered"].append(
        {
            "turn": enc["turn"],
            "query": request,
            "matched": findings[0].id if findings else None,
            "matched_all": [f.id for f in findings],
        }
    )
    updates = _check_evolution(enc, case, tool_context)
    S.put(tool_context.state, enc)

    if not findings:
        return {
            "status": "not_available",
            "message": (
                "That investigation has no result in this case. Tell the student "
                "it is unavailable here and ask what else they would order. "
                "Do not make up a result."
            ),
            "did_you_mean": suggestions,
            "note": "Ordering it still counts towards investigation selection.",
        }

    return {
        "status": "ok",
        "results": [
            {"investigation": f.label, "result": f.result, "tier": f.tier}
            for f in findings
        ],
        "case_update": updates or None,
        "reminder": (
            "Report the results verbatim. Do not tell the student what they mean "
            "or which diagnosis they support."
        ),
    }
