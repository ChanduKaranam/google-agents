"""Profile tools — the only writers of the stored student profile.

Extractors propose; these tools validate, merge and persist — now with
provenance. Every stored path records where its value came from
(`user_explicit` / `resume` / `user_confirmed`), and a resume's domain
*inferences* live in a separate unconfirmed channel until the student
confirms one. What the student said, what the resume said, and what was
inferred never blur (V2 brief §49).
"""

from __future__ import annotations

from typing import Any

from google.adk.tools import ToolContext
from pydantic import ValidationError

from app.config.settings import STATE_PROFILE, STATE_PROFILE_META
from app.models.student import ProfileUpdate, StudentProfile
from app.services.matching_service import gpa_on_4_scale
from app.services.profile_service import apply_update
from app.services.question_service import choose_next_question, readiness

VALID_SOURCES = ("user_explicit", "resume", "user_confirmed")


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


def _read_meta(state: Any) -> dict[str, Any]:
    stored = state.get(STATE_PROFILE_META)
    meta = dict(stored) if isinstance(stored, dict) else {}
    meta.setdefault("fields", {})
    meta.setdefault("inferred_domains", [])
    return meta


def get_profile(tool_context: ToolContext) -> dict:
    """Read the stored student profile with provenance.

    Call before asking the student anything, so nothing already known is
    asked again.

    Returns:
        Known fields by section, each path's source (user_explicit / resume
        / user_confirmed), any unconfirmed domain inferences awaiting the
        student's confirmation, and the profile readiness picture.
    """
    profile = _read_profile(tool_context.state)
    meta = _read_meta(tool_context.state)
    known = profile.known()
    return {
        "status": "success",
        "is_empty": not known,
        "profile": known,
        "provenance": meta["fields"],
        "unconfirmed_domain_inferences": meta["inferred_domains"],
        "readiness": readiness(profile),
    }


def update_profile(update: dict, source: str, tool_context: ToolContext) -> dict:
    """Merge a proposed profile update into the stored profile.

    Args:
        update: A ProfileUpdate shape — `{"profile": {<section>: {<field>:
            value}}, "ambiguities": [...], "inferred_domains": [...]}` —
            exactly as an extractor returned it. Only what was actually
            stated goes in `profile`; inferences stay in
            `inferred_domains`.
        source: Where these values came from — `user_explicit` for what the
            student typed, `resume` for resume extraction, `user_confirmed`
            when the student confirms a previous inference.

    Returns:
        The changed paths, the merged known profile, unconfirmed
        inferences, and the readiness picture.
    """
    if source not in VALID_SOURCES:
        return {
            "status": "error",
            "reason": "invalid_source",
            "message": f"source must be one of {VALID_SOURCES}, not '{source}'.",
        }
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

    meta = _read_meta(tool_context.state)
    for path in changed:
        meta["fields"][path] = {
            "source": source,
            "status": "confirmed" if source == "user_confirmed" else "extracted",
            "confidence": 1.0,
        }
    for inference in proposed.inferred_domains:
        entry = {
            **inference.model_dump(),
            "source": "resume_inference",
            "status": "needs_confirmation",
        }
        existing = [
            d for d in meta["inferred_domains"] if d["domain"] != inference.domain
        ]
        meta["inferred_domains"] = [*existing, entry]
    tool_context.state[STATE_PROFILE_META] = meta

    return {
        "status": "success",
        "changed": changed,
        "ambiguities": proposed.ambiguities,
        "profile": merged.known(),
        "unconfirmed_domain_inferences": meta["inferred_domains"],
        "readiness": readiness(merged),
        "note": (
            "Inferred domains are suggestions to confirm with the student, "
            "never facts. On confirmation, store the choice via "
            "update_profile with source='user_confirmed'."
        ),
    }


def get_interview_state(intent: str, tool_context: ToolContext) -> dict:
    """The one question worth asking next, given what the student wants.

    Args:
        intent: The current conversational goal, e.g. `FIND_AFFORDABLE`,
            `CHECK_ELIGIBILITY`, `FIND_RESEARCH_PROGRAMS`,
            `CAREER_ORIENTED_SEARCH`, `ESTIMATE_COST`, or empty for the
            generic interview. Intent reorders priorities; it never adds
            questions.

    Returns:
        `next_question` (field, why, suggested phrasing — rephrase
        naturally, never read it verbatim as a form), and the readiness
        tiers so you know when enough is enough.
    """
    profile = _read_profile(tool_context.state)
    return {
        "status": "success",
        "next_question": choose_next_question(profile, intent),
        "readiness": readiness(profile),
        "note": (
            "Ask ONE question, woven into the conversation. If readiness "
            "for the current task is already sufficient, skip asking and "
            "act instead."
        ),
    }


def convert_gpa(tool_context: ToolContext) -> dict:
    """Convert the stored CGPA to a US 4.0 equivalent, deterministically.

    Returns:
        The converted value with the linear-approximation caveat, or what
        is missing (CGPA or its scale). Never compute this yourself.
    """
    profile = _read_profile(tool_context.state)
    cgpa = profile.education.cgpa
    scale = profile.education.grading_scale
    if cgpa is None or not scale:
        return {
            "status": "error",
            "reason": "gpa_or_scale_missing",
            "message": "Need both the CGPA and its grading scale first.",
        }
    converted = gpa_on_4_scale(cgpa, scale)
    if converted is None:
        return {
            "status": "error",
            "reason": "inconsistent_scale",
            "message": f"CGPA {cgpa} is not valid on a /{scale} scale.",
        }
    return {
        "status": "success",
        "input": f"{cgpa}/{scale}",
        "us_4pt_equivalent": converted,
        "caveat": (
            "Linear approximation, not an official credential evaluation. "
            "Universities may compute it differently."
        ),
    }


def clear_profile(confirm: bool, tool_context: ToolContext) -> dict:
    """Erase the stored profile and its provenance completely.

    Args:
        confirm: Must be true. Ask the student for explicit confirmation
            before calling; never promise deletion without calling this.

    Returns:
        Confirmation that everything profile-related was removed.
    """
    if not confirm:
        return {
            "status": "error",
            "reason": "not_confirmed",
            "message": "Ask the student to confirm before erasing.",
        }
    tool_context.state[STATE_PROFILE] = StudentProfile().model_dump()
    tool_context.state[STATE_PROFILE_META] = {"fields": {}, "inferred_domains": []}
    return {
        "status": "success",
        "message": "The profile and its provenance were erased.",
    }
