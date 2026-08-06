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

"""Deterministic profile state operations.

Everything in this module is pure Python over plain dicts. No LLM, no network,
no ADK types — which is what makes it unit-testable, and is the concrete form
of spec principle P3 ("arithmetic belongs in Python, not in the model").

The ADK boundary lives in `app/tools/profile_tools.py`; this module is the
logic it delegates to.
"""

from __future__ import annotations

import copy
import datetime as dt
import re
from typing import Any

from app.config import MAX_VALUE_HISTORY, PROFILE_SCHEMA_VERSION
from app.reference.gpa_scales import convert_to_us_4pt
from app.reference.profile_fields import CORE_FIELDS, DERIVED_FIELDS, FIELDS
from app.schemas import ClaimTier

_WHITESPACE = re.compile(r"\s+")
# Punctuation stripped before evidence matching. Deliberately narrow: it
# absorbs formatting differences ("GRE: 320" vs "GRE 320") without letting
# through a span that shares no actual tokens with the student's text.
_PUNCTUATION_CHARS = ".,:;!?()[]\"'`\u2018\u2019\u201c\u201d"
_PUNCTUATION = re.compile(f"[{re.escape(_PUNCTUATION_CHARS)}]")


def now_iso() -> str:
    """Current UTC time as an ISO-8601 string."""
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds")


def empty_profile() -> dict[str, Any]:
    """A fresh, empty profile record."""
    stamp = now_iso()
    return {
        "schema_version": PROFILE_SCHEMA_VERSION,
        "created_at": stamp,
        "updated_at": stamp,
        "fields": {},
    }


def read_profile(state: Any, key: str) -> dict[str, Any]:
    """Return a mutable deep copy of the stored profile.

    A copy, not the live object: ADK registers a state delta on assignment to
    a key, so in-place mutation of a nested dict can be missed. Callers mutate
    the copy and hand it back to `write_profile`.
    """
    stored = state.get(key)
    if not isinstance(stored, dict) or "fields" not in stored:
        return empty_profile()
    return copy.deepcopy(stored)


def write_profile(state: Any, key: str, profile: dict[str, Any]) -> None:
    """Persist `profile`, stamping `updated_at`."""
    profile["updated_at"] = now_iso()
    state[key] = profile


# --- Evidence verification --------------------------------------------------


def normalize_for_match(text: str) -> str:
    """Lower-case, strip light punctuation, and collapse whitespace."""
    without_punctuation = _PUNCTUATION.sub(" ", text.lower())
    return _WHITESPACE.sub(" ", without_punctuation).strip()


def collect_student_text(session: Any, user_content: Any) -> str:
    """Concatenate every piece of text the student themselves authored.

    This is the haystack that `evidence_span` values are checked against. Only
    user-authored turns are included: model output is never allowed to become
    its own evidence, which would defeat the control entirely.
    """
    chunks: list[str] = []

    for event in getattr(session, "events", None) or []:
        content = getattr(event, "content", None)
        if content is None:
            continue
        if getattr(content, "role", None) != "user":
            continue
        for part in getattr(content, "parts", None) or []:
            text = getattr(part, "text", None)
            if text:
                chunks.append(text)

    if user_content is not None and getattr(user_content, "role", None) == "user":
        for part in getattr(user_content, "parts", None) or []:
            text = getattr(part, "text", None)
            if text:
                chunks.append(text)

    return "\n".join(chunks)


def evidence_supports(evidence_span: str, student_text: str) -> bool:
    """True if `evidence_span` really appears in the student's own words."""
    span = normalize_for_match(evidence_span)
    if not span:
        return False
    return span in normalize_for_match(student_text)


# --- Field application ------------------------------------------------------


def apply_field(
    profile: dict[str, Any],
    field_name: str,
    value: Any,
    tier: ClaimTier,
    evidence_span: str | None,
    rule_id: str | None,
) -> dict[str, Any]:
    """Write one already-validated value into `profile`.

    Returns a per-field outcome describing whether an existing value was
    replaced, so the caller can tell the student rather than overwriting in
    silence (a named C1 failure case).
    """
    fields = profile.setdefault("fields", {})
    existing = fields.get(field_name)

    history: list[str] = []
    replaced_value: Any = None
    if isinstance(existing, dict):
        history = list(existing.get("superseded") or [])
        if existing.get("value") != value:
            replaced_value = existing.get("value")
            history.append(str(existing.get("value")))
            history = history[-MAX_VALUE_HISTORY:]

    fields[field_name] = {
        "value": value,
        "tier": tier.value,
        "recorded_at": now_iso(),
        "evidence_span": evidence_span,
        "rule_id": rule_id,
        "superseded": history,
    }

    return {
        "field": field_name,
        "value": value,
        "tier": tier.value,
        "replaced_previous_value": replaced_value,
    }


def derive_gpa(profile: dict[str, Any]) -> dict[str, Any] | None:
    """Recompute `gpa_us_4pt` from `gpa_value` + `gpa_scale`, if both exist.

    Returns the derivation outcome, or None when the dependencies are absent.
    """
    fields = profile.get("fields", {})
    value_entry = fields.get("gpa_value")
    scale_entry = fields.get("gpa_scale")
    if not isinstance(value_entry, dict) or not isinstance(scale_entry, dict):
        return None

    conversion = convert_to_us_4pt(
        float(value_entry["value"]), str(scale_entry["value"])
    )
    if conversion["status"] != "success":
        fields.pop("gpa_us_4pt", None)
        return conversion

    apply_field(
        profile,
        "gpa_us_4pt",
        conversion["us_4pt_equivalent"],
        ClaimTier.INFERENCE,
        None,
        conversion["rule_id"],
    )
    return conversion


def unmet_dependencies(profile: dict[str, Any]) -> dict[str, list[str]]:
    """Fields that are present but missing a companion field they require."""
    fields = profile.get("fields", {})
    unmet: dict[str, list[str]] = {}
    for name, spec in FIELDS.items():
        if name not in fields:
            continue
        missing = [dep for dep in spec.requires if dep not in fields]
        if missing:
            unmet[name] = missing
    return unmet


def clear_fields(profile: dict[str, Any], field_names: list[str]) -> list[str]:
    """Remove the named fields (and any derivation that depended on them)."""
    fields = profile.get("fields", {})
    removed: list[str] = []
    for name in field_names:
        if name in fields:
            del fields[name]
            removed.append(name)
    # A derived value must never outlive its inputs.
    if ("gpa_value" in removed or "gpa_scale" in removed) and ("gpa_us_4pt" in fields):
        del fields["gpa_us_4pt"]
        removed.append("gpa_us_4pt")
    return removed


# --- Completeness -----------------------------------------------------------


def compute_completeness(profile: dict[str, Any]) -> dict[str, Any]:
    """Report which fields are present, which are missing, and why they matter.

    C1 requires the report to name the missing fields *and* the reason each
    one matters, so `why_it_matters` is carried through verbatim from the
    registry rather than summarised.
    """
    present = set(profile.get("fields", {})) - set(DERIVED_FIELDS)

    by_importance: dict[str, dict[str, Any]] = {}
    missing: list[dict[str, str]] = []

    for importance in ("core", "recommended", "optional"):
        names = [n for n, s in FIELDS.items() if s.importance == importance]
        have = [n for n in names if n in present]
        lack = [n for n in names if n not in present]
        by_importance[importance] = {
            "present": len(have),
            "total": len(names),
            "missing": lack,
        }
        for name in lack:
            missing.append(
                {
                    "field": name,
                    "importance": importance,
                    "why_it_matters": FIELDS[name].why_it_matters,
                }
            )

    total = len(FIELDS)
    core_missing = by_importance["core"]["missing"]

    return {
        "core_complete": not core_missing,
        "core_missing": core_missing,
        "overall_present": len(present),
        "overall_total": total,
        "overall_percent": round(len(present) / total * 100, 1) if total else 0.0,
        "by_importance": by_importance,
        "missing_fields": missing,
        "unmet_dependencies": unmet_dependencies(profile),
        "ready_for_program_research": not core_missing,
        "core_field_names": list(CORE_FIELDS),
    }


def export_profile(profile: dict[str, Any]) -> dict[str, Any]:
    """Flatten the profile for display, preserving provenance on every value."""
    fields = profile.get("fields", {})
    return {
        "schema_version": profile.get("schema_version", PROFILE_SCHEMA_VERSION),
        "created_at": profile.get("created_at"),
        "updated_at": profile.get("updated_at"),
        "field_count": len(fields),
        "fields": {
            name: {
                "value": entry.get("value"),
                "tier": entry.get("tier"),
                "recorded_at": entry.get("recorded_at"),
                "evidence_span": entry.get("evidence_span"),
                "rule_id": entry.get("rule_id"),
                "previous_values": entry.get("superseded") or [],
            }
            for name, entry in fields.items()
        },
    }
