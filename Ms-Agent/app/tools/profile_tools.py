"""Profile tools — the only writers of the stored student profile.

The Profile Agent extracts and proposes; these tools validate, merge and
persist. A proposal that fails validation is refused with the reason, never
silently "fixed".
"""

from __future__ import annotations

from typing import Any

from google.adk.tools import ToolContext
from pydantic import ValidationError

from app.config.settings import STATE_PROFILE
from app.models.student import ProfileUpdate, StudentProfile
from app.services.profile_service import (
    apply_update,
    missing_important_fields,
)


def _read_profile(state: Any) -> StudentProfile:
    stored = state.get(STATE_PROFILE)
    if not isinstance(stored, dict):
        return StudentProfile()
    try:
        return StudentProfile.model_validate(stored)
    except ValidationError:
        # Corrupt state must not brick the conversation; start clean and
        # let the student re-state anything lost.
        return StudentProfile()


def get_profile(tool_context: ToolContext) -> dict:
    """Read the stored student profile.

    Call before asking the student anything, so nothing already known is
    asked again.

    Returns:
        The known fields by section, whether anything is stored yet, and
        the missing important fields in value order (ask only the first).
    """
    profile = _read_profile(tool_context.state)
    known = profile.known()
    return {
        "status": "success",
        "is_empty": not known,
        "profile": known,
        "missing_important_fields": missing_important_fields(profile),
    }


def update_profile(update: dict, tool_context: ToolContext) -> dict:
    """Merge a proposed profile update into the stored profile.

    Args:
        update: A ProfileUpdate shape — `{"profile": {<section>: {<field>:
            value}}, "ambiguities": [...]}` — exactly as the profile agent
            returned it. Only fields the student actually stated.

    Returns:
        The changed paths, the merged known profile, and what important
        information is still missing.
    """
    try:
        proposed = ProfileUpdate.model_validate(update)
    except ValidationError as exc:
        return {
            "status": "error",
            "reason": "invalid_update",
            "message": str(exc.errors()[0].get("msg", "invalid update"))[:200],
            "detail": [
                {"field": ".".join(str(p) for p in e["loc"]), "problem": e["msg"]}
                for e in exc.errors()[:5]
            ],
        }

    current = _read_profile(tool_context.state)
    merged, changed = apply_update(current, proposed)
    tool_context.state[STATE_PROFILE] = merged.model_dump()

    return {
        "status": "success",
        "changed": changed,
        "ambiguities": proposed.ambiguities,
        "profile": merged.known(),
        "missing_important_fields": missing_important_fields(merged),
    }


def get_missing_fields(tool_context: ToolContext) -> dict:
    """List important profile fields not yet known, most valuable first.

    Returns:
        Missing fields with why each matters. Ask the student for the first
        one only — never the whole list at once.
    """
    profile = _read_profile(tool_context.state)
    missing = missing_important_fields(profile)
    return {
        "status": "success",
        "missing_important_fields": missing,
        "ask_next": missing[0] if missing else None,
    }
