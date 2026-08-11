"""Application tools — researched requirements in, readiness and actions out.

Requirements arrive through the same admission gate as every other program
fact (`save_research` — the requirement slots are authoritative, so a
forum can never establish one). These tools interpret what is stored,
compare it with the profile and the tracked documents, and derive the next
action. Nothing here invents a requirement or a deadline (§5-§10).
"""

from __future__ import annotations

from datetime import date
from typing import Any

from google.adk.tools import ToolContext

from app.application.analysis import (
    APPLICATION_REQUIREMENT_FIELDS,
    application_readiness,
    deadline_urgency,
    extract_lor_details,
    interpret_document_requirement,
)
from app.application.tracker import (
    next_action,
    set_document,
    upsert_application,
)
from app.config.settings import STATE_APPLICATIONS, STATE_KNOWLEDGE
from app.exams.requirements import interpret_requirement
from app.finance.analysis import assess_money_freshness, extract_money
from app.models.program import Program
from app.tools.profile_tools import _read_profile
from app.university.analysis import assess_deadline_freshness


def _stored_programs(state: Any) -> dict[str, Program]:
    knowledge = state.get(STATE_KNOWLEDGE)
    knowledge = knowledge if isinstance(knowledge, dict) else {}
    return {key: Program.model_validate(raw) for key, raw in knowledge.items()}


def check_application_requirements(tool_context: ToolContext) -> dict:
    """Interpret the researched application requirements per program.

    Reads stored, evidence-graded requirement facts only. Each row carries
    the published sentence, its deterministic interpretation (required /
    optional / not_required / conditional / waived / unknown), LOR details
    when stated, and the source with retrieval date. Requirements nothing
    researched are listed as unknown — present them as unknown, never
    assume either way, and never carry a requirement from one program to
    another.

    Returns:
        Per-program requirement rows plus unknown_requirements, or an
        honest error naming the fields to research first.
    """
    profile = _read_profile(tool_context.state)
    intake = profile.target.intake or ""
    programs = [
        program
        for program in _stored_programs(tool_context.state).values()
        if any(f in program.facts for f in APPLICATION_REQUIREMENT_FIELDS)
    ]
    if not programs:
        return {
            "status": "error",
            "reason": "no_application_evidence",
            "message": (
                "No application requirements are stored yet. Research the "
                "program's admission pages for: "
                + ", ".join(APPLICATION_REQUIREMENT_FIELDS)
                + ", then save the claims."
            ),
        }

    out = []
    for program in programs:
        rows: list[dict[str, Any]] = []
        for field in APPLICATION_REQUIREMENT_FIELDS:
            fact = program.facts.get(field)
            if fact is None:
                continue
            row: dict[str, Any] = {
                "field": field,
                "value": fact.value,
                "verification_status": fact.status,
                "source_domain": fact.evidence.source_domain,
                "source_type": fact.evidence.source_type,
                "url": fact.evidence.url,
                "retrieved_at": fact.evidence.retrieved_at,
            }
            if field == "application_deadline":
                row["freshness"] = assess_deadline_freshness(fact.value, intake)
                row["urgency"] = deadline_urgency(fact.value, date.today())
            elif field == "application_fee":
                row["money"] = extract_money(fact.value)
                row["freshness"] = assess_money_freshness(fact.value, intake)
            elif field in ("english_requirement", "gre_requirement"):
                row["interpretation"] = interpret_requirement(fact.value)
            elif field != "application_portal":
                row["interpretation"] = interpret_document_requirement(fact.value)
            if field == "lor_requirement":
                row["lor_details"] = extract_lor_details(fact.value)
            if fact.conflicts:
                row["conflicts"] = fact.conflicts
            rows.append(row)
        out.append(
            {
                "university": program.university,
                "program": program.name,
                "requirements": rows,
                "unknown_requirements": sorted(
                    f
                    for f in APPLICATION_REQUIREMENT_FIELDS
                    if f not in program.facts
                ),
            }
        )
    return {
        "status": "success",
        "programs": out,
        "note": (
            "Unknown means not researched or not established — say exactly "
            "that. Requirements never transfer between programs."
        ),
    }


def track_application(
    university: str, program: str, status: str, tool_context: ToolContext
) -> dict:
    """Create or update a tracked application's status.

    Args:
        university: University name as researched.
        program: Program name as researched.
        status: One of researching, shortlisted, preparing, ready,
            submitted, under_review, decision_received, accepted,
            rejected, withdrawn.

    Returns:
        The tracked application, or a refusal for an unknown status.
    """
    store = tool_context.state.get(STATE_APPLICATIONS)
    store = dict(store) if isinstance(store, dict) else {}
    try:
        entry = upsert_application(store, university, program, status)
    except ValueError as error:
        return {"status": "error", "reason": "invalid_status", "message": str(error)}
    tool_context.state[STATE_APPLICATIONS] = store
    return {"status": "success", "application": entry}


def update_document_status(
    university: str,
    program: str,
    document: str,
    status: str,
    tool_context: ToolContext,
) -> dict:
    """Set one document's state on a tracked application.

    Args:
        university: University name as researched.
        program: Program name as researched.
        document: One of sop, lor, transcripts, resume, portfolio,
            english_test, gre_score, application_fee, other.
        status: One of missing, draft, ready, submitted, verified.

    Returns:
        The updated application, or a refusal for unknown values.
    """
    store = tool_context.state.get(STATE_APPLICATIONS)
    store = dict(store) if isinstance(store, dict) else {}
    try:
        entry = set_document(store, university, program, document, status)
    except ValueError as error:
        return {"status": "error", "reason": "invalid_value", "message": str(error)}
    tool_context.state[STATE_APPLICATIONS] = store
    return {"status": "success", "application": entry}


def get_application_dashboard(tool_context: ToolContext) -> dict:
    """Readiness, deadline urgency and the next action per tracked application.

    Joins the tracker with the researched requirements and the profile.
    Every verdict is derived: missing documents block readiness, a passed
    deadline demands verification, unknown requirements stay unknown.

    Returns:
        Per-application readiness rows, deadline urgency, next_action —
        plus the single overall next action. Never an admission judgment
        of any kind.
    """
    store = tool_context.state.get(STATE_APPLICATIONS)
    store = store if isinstance(store, dict) else {}
    if not store:
        return {
            "status": "error",
            "reason": "nothing_tracked",
            "message": (
                "No applications are tracked yet. Track one with "
                "track_application once the student picks a program."
            ),
        }
    profile = _read_profile(tool_context.state)
    programs = _stored_programs(tool_context.state)
    today = date.today()

    applications = []
    for key, raw in store.items():
        program = programs.get(key)
        documents = dict(raw.get("documents") or {})
        if program is not None:
            readiness = application_readiness(profile, program, documents)
            deadline_fact = program.facts.get("application_deadline")
            urgency = deadline_urgency(
                deadline_fact.value if deadline_fact else "", today
            )
        else:
            readiness = {
                "rows": [],
                "overall": "unknown",
                "unknown_requirements": list(APPLICATION_REQUIREMENT_FIELDS),
                "note": "This program's requirements are not researched yet.",
            }
            urgency = deadline_urgency("", today)
        applications.append(
            {
                "university": raw.get("university"),
                "program": raw.get("program"),
                "application_status": raw.get("status"),
                "documents": documents,
                "readiness": readiness,
                "deadline": urgency,
                "next_action": next_action(raw, readiness, urgency),
            }
        )

    def _sort_key(app: dict[str, Any]) -> tuple[int, int]:
        days = app["deadline"]["days_remaining"]
        return (0, days) if days is not None else (1, 0)

    applications.sort(key=_sort_key)
    return {
        "status": "success",
        "applications": applications,
        "overall_next_action": applications[0]["next_action"],
        "note": (
            "Readiness is document and requirement state only — it says "
            "nothing about outcomes. Unknown requirements need the program "
            "page, not an assumption."
        ),
    }
