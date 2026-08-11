"""The application tracker — deterministic state, closed vocabularies.

A plain dict store (persisted in session state by the tools), mutated only
through these functions: statuses and document types are closed sets, so a
hallucinated status is a `ValueError` at the boundary, never stored data.
`next_action` is a fixed priority ladder — a passed or unverified deadline
outranks documents; blocking documents outrank polish.
"""

from __future__ import annotations

from typing import Any

APPLICATION_STATUSES = (
    "researching",
    "shortlisted",
    "preparing",
    "ready",
    "submitted",
    "under_review",
    "decision_received",
    "accepted",
    "rejected",
    "withdrawn",
)

DOCUMENT_STATUSES = ("missing", "draft", "ready", "submitted", "verified")

DOCUMENT_TYPES = (
    "sop",
    "lor",
    "transcripts",
    "resume",
    "portfolio",
    "english_test",
    "gre_score",
    "application_fee",
    "other",
)

# Blocking documents first — the order actions are recommended in.
_DOCUMENT_PRIORITY = ("sop_requirement", "lor_requirement", "transcript_requirement",
                      "resume_requirement", "english_requirement", "gre_requirement",
                      "portfolio_requirement")


def _key(university: str, program: str) -> str:
    return f"{university.strip().lower()}::{program.strip().lower()}"


def upsert_application(
    store: dict[str, Any], university: str, program: str, status: str
) -> dict[str, Any]:
    """Create or update one tracked application; documents survive updates."""
    if status not in APPLICATION_STATUSES:
        raise ValueError(
            f"unknown application status '{status}'; allowed: "
            f"{APPLICATION_STATUSES}"
        )
    key = _key(university, program)
    entry = store.get(key) or {
        "university": university.strip(),
        "program": program.strip(),
        "documents": {},
    }
    entry["status"] = status
    store[key] = entry
    return entry


def set_document(
    store: dict[str, Any],
    university: str,
    program: str,
    document: str,
    status: str,
) -> dict[str, Any]:
    """Set one document's state on a tracked application."""
    if document not in DOCUMENT_TYPES:
        raise ValueError(
            f"unknown document '{document}'; allowed: {DOCUMENT_TYPES}"
        )
    if status not in DOCUMENT_STATUSES:
        raise ValueError(
            f"unknown document status '{status}'; allowed: {DOCUMENT_STATUSES}"
        )
    key = _key(university, program)
    entry = store.get(key)
    if entry is None:
        entry = {
            "university": university.strip(),
            "program": program.strip(),
            "status": "researching",
            "documents": {},
        }
        store[key] = entry
    entry["documents"][document] = status
    return entry


def next_action(
    application: dict[str, Any],
    readiness: dict[str, Any],
    urgency: dict[str, Any],
) -> str:
    """The one thing to do next for this application, by fixed priority."""
    if urgency.get("urgency") == "passed":
        return urgency["note"]
    missing = {
        r["requirement"]: r
        for r in readiness.get("rows", [])
        if r["verdict"] == "missing"
    }
    for field in _DOCUMENT_PRIORITY:
        if field in missing:
            return missing[field]["action"]
    in_progress = [
        r for r in readiness.get("rows", []) if r["verdict"] == "in_progress"
    ]
    if in_progress:
        return in_progress[0]["action"]
    if urgency.get("urgency") == "unknown":
        return (
            "Verify the application deadline on the program page — nothing "
            "verified is stored for this cycle."
        )
    if readiness.get("overall") == "ready" and application.get("status") not in (
        "submitted",
        "under_review",
        "decision_received",
        "accepted",
        "rejected",
        "withdrawn",
    ):
        return (
            "Every researched requirement is covered — submit before the "
            f"deadline ({urgency.get('note', 'timing unverified')})."
        )
    return (
        "Verify the requirements still marked unknown on the program page, "
        "then re-check readiness."
    )
