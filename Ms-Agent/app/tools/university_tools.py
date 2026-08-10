"""University knowledge tools — research in, graded facts out.

`save_research` is the admission gate for institutional facts: every claim
the research agent proposed is graded against what the search runtime
actually retrieved (the evidence ledger), stored with its source, and
reported back with its verification status. There is no path into the
knowledge store that skips grading.
"""

from __future__ import annotations

from typing import Any

from google.adk.tools import ToolContext

from app.config.settings import STATE_EVIDENCE, STATE_KNOWLEDGE
from app.models.program import PROGRAM_FIELDS, Program
from app.services.research_service import build_fact, harvest_grounding

# Facts a student will act on with money or a deadline. These demand a
# source with standing: community/video/social platforms can never supply
# them (V1's live probe served a deadline "reported by youtube.com"), and a
# non-official source can at best report them, never verify them.
AUTHORITATIVE_FIELDS: frozenset[str] = frozenset(
    {
        "application_deadline",
        "tuition",
        "tuition_currency",
        "gpa_requirement",
        "english_requirement",
        "gre_requirement",
        "intake",
    }
)


def _collect_evidence(tool_context: ToolContext) -> list[dict[str, Any]]:
    """Session grounding plus the ledger the research callback stored."""
    entries: dict[str, dict[str, Any]] = {}
    session = getattr(tool_context, "session", None)
    for entry in harvest_grounding(session):
        entries[entry["domain"]] = entry
    stored = tool_context.state.get(STATE_EVIDENCE)
    for entry in stored if isinstance(stored, list) else []:
        domain = entry.get("domain")
        if not domain:
            continue
        if domain in entries:
            known = entries[domain]["segments"]
            known.extend(s for s in entry.get("segments", []) if s not in known)
        else:
            entries[domain] = entry
    return list(entries.values())


def save_research(
    university: str,
    program: str,
    country: str,
    program_url: str,
    claims: list[dict],
    tool_context: ToolContext,
) -> dict:
    """Store researched program facts, graded against retrieved evidence.

    Args:
        university: University name, e.g. `University of Toronto`.
        program: Program name, e.g. `MSc Computer Science`.
        country: Country the program is in, if stated.
        program_url: The program page URL, if found.
        claims: One dict per fact: `{"field": <slot>, "value": <as
            published>, "source_domain": <domain>, "quote": <supporting
            text, optional>}`. Valid slots: tuition, tuition_currency,
            duration, intake, application_deadline, gpa_requirement,
            english_requirement, gre_requirement, structure,
            coop_available, other_requirements.

    Returns:
        Per-claim verification statuses (verified / partially_verified /
        unverified), refusals for unknown fields, and the fields still
        unknown for this program.
    """
    if not university.strip() or not program.strip():
        return {
            "status": "error",
            "reason": "missing_identity",
            "message": "A program needs both a university and a program name.",
        }

    harvest = _collect_evidence(tool_context)
    if not harvest and claims:
        return {
            "status": "error",
            "reason": "no_sources_retrieved",
            "message": (
                "Nothing was retrieved this session, so no claim can be "
                "graded. Research first; never record from memory."
            ),
        }

    stored_facts: dict[str, Any] = {}
    graded: list[dict[str, Any]] = []
    refused: list[dict[str, Any]] = []
    for claim in claims:
        field = str(claim.get("field", "")).strip()
        value = str(claim.get("value", "")).strip()
        domain = str(claim.get("source_domain", "")).strip()
        if field not in PROGRAM_FIELDS:
            refused.append(
                {
                    "field": field,
                    "reason": "unknown_field",
                    "valid_fields": sorted(PROGRAM_FIELDS),
                }
            )
            continue
        if not value or not domain:
            refused.append({"field": field, "reason": "missing_value_or_source"})
            continue
        fact = build_fact(
            value,
            domain,
            harvest,
            university_website="",
            quote=str(claim.get("quote", "")),
        )
        # The authority gate. Verification asks "was this genuinely
        # retrieved"; authority asks "does this source have standing to
        # state this fact". Both must hold.
        if field in AUTHORITATIVE_FIELDS:
            if fact.evidence.source_type == "community":
                refused.append(
                    {
                        "field": field,
                        "reason": "source_lacks_authority",
                        "message": (
                            f"'{fact.evidence.source_domain}' is a community/"
                            "social platform and cannot establish "
                            f"'{field}'. Use the university's own pages."
                        ),
                    }
                )
                continue
            if fact.evidence.source_type == "aggregator" and fact.status == "verified":
                # An aggregator can report an admission fact, never verify
                # it — restating a figure is not confirming it. "other"
                # keeps its grading: most universities outside the US have
                # no .edu suffix, and without a university-domain registry
                # (a V2.1 item) their own sites classify as "other".
                fact = fact.model_copy(update={"status": "partially_verified"})
        stored_facts[field] = fact
        graded.append(
            {
                "field": field,
                "value": value,
                "verification_status": fact.status,
                "source_domain": fact.evidence.source_domain,
                "source_type": fact.evidence.source_type,
                "url": fact.evidence.url,
            }
        )

    entry = Program(
        university=university.strip(),
        name=program.strip(),
        country=country.strip(),
        program_url=program_url.strip(),
        facts=stored_facts,
    )

    knowledge = tool_context.state.get(STATE_KNOWLEDGE)
    knowledge = dict(knowledge) if isinstance(knowledge, dict) else {}
    existing = knowledge.get(entry.key)
    if isinstance(existing, dict):
        # New facts land on top of old; old facts survive when not re-stated.
        merged = Program.model_validate(existing)
        merged_facts = dict(merged.facts)
        merged_facts.update(stored_facts)
        entry = entry.model_copy(update={"facts": merged_facts})
    knowledge[entry.key] = entry.model_dump()
    tool_context.state[STATE_KNOWLEDGE] = knowledge

    return {
        "status": "success"
        if graded and not refused
        else ("partial" if graded else "error"),
        "program_key": entry.key,
        "graded_claims": graded,
        "refused_claims": refused,
        "unknown_fields": entry.unknown_fields(),
        "note": (
            "Unverified claims must be presented as unconfirmed, with their "
            "source named — never as fact."
        ),
    }


def get_programs(tool_context: ToolContext) -> dict:
    """Read every researched program with its graded facts.

    Returns:
        Programs keyed by university::program, each fact carrying value,
        verification status, source domain and URL, plus unknown fields.
    """
    knowledge = tool_context.state.get(STATE_KNOWLEDGE)
    knowledge = knowledge if isinstance(knowledge, dict) else {}
    programs = []
    for raw in knowledge.values():
        entry = Program.model_validate(raw)
        programs.append(
            {
                "university": entry.university,
                "program": entry.name,
                "country": entry.country,
                "program_url": entry.program_url,
                "facts": {
                    name: {
                        "value": fact.value,
                        "verification_status": fact.status,
                        "source_domain": fact.evidence.source_domain,
                        "source_type": fact.evidence.source_type,
                        "url": fact.evidence.url,
                        "retrieved_at": fact.evidence.retrieved_at,
                    }
                    for name, fact in entry.facts.items()
                },
                "unknown_fields": entry.unknown_fields(),
            }
        )
    return {"status": "success", "count": len(programs), "programs": programs}
