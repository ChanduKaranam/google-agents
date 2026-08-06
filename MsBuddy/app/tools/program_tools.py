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

"""C2 program tools — the only path from retrieved content into durable state.

Three controls are enforced here rather than in the prompt:

1. **Query isolation** — `build_program_query` assembles the search string
   from scoping terms only and then screens the result against the student's
   own stored profile. If a sensitive profile value appears in the query, the
   query is refused. Spec §5.2 invariant 1 and §8.2.3 therefore hold even if
   a model, or an injected instruction, tries to leak the student's details.

2. **Citation reality** — `save_program_record` refuses any claim whose
   `source_domain` was not actually retrieved this turn, or whose quote does
   not appear in a segment the runtime grounded against that domain. A
   fabricated citation cannot survive, which is what makes spec §7.4.2
   structural rather than instructional.

3. **Named unknowns** — what could not be sourced is returned by name, never
   omitted (spec C2).
"""

from __future__ import annotations

from typing import Any

from google.adk.tools import ToolContext

from app.config import STATE_PROFILE, STATE_SHORTLIST
from app.evidence import (
    collect_sources,
    find_supporting_source,
    make_evidence_record,
    retrieved_domains,
    value_is_supported_by_quote,
)
from app.profile_store import read_profile
from app.program_store import (
    apply_claim,
    make_program_id,
    read_shortlist,
    render_program,
    render_shortlist,
    upsert_program,
    write_shortlist,
)
from app.reference.profile_fields import FIELDS as PROFILE_FIELD_SPECS
from app.reference.program_fields import (
    ALL_FIELD_NAMES,
    is_writable,
    staleness_class_for,
)
from app.schemas import ProgramClaim

RESEARCH_AGENT_NAME = "program_research_agent"

# Profile fields that legitimately scope a search. Everything else in the
# profile is the student's private data and must never reach a query.
QUERY_SAFE_PROFILE_FIELDS = frozenset(
    {
        "target_countries",
        "specialization_interest",
        "target_intake_term",
        "target_intake_year",
    }
)

SENSITIVE_PROFILE_FIELDS = frozenset(PROFILE_FIELD_SPECS) - QUERY_SAFE_PROFILE_FIELDS

# Values shorter than this are too generic to treat as an identifying leak
# (a GPA scale key, a one-letter answer) and would cause false refusals.
MIN_SENSITIVE_TOKEN_LENGTH = 3


def _sensitive_values(profile: dict[str, Any]) -> list[tuple[str, str]]:
    """(field_name, lower-cased value) for every sensitive stored value."""
    out: list[tuple[str, str]] = []
    for name, entry in (profile.get("fields") or {}).items():
        if name not in SENSITIVE_PROFILE_FIELDS:
            continue
        value = entry.get("value")
        for item in value if isinstance(value, list) else [value]:
            text = str(item).strip().lower()
            if len(text) >= MIN_SENSITIVE_TOKEN_LENGTH:
                out.append((name, text))
    return out


def build_program_query(
    university: str,
    program: str,
    country: str,
    intake: str,
    tool_context: ToolContext,
) -> dict:
    """Build a privacy-safe web search query for a program.

    Assembles a query from scoping terms only, then checks it against the
    student's stored profile and refuses if any of their private details
    appear. Use this to construct the query before asking the research agent
    to search; never hand-write a query containing the student's scores,
    institution, budget or citizenship.

    Args:
        university: Institution name, or an empty string for an open search.
        program: Program or field of study, e.g. 'MSc Data Science'.
        country: Country to scope to, or an empty string.
        intake: Intake such as 'Fall 2027', or an empty string.

    Returns:
        A dict with the assembled `query`, or an error naming the profile
        field that would have leaked.
    """
    parts = [p.strip() for p in (university, program, country, intake) if p.strip()]
    if not parts:
        return {
            "status": "error",
            "message": "Supply at least a university or a program to search for.",
        }

    query = " ".join(parts)
    lowered = query.lower()

    profile = read_profile(tool_context.state, STATE_PROFILE)
    for field_name, value in _sensitive_values(profile):
        if value in lowered:
            return {
                "status": "error",
                "reason": "profile_data_in_query",
                "message": (
                    f"The query contains the student's '{field_name}', which "
                    "must never be sent to a search engine. Rebuild the query "
                    "from the university, program, country and intake only."
                ),
            }

    return {
        "status": "success",
        "query": query,
        "note": (
            "Privacy-checked against the stored profile. Search only for what "
            "this query asks; do not add the student's details to it."
        ),
    }


def save_program_record(
    university: str,
    program: str,
    claims: list[ProgramClaim],
    tool_context: ToolContext,
) -> dict:
    """Record verified facts about a program, with their sources.

    Every claim is checked against what was actually retrieved this turn. A
    claim naming a source that was not fetched, or quoting text that was not
    found on that source, is refused and NOT stored. Facts from official
    institution or government domains are recorded as VERIFIED; facts from
    anywhere else are recorded as REPORTED and attributed to whoever reported
    them. Fields that could not be sourced are returned as unknown.

    Args:
        university: The institution the program belongs to.
        program: The program name as published.
        claims: The facts to record. Each needs `field_name`, `value`,
            `source_domain` and a verbatim `supporting_quote` from that source.

    Returns:
        A dict with the stored record, per-claim `rejected` reasons, and the
        fields that remain unknown.
    """
    if not claims:
        return {
            "status": "error",
            "message": "No claims supplied.",
            "known_fields": list(ALL_FIELD_NAMES),
        }

    harvest = collect_sources(
        getattr(tool_context, "session", None), tool_context.state
    )
    if not harvest:
        return {
            "status": "error",
            "reason": "no_sources_retrieved",
            "message": (
                "No web sources were retrieved in this session, so nothing can "
                "be stored. Ask the research agent to search first. Never "
                "record a program fact from memory."
            ),
        }

    available = retrieved_domains(harvest)
    program_id = make_program_id(university, program)
    shortlist = read_shortlist(tool_context.state, STATE_SHORTLIST)
    record = upsert_program(shortlist, program_id, university, program)

    saved: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for raw in claims:
        claim = (
            raw if isinstance(raw, ProgramClaim) else ProgramClaim.model_validate(raw)
        )

        if not is_writable(claim.field_name):
            rejected.append(
                {
                    "field": claim.field_name,
                    "reason": "unknown_field",
                    "message": (
                        f"'{claim.field_name}' is not a program field. "
                        f"Known fields: {', '.join(ALL_FIELD_NAMES)}."
                    ),
                }
            )
            continue

        if not value_is_supported_by_quote(claim.value, claim.supporting_quote):
            rejected.append(
                {
                    "field": claim.field_name,
                    "reason": "value_not_in_quote",
                    "message": (
                        f"The quote does not contain the number(s) in "
                        f"'{claim.value}'. A real quote attached to a number "
                        "the source never stated is still a fabrication. "
                        "Quote the text that states this exact value, or "
                        "record the field as unknown."
                    ),
                }
            )
            continue

        source = find_supporting_source(
            harvest, claim.supporting_quote, claim.source_domain
        )
        if source is None:
            rejected.append(
                {
                    "field": claim.field_name,
                    "reason": "unsupported_claim",
                    "message": (
                        f"No retrieved content from '{claim.source_domain}' "
                        "contains that quote. Domains actually retrieved: "
                        f"{', '.join(sorted(available)) or 'none'}. Record this "
                        "field as unknown rather than asserting it."
                    ),
                }
            )
            continue

        evidence = make_evidence_record(
            program_id=program_id,
            field_name=claim.field_name,
            value=claim.value,
            quote=claim.supporting_quote,
            source=source,
            staleness_class=staleness_class_for(claim.field_name),
            agent_name=RESEARCH_AGENT_NAME,
        )
        saved.append(apply_claim(record, claim.field_name, claim.value, evidence))

    if saved:
        write_shortlist(tool_context.state, STATE_SHORTLIST, shortlist)

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
        "retrieved_domains": sorted(available),
        "record": render_program(record),
    }


def get_shortlist(tool_context: ToolContext) -> dict:
    """Return every program recorded so far, with tiers and staleness.

    Read this before researching a program again — a fact already stored and
    still fresh does not need re-fetching.

    Returns:
        A dict containing the shortlist and each field's provenance.
    """
    shortlist = read_shortlist(tool_context.state, STATE_SHORTLIST)
    rendered = render_shortlist(shortlist)
    return {
        "status": "success",
        "is_empty": rendered["program_count"] == 0,
        **rendered,
    }
