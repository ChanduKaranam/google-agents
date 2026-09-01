"""Encounter state kept in ADK session state.

ADK persists `tool_context.state` across turns, so this module is only a set of
helpers for reading/writing a well-known shape.  Keys are prefixed `enc.` so
they are easy to spot in the ADK dev-UI state inspector.
"""

from __future__ import annotations

from typing import Any

KEY = "enc"

PHASES = [
    "not_started",
    "history",
    "examination",
    "investigations",
    "differential",
    "final",
    "evaluated",
]


def blank() -> dict[str, Any]:
    return {
        "case_id": None,
        "phase": "not_started",
        "turn": 0,
        "questions_asked": [],       # [{"turn": n, "text": ...}]
        "patient_replies": [],       # [{"turn": n, "text": ...}]
        "exams_requested": [],       # [{"turn": n, "query":..., "matched": id|None}]
        "investigations_ordered": [],
        "differential_submitted": [],  # [{"dx":..., "rationale":...}]
        "distinguishing_plan": "",
        "final_diagnosis": "",
        "final_reasoning": "",
        "hints_used": 0,
        "revealed": False,
        "metacognition": [],         # [{"question":..., "student_reason":...}]
        "evolution_fired": [],
        "scorecard": None,
    }


def get(state) -> dict[str, Any]:
    enc = state.get(KEY)
    if not enc:
        enc = blank()
        state[KEY] = enc
    return enc


def put(state, enc: dict[str, Any]) -> None:
    # Re-assign so ADK records a state delta for the event.
    state[KEY] = enc


def bump_turn(enc: dict[str, Any]) -> int:
    enc["turn"] = int(enc.get("turn", 0)) + 1
    return enc["turn"]


def advance(enc: dict[str, Any], phase: str) -> None:
    """Move forward only; a student may examine after ordering bloods."""
    if PHASES.index(phase) > PHASES.index(enc.get("phase", "not_started")):
        enc["phase"] = phase


def active_case_id(state) -> str | None:
    return get(state).get("case_id")
