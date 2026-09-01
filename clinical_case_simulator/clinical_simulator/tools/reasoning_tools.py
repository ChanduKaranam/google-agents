"""Tools for the clinical-reasoning phase (research doc, sections 6 and 15)."""

from __future__ import annotations

from typing import Any

from google.adk.tools import ToolContext

from .. import session as S


def submit_differential(
    diagnoses: list[str], rationales: list[str], tool_context: ToolContext
) -> dict[str, Any]:
    """Records the student's differential diagnosis. Does not grade it yet.

    Args:
        diagnoses: The student's candidate diagnoses, most likely first.
        rationales: One reason per diagnosis, in the same order. Pass an empty
            string for any diagnosis the student gave without a reason — do not
            invent reasoning on their behalf.

    Returns:
        Confirmation and the next step. No feedback on correctness.
    """
    enc = S.get(tool_context.state)
    if not enc.get("case_id"):
        return {"status": "no_active_case"}

    items = []
    for i, dx in enumerate(diagnoses):
        items.append(
            {"dx": dx, "rationale": rationales[i] if i < len(rationales) else ""}
        )
    enc["differential_submitted"] = items
    S.advance(enc, "differential")
    S.put(tool_context.state, enc)

    missing_reasons = [i["dx"] for i in items if not i["rationale"].strip()]
    return {
        "status": "recorded",
        "count": len(items),
        "recorded": [i["dx"] for i in items],
        "coaching": (
            "This is now banked and will be marked as given. Do NOT say whether "
            "these are right. Ask what single piece of information would most "
            "change the ranking, then record their discriminating plan."
        ),
        "diagnoses_given_without_a_reason": missing_reasons,
        "note": (
            "Fewer than three diagnoses scores lower. Ask for more — but if they "
            "decline or move on, that is their choice to make and you record it."
            if len(items) < 3
            else ""
        ),
    }


def submit_discriminating_plan(plan: str, tool_context: ToolContext) -> dict[str, Any]:
    """Records how the student would tell their differentials apart.

    Args:
        plan: The student's own words on what further history, examination or
            investigation would discriminate between their diagnoses, and what
            result would favour which.

    Returns:
        Confirmation.
    """
    enc = S.get(tool_context.state)
    if not enc.get("case_id"):
        return {"status": "no_active_case"}
    enc["distinguishing_plan"] = plan
    S.put(tool_context.state, enc)
    return {
        "status": "recorded",
        "coaching": (
            "Let them act on the plan if they want more tests, then ask for a "
            "final diagnosis. Still no confirmation of correctness."
        ),
    }


def submit_final_diagnosis(
    diagnosis: str, reasoning: str, tool_context: ToolContext
) -> dict[str, Any]:
    """Records the student's final diagnosis and closes the reasoning phase.

    Args:
        diagnosis: The single diagnosis the student commits to.
        reasoning: Their justification, in their own words — which findings
            support it and which alternatives they excluded and why.

    Returns:
        Confirmation. Correctness is not disclosed here; it comes out in the
        evaluation report.
    """
    enc = S.get(tool_context.state)
    if not enc.get("case_id"):
        return {"status": "no_active_case"}
    enc["final_diagnosis"] = diagnosis
    enc["final_reasoning"] = reasoning
    S.advance(enc, "final")
    S.put(tool_context.state, enc)

    thin = len(reasoning.split()) < 25
    skipped_differential = not enc.get("differential_submitted")
    return {
        "status": "recorded",
        "coaching": (
            "Recorded. Invite them to expand — which findings support it, and "
            "what they ruled out — because their reasoning is scored. If they "
            "decline, evaluate anyway. Never withhold the report."
            if thin
            else "Recorded. Produce the performance report when they are ready."
        ),
        "reasoning_looks_thin": thin,
        "note": (
            "They committed to an answer without giving a differential first. "
            "Mention the skipped step once, then move on — it is already "
            "reflected in their score."
            if skipped_differential
            else ""
        ),
    }


def record_metacognition(
    question: str, student_reason: str, tool_context: ToolContext
) -> dict[str, Any]:
    """Records why the student asked a particular question.

    Use this after the case, when probing the student on one of their own
    questions ("You asked about smoking — why was that relevant?").

    Args:
        question: The student's original question.
        student_reason: Their explanation of why they asked it.

    Returns:
        Confirmation. The exchange is included in the evaluation transcript.
    """
    enc = S.get(tool_context.state)
    enc["metacognition"].append(
        {"question": question, "student_reason": student_reason}
    )
    S.put(tool_context.state, enc)
    return {"status": "recorded", "count": len(enc["metacognition"])}
