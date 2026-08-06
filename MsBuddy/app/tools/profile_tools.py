# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""The five profile tools named in `.agents-cli-spec.md` C1.

These are the only path by which anything reaches `user:profile`. Three
controls are enforced here, not in the prompt:

1. **Allowlist** — an unknown field name is rejected outright.
2. **Validation** — a value outside its declared range is rejected with a
   reason, so a percentage can never be stored as a 10-point CGPA.
3. **Evidence** — every stored student fact must quote the student's own
   words, and the quote is checked against the session's user-authored text.
   A field the student never mentioned therefore cannot be written, which is
   what makes C1's "zero unstated fields ever written" structural.

Tools return status dicts and never raise: a raised exception would reach the
model as an opaque error, while a status dict tells it precisely what to fix.
"""

from __future__ import annotations

from typing import Any

from google.adk.tools import ToolContext

from app.config import CLEAR_ALL_SENTINEL, STATE_PROFILE
from app.profile_store import (
    apply_field,
    clear_fields,
    collect_student_text,
    compute_completeness,
    derive_gpa,
    empty_profile,
    evidence_supports,
    export_profile,
    read_profile,
    write_profile,
)
from app.reference.gpa_scales import SCALE_KEYS, convert_to_us_4pt
from app.reference.profile_fields import FIELDS, validate_field
from app.schemas import ClaimTier, ExtractedField


def save_profile_fields(
    entries: list[ExtractedField], tool_context: ToolContext
) -> dict:
    """Record profile fields the student has explicitly stated.

    Every entry must quote the student's own words in `evidence_span`. The
    quote is verified against what the student actually wrote; entries whose
    quote cannot be found are rejected and NOT stored. Never supply a value
    the student did not state, and never paraphrase the evidence.

    Args:
        entries: The fields to record. Each needs `field_name` (a known
            profile field), `value` (as a string), and `evidence_span` (an
            exact quote of the student's words supporting that value).

    Returns:
        A dict with per-entry `saved` and `rejected` outcomes, any derived
        values, and the updated completeness summary.
    """
    if not entries:
        return {
            "status": "error",
            "message": "No entries supplied.",
            "known_fields": sorted(FIELDS),
        }

    profile = read_profile(tool_context.state, STATE_PROFILE)
    student_text = collect_student_text(
        getattr(tool_context, "session", None),
        getattr(tool_context, "user_content", None),
    )

    saved: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for raw in entries:
        entry = (
            raw
            if isinstance(raw, ExtractedField)
            else ExtractedField.model_validate(raw)
        )

        checked = validate_field(entry.field_name, entry.value)
        if not checked["ok"]:
            rejected.append(
                {
                    "field": entry.field_name,
                    "reason": "invalid_value",
                    "message": checked["message"],
                }
            )
            continue

        if not evidence_supports(entry.evidence_span, student_text):
            rejected.append(
                {
                    "field": entry.field_name,
                    "reason": "unverified_evidence",
                    "message": (
                        "The quoted evidence was not found in the student's own "
                        "messages, so this value was not stored. Quote the "
                        "student exactly, or ask them for the value directly."
                    ),
                }
            )
            continue

        saved.append(
            apply_field(
                profile,
                entry.field_name,
                checked["value"],
                ClaimTier.USER_STATED,
                entry.evidence_span,
                None,
            )
        )

    derivations: list[dict[str, Any]] = []
    if saved:
        derived = derive_gpa(profile)
        if derived is not None:
            derivations.append(derived)
        write_profile(tool_context.state, STATE_PROFILE, profile)

    if saved and rejected:
        status = "partial"
    elif saved:
        status = "success"
    else:
        status = "error"

    return {
        "status": status,
        "saved": saved,
        "rejected": rejected,
        "derived": derivations,
        "completeness": compute_completeness(profile),
    }


def get_profile(tool_context: ToolContext) -> dict:
    """Return everything currently recorded about the student.

    Each value carries where it came from: `USER_STATED` values quote the
    student, `INFERENCE` values name the rule that derived them. Read this
    before asking the student anything, so already-known facts are not
    requested twice.

    Returns:
        A dict containing the stored profile and its provenance.
    """
    profile = read_profile(tool_context.state, STATE_PROFILE)
    exported = export_profile(profile)
    return {
        "status": "success",
        "is_empty": exported["field_count"] == 0,
        "profile": exported,
    }


def profile_completeness(tool_context: ToolContext) -> dict:
    """Report which profile fields are missing and why each one matters.

    Use this to decide what to ask next. Ask only for fields that unblock
    what the student is currently trying to do — never read the whole missing
    list back to them as a questionnaire.

    Returns:
        A dict with per-importance counts, the missing fields with the reason
        each matters, and whether the core fields are complete.
    """
    profile = read_profile(tool_context.state, STATE_PROFILE)
    return {"status": "success", **compute_completeness(profile)}


def normalize_gpa(value: float, scale: str) -> dict:
    """Convert a GPA to its US 4.0 equivalent using a versioned rule.

    The scale must be stated explicitly — a bare number is ambiguous and a
    percentage read as a 10-point CGPA is a serious error. This is a linear
    approximation, not a credential evaluation, and the result is inference
    rather than fact.

    Args:
        value: The GPA figure exactly as the student stated it.
        scale: One of 'pct_100', 'cgpa_10', 'cgpa_5', 'cgpa_4', 'gpa_4_us'.

    Returns:
        A dict with the converted value, the rule id used, and any warning
        that the value looks implausible for the stated scale.
    """
    result = convert_to_us_4pt(value, scale)
    if result["status"] != "success":
        result["supported_scales"] = list(SCALE_KEYS)
    return result


def clear_profile_fields(field_names: list[str], tool_context: ToolContext) -> dict:
    """Delete recorded profile fields at the student's request.

    Pass the exact field names to remove. To erase the entire profile, pass
    the single value '__all__'. An empty list is rejected so that a malformed
    request can never wipe data by accident.

    Args:
        field_names: Field names to delete, or ['__all__'] to erase everything.

    Returns:
        A dict naming what was removed and what remains.
    """
    if not field_names:
        return {
            "status": "error",
            "message": (
                "No field names supplied. Name the fields to delete, or pass "
                "'__all__' to erase the whole profile."
            ),
        }

    if CLEAR_ALL_SENTINEL in field_names:
        previous = read_profile(tool_context.state, STATE_PROFILE)
        removed = sorted(previous.get("fields", {}))
        write_profile(tool_context.state, STATE_PROFILE, empty_profile())
        return {
            "status": "success",
            "cleared_all": True,
            "removed": removed,
            "remaining_field_count": 0,
        }

    profile = read_profile(tool_context.state, STATE_PROFILE)
    removed = clear_fields(profile, field_names)
    not_found = [n for n in field_names if n not in removed]
    write_profile(tool_context.state, STATE_PROFILE, profile)

    return {
        "status": "success" if removed else "error",
        "cleared_all": False,
        "removed": removed,
        "not_found": not_found,
        "remaining_field_count": len(profile.get("fields", {})),
        "completeness": compute_completeness(profile),
    }
