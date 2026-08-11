"""Profile tools — the only writers of the stored student profile.

Extractors propose; these tools validate, merge and persist — with
provenance and an explicit precedence model (refactor §2): what the
student says NOW beats this session's resume, which beats anything
historical, and inference outranks nothing. Precedence is applied
silently — a superseded value becomes history, never a question. The
student is NEVER asked to reconcile stored data with what they just said.
What the student said, what the resume said, and what was inferred never
blur (V2 brief §49).
"""

from __future__ import annotations

from typing import Any

from google.adk.tools import ToolContext
from pydantic import ValidationError

from app.config.settings import (
    STATE_PROFILE,
    STATE_PROFILE_META,
    STATE_SESSION_FACTS,
)
from app.models.student import ProfileUpdate, StudentProfile
from app.services.matching_service import gpa_on_4_scale
from app.services.profile_enrichment import derive_skills
from app.services.profile_service import apply_update
from app.services.question_service import choose_next_question, readiness

VALID_SOURCES = ("user_explicit", "resume", "user_confirmed")


def _authority(source: str, in_session: bool) -> int:
    """Effective priority (§2, lower = stronger).

    1 — the student, this session (user_explicit / user_confirmed)
    3 — a resume analyzed this session
    4 — the student, a previous session
    5 — a historical resume
    """
    if source in ("user_explicit", "user_confirmed"):
        return 1 if in_session else 4
    return 3 if in_session else 5


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
    session_facts = tool_context.state.get(STATE_SESSION_FACTS)
    session_facts = session_facts if isinstance(session_facts, dict) else {}
    known = profile.known()
    return {
        "status": "success",
        "is_empty": not known,
        "profile": known,
        "provenance": meta["fields"],
        "stated_this_session": sorted(session_facts),
        "historical": sorted(set(meta["fields"]) - set(session_facts)),
        "unconfirmed_domain_inferences": meta["inferred_domains"],
        "derived_skills": meta.get("derived_skills", []),
        "readiness": readiness(profile),
        "note": (
            "Historical values are context, not current truth — anything "
            "the student states now supersedes them automatically."
        ),
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
    meta = _read_meta(tool_context.state)
    session_facts = tool_context.state.get(STATE_SESSION_FACTS)
    session_facts = dict(session_facts) if isinstance(session_facts, dict) else {}

    # Precedence merge (refactor §2-§4): where a differing value exists,
    # the stronger authority wins SILENTLY. Incoming values are always
    # "this session". A weaker incoming source (a resume against something
    # the student already said) is kept as history (`retained`); a
    # stronger one supersedes the stored value (`auto_resolved`). Equal
    # authority = a self-correction — newest wins (§9). None of these is
    # ever a question for the student.
    auto_resolved: list[dict[str, Any]] = []
    retained: list[dict[str, Any]] = []
    incoming_authority = _authority(source, in_session=True)
    for section_name in type(proposed.profile).model_fields:
        proposed_section = getattr(proposed.profile, section_name)
        current_section = getattr(current, section_name)
        for field_name in type(proposed_section).model_fields:
            incoming = getattr(proposed_section, field_name)
            if incoming is None or incoming == [] or incoming == {}:
                continue
            existing = getattr(current_section, field_name)
            if existing is None or existing == [] or existing == incoming:
                continue
            path = f"{section_name}.{field_name}"
            existing_source = (meta["fields"].get(path) or {}).get(
                "source", "user_explicit"
            )
            existing_authority = _authority(
                existing_source, in_session=path in session_facts
            )
            history = list((meta["fields"].get(path) or {}).get("history", []))
            if incoming_authority <= existing_authority:
                history.append({"value": existing, "source": existing_source})
                meta["fields"].setdefault(path, {})["history"] = history
                auto_resolved.append(
                    {
                        "field": path,
                        "effective_value": incoming,
                        "effective_source": source,
                        "superseded_value": existing,
                        "superseded_source": existing_source,
                        "rule": "current statement outranks the stored value",
                    }
                )
            else:
                history.append({"value": incoming, "source": source})
                meta["fields"].setdefault(path, {})["history"] = history
                retained.append(
                    {
                        "field": path,
                        "kept_value": existing,
                        "kept_source": existing_source,
                        "incoming_value": incoming,
                        "incoming_source": source,
                        "rule": (
                            "the student's stated value outranks this "
                            "source; the incoming value went to history"
                        ),
                    }
                )
                # Strip so the merge cannot apply the weaker value.
                setattr(proposed_section, field_name, None)

    merged, changed = apply_update(current, proposed)
    tool_context.state[STATE_PROFILE] = merged.model_dump()

    for path in changed:
        history = (meta["fields"].get(path) or {}).get("history", [])
        meta["fields"][path] = {
            "source": source,
            "status": "confirmed" if source == "user_confirmed" else "extracted",
            "confidence": 1.0,
            **({"history": history} if history else {}),
        }
        session_facts[path] = {"source": source}
    tool_context.state[STATE_SESSION_FACTS] = session_facts

    # Deterministic enrichment (§8-9): skills derived from stated skills and
    # project descriptions, each with its textual basis. Metadata only —
    # never merged into the stated profile.
    enrichment_text = " ".join([*merged.technical.skills, *merged.projects.projects])
    meta["derived_skills"] = derive_skills(enrichment_text)
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
        "auto_resolved": auto_resolved,
        "retained": retained,
        "ambiguities": proposed.ambiguities,
        "profile": merged.known(),
        "unconfirmed_domain_inferences": meta["inferred_domains"],
        "derived_skills": meta["derived_skills"],
        "readiness": readiness(merged),
        "note": (
            "Precedence already applied — never ask the student to "
            "reconcile these. `auto_resolved` values superseded history "
            "silently; `retained` values kept the student's own statement. "
            "Acknowledge naturally and continue the task. Only "
            "`ambiguities` (a genuinely unclear statement) may prompt one "
            "concrete question. Inferred domains stay suggestions until "
            "confirmed via source='user_confirmed'."
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
    tool_context.state[STATE_SESSION_FACTS] = {}
    return {
        "status": "success",
        "message": "The profile and its provenance were erased.",
    }
