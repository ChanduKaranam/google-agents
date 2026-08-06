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

"""Deterministic shortlist state operations (spec C2, §6.1 `user:shortlist`).

Mirrors `profile_store`: pure Python over plain dicts, read-copy-write against
ADK state, no LLM and no network. Retrieved content reaches this module only
after it has already been verified against harvested grounding, which is what
keeps spec §5.2 invariant 2 ("retrieved content never lands directly in
`user:` state") true by construction.
"""

from __future__ import annotations

import copy
import re
from typing import Any

from app.config import PROFILE_SCHEMA_VERSION
from app.evidence import evaluate_staleness, now_utc
from app.reference.program_fields import ALL_FIELD_NAMES

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def now_iso() -> str:
    """Current UTC time as an ISO-8601 string."""
    return now_utc().isoformat(timespec="seconds")


def make_program_id(university: str, program: str) -> str:
    """Stable slug identifying a program within the shortlist."""
    joined = f"{university}-{program}".lower()
    return _SLUG_STRIP.sub("-", joined).strip("-")[:80]


def empty_shortlist() -> dict[str, Any]:
    """A fresh, empty shortlist record."""
    stamp = now_iso()
    return {
        "schema_version": PROFILE_SCHEMA_VERSION,
        "created_at": stamp,
        "updated_at": stamp,
        "programs": {},
    }


def read_shortlist(state: Any, key: str) -> dict[str, Any]:
    """Return a mutable deep copy of the stored shortlist."""
    stored = state.get(key)
    if not isinstance(stored, dict) or "programs" not in stored:
        return empty_shortlist()
    return copy.deepcopy(stored)


def write_shortlist(state: Any, key: str, shortlist: dict[str, Any]) -> None:
    """Persist `shortlist`, stamping `updated_at`."""
    shortlist["updated_at"] = now_iso()
    state[key] = shortlist


def upsert_program(
    shortlist: dict[str, Any],
    program_id: str,
    university: str,
    program: str,
) -> dict[str, Any]:
    """Get or create the ProgramRecord for `program_id`."""
    programs = shortlist.setdefault("programs", {})
    record = programs.get(program_id)
    if record is None:
        record = {
            "program_id": program_id,
            "university": university,
            "program": program,
            "first_seen_at": now_iso(),
            "fields": {},
        }
        programs[program_id] = record
    return record


# Preference order when several sources speak to the same field. Official
# outranks third-party, but third-party is never discarded — spec §7.1 keeps
# REPORTED as a real tier, not a synonym for "ignored".
_TIER_RANK = {"VERIFIED": 2, "REPORTED": 1}


def _rank(entry: dict[str, Any]) -> tuple[int, str]:
    """Sort key: tier first, then recency."""
    return (
        _TIER_RANK.get(str(entry.get("tier")), 0),
        str(entry.get("evidence", {}).get("retrieved_at") or ""),
    )


def apply_claim(
    record: dict[str, Any],
    field_name: str,
    value: str,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    """Store one verified claim on a ProgramRecord.

    Every source that speaks to a field is retained in `sources`; nothing is
    overwritten. The displayed value is chosen by rank — official before
    third-party, newer before older — rather than by arrival order.

    This matters in both directions. A conflicting value is surfaced rather
    than averaged away (spec §7.4.4). And a *corroborating* value from a
    weaker source can no longer displace the official one: previously an
    aggregator restating a university's own tuition figure silently
    downgraded the field from VERIFIED to REPORTED and replaced the
    citation with the aggregator's.
    """
    fields = record.setdefault("fields", {})
    existing = fields.get(field_name)

    sources: list[dict[str, Any]] = []
    if isinstance(existing, dict):
        sources = list(existing.get("sources") or [])

    domain = evidence.get("source_domain")
    # Re-stating the same value from the same source refreshes it rather
    # than accumulating duplicates.
    sources = [
        s
        for s in sources
        if not (
            s.get("value") == value
            and s.get("evidence", {}).get("source_domain") == domain
        )
    ]
    sources.append({"value": value, "tier": evidence["tier"], "evidence": evidence})

    preferred = max(sources, key=_rank)
    conflicts = [s for s in sources if s["value"] != preferred["value"]]
    corroborations = [
        s for s in sources if s["value"] == preferred["value"] and s is not preferred
    ]

    fields[field_name] = {
        "value": preferred["value"],
        "tier": preferred["tier"],
        "evidence": preferred["evidence"],
        "sources": sources,
        "conflicts": conflicts,
        "corroborations": corroborations,
    }

    return {
        "field": field_name,
        "value": preferred["value"],
        "tier": preferred["tier"],
        "accepted_value": value,
        "preferred_source": preferred["evidence"].get("source_domain"),
        "source_count": len(sources),
        "corroborated_by": [s["evidence"].get("source_domain") for s in corroborations],
        "conflict_with": [s["value"] for s in conflicts],
    }


def unknown_fields(record: dict[str, Any]) -> list[str]:
    """Fields with no stored value.

    C2 requires these to be *named* as unknown rather than omitted, so that a
    gap in coverage can never read as an absence of a requirement.
    """
    stored = set(record.get("fields", {}))
    return [name for name in ALL_FIELD_NAMES if name not in stored]


def render_program(record: dict[str, Any]) -> dict[str, Any]:
    """Present one ProgramRecord with tiers, citations and staleness notices."""
    fields: dict[str, Any] = {}
    stale_fields: list[str] = []

    for name, entry in record.get("fields", {}).items():
        evidence = entry.get("evidence", {})
        staleness = evaluate_staleness(evidence)
        if staleness["is_stale"]:
            stale_fields.append(name)
        fields[name] = {
            "value": entry.get("value"),
            "tier": entry.get("tier"),
            "source_domain": evidence.get("source_domain"),
            "source_is_official": evidence.get("source_is_official"),
            "source_url": evidence.get("source_url"),
            "url_is_grounding_redirect": evidence.get("url_is_grounding_redirect"),
            "retrieved_at": evidence.get("retrieved_at"),
            "staleness_class": evidence.get("staleness_class"),
            "is_stale": staleness["is_stale"],
            "staleness_notice": staleness["notice"],
            "supporting_quote": evidence.get("supporting_quote"),
            "conflicts": entry.get("conflicts", []),
            # Retained so a later comparison layer can weigh a fact stated by
            # several independent sources above one stated by a single site.
            "corroborations": entry.get("corroborations", []),
            "source_count": len(entry.get("sources") or []),
            "all_source_domains": sorted(
                {
                    str(s.get("evidence", {}).get("source_domain"))
                    for s in (entry.get("sources") or [])
                }
            ),
        }

    return {
        "program_id": record.get("program_id"),
        "university": record.get("university"),
        "program": record.get("program"),
        "fields": fields,
        "unknown_fields": unknown_fields(record),
        "stale_fields": stale_fields,
        "verified_count": sum(1 for f in fields.values() if f["tier"] == "VERIFIED"),
        "reported_count": sum(1 for f in fields.values() if f["tier"] == "REPORTED"),
    }


def render_shortlist(shortlist: dict[str, Any]) -> dict[str, Any]:
    """Present the whole shortlist."""
    programs = shortlist.get("programs", {})
    return {
        "program_count": len(programs),
        "programs": [render_program(r) for r in programs.values()],
    }
