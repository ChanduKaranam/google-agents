"""Case selection and encounter start."""

from __future__ import annotations

from typing import Any

from google.adk.tools import ToolContext

from .. import session as S
from ..cases import get_case, list_cases


def list_available_cases(difficulty: int) -> dict[str, Any]:
    """Lists the cases a student can start. Never reveals any diagnosis.

    Args:
        difficulty: 1 (beginner) to 4 (expert). Pass 0 for all levels.

    Returns:
        The case catalogue with id, title, presenting complaint and level.
    """
    level = difficulty if difficulty in (1, 2, 3, 4) else None
    cases = list_cases(level)
    return {
        "status": "ok",
        "count": len(cases),
        "levels": {
            1: "Beginner — strong clues, simple presentation",
            2: "Intermediate — several diagnoses, needs targeted history",
            3: "Advanced — conflicting information, careful reasoning",
            4: "Expert — incomplete and evolving information",
        },
        "cases": cases,
    }


def start_case(case_id: str, tool_context: ToolContext) -> dict[str, Any]:
    """Starts a clinical encounter and returns the opening brief.

    Resets any encounter already in progress.

    Args:
        case_id: The case identifier, e.g. "IM-001". Pass an empty string to
            start the easiest available case.

    Returns:
        The case brief to read to the student, plus how to interact.
    """
    if not case_id.strip():
        catalogue = list_cases()
        if not catalogue:
            return {"status": "error", "message": "The case bank is empty."}
        case_id = catalogue[0]["case_id"]

    case = get_case(case_id)
    if case is None:
        return {
            "status": "error",
            "message": f"No case '{case_id}'. Use list_available_cases first.",
            "available": [c["case_id"] for c in list_cases()],
        }

    enc = S.blank()
    enc["case_id"] = case.case_id
    enc["phase"] = "history"
    S.put(tool_context.state, enc)

    return {
        "status": "ok",
        "case_id": case.case_id,
        "read_this_to_the_student_verbatim": (
            f"**Case {case.case_id} — {case.specialty}, {case.setting}**\n\n"
            f"{case.opening_brief}\n\n"
            f"You may ask the patient questions at any time. When you want to "
            f"examine the patient or order a test, just say so.\n\n"
            f"Begin when ready."
        ),
        "difficulty": case.difficulty,
        "reminder": (
            "Practice Mode is on. Do not reveal or hint at the diagnosis. "
            "Route every patient-directed question through ask_patient."
        ),
    }


def case_status(tool_context: ToolContext) -> dict[str, Any]:
    """Reports how far the student has got in the current encounter.

    Returns:
        Counts of questions asked, examinations and investigations done, and
        which steps of the workflow are still outstanding.
    """
    enc = S.get(tool_context.state)
    if not enc.get("case_id"):
        return {"status": "no_active_case"}

    outstanding = []
    if not enc["differential_submitted"]:
        outstanding.append("submit_differential")
    if not enc["distinguishing_plan"]:
        outstanding.append("submit_discriminating_plan")
    if not enc["final_diagnosis"]:
        outstanding.append("submit_final_diagnosis")
    if not enc["scorecard"]:
        outstanding.append("evaluate_encounter")

    return {
        "status": "ok",
        "case_id": enc["case_id"],
        "phase": enc["phase"],
        "questions_asked": len(enc["questions_asked"]),
        "examinations_done": len(enc["exams_requested"]),
        "investigations_ordered": len(enc["investigations_ordered"]),
        "differential_size": len(enc["differential_submitted"]),
        "hints_used": enc["hints_used"],
        "outstanding_steps": outstanding,
    }
