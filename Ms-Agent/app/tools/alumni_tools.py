"""Alumni tools — discovery proposes, this gate decides, analysis counts.

`save_alumni_findings` is the only path into the alumni store, and it
enforces the three absolute rules of the alumni brief in order:

1. **The allowlist (§26).** Every claim's domain must resolve to one of the
   26 approved sources — university/company official domains recognized
   dynamically. An unknown domain is discarded, whatever it said.
2. **No fabricated alumni (§33).** A person is admitted only if their name
   appears in text the search runtime actually attributed to an approved
   domain this session. A name in no retrieved text does not exist here.
3. **Entity resolution (§52-53).** Multi-source appearances merge into one
   entity; an immutable conflict (graduation year) splits namesakes;
   mutable conflicts (company) are retained side by side, never resolved
   silently.
"""

from __future__ import annotations

from typing import Any

from google.adk.tools import ToolContext
from pydantic import ValidationError

from app.alumni.analysis import analyze_group, similarity
from app.alumni.entity_resolution import resolve_alumni_identity
from app.alumni.models import (
    AlumniFinding,
    AlumniRecord,
    StoredClaim,
    StoredEvidence,
)
from app.alumni.source_registry import (
    DynamicDomains,
    identify_source,
    source_label,
    tier_of,
)
from app.config.settings import STATE_ALUMNI, STATE_KNOWLEDGE
from app.models.evidence import Evidence
from app.services.research_service import normalize_domain
from app.tools.profile_tools import _read_profile
from app.tools.university_tools import _collect_evidence


def _flatten(text: str) -> str:
    return " ".join(str(text or "").casefold().split())


def _dynamic_domains(
    tool_context: ToolContext, university_domain: str
) -> DynamicDomains:
    """Official university domains: the one the agent reported, plus every
    program_url domain already in the knowledge store."""
    domains = []
    if university_domain.strip():
        domains.append(normalize_domain(university_domain))
    knowledge = tool_context.state.get(STATE_KNOWLEDGE)
    for record in (knowledge or {}).values() if isinstance(knowledge, dict) else []:
        url = record.get("program_url") or ""
        domain = normalize_domain(url)
        if domain and domain not in domains:
            domains.append(domain)
    return DynamicDomains(university_domains=tuple(domains))


def save_alumni_findings(
    university: str,
    university_domain: str,
    findings: list[dict],
    tool_context: ToolContext,
) -> dict:
    """Store alumni findings that approved sources actually support.

    Args:
        university: The university these alumni are associated with.
        university_domain: The university's official domain (e.g.
            `utoronto.ca`) so its own pages count as Tier-1 sources.
        findings: One dict per person: `{"name": ..., "university": ...,
            "claims": [{"field": ..., "value": ..., "source_domain": ...}]}`.
            Valid fields: program, graduation_year, company, role, location,
            skills, research_area, publication, phd_institution, startup.

    Returns:
        Admitted people with evidence strength, per-person refusals with
        named reasons, and what happened during entity resolution.
    """
    harvest = _collect_evidence(tool_context)
    if not harvest and findings:
        return {
            "status": "error",
            "reason": "no_sources_retrieved",
            "message": (
                "Nothing was retrieved this session, so no alumni can be "
                "recorded. Research first; never record a person from memory."
            ),
        }
    dynamic = _dynamic_domains(tool_context, university_domain)
    by_domain = {e["domain"]: e for e in harvest}

    stored = tool_context.state.get(STATE_ALUMNI)
    store: dict[str, Any] = dict(stored) if isinstance(stored, dict) else {}

    admitted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for raw in findings:
        try:
            finding = AlumniFinding.model_validate(raw)
        except ValidationError as exc:
            rejected.append(
                {
                    "name": str(raw.get("name", "?")),
                    "reason": "invalid_finding",
                    "message": str(exc.errors()[0].get("msg", ""))[:160],
                }
            )
            continue

        flat_name = _flatten(finding.name)
        claims: dict[str, StoredClaim] = {}
        source_keys: list[str] = []
        claim_refusals: list[dict[str, str]] = []

        for claim in finding.claims:
            domain = normalize_domain(claim.source_domain)
            source_key = identify_source(domain, dynamic)
            if source_key is None:
                claim_refusals.append(
                    {
                        "field": claim.field,
                        "reason": "source_not_allowlisted",
                        "domain": domain,
                    }
                )
                continue
            entry = by_domain.get(domain)
            named = entry is not None and any(
                flat_name in _flatten(s) for s in entry["segments"]
            )
            if not named:
                claim_refusals.append(
                    {
                        "field": claim.field,
                        "reason": "name_not_in_retrieved_text",
                        "domain": domain,
                    }
                )
                continue
            claims[claim.field] = StoredClaim(
                value=claim.value,
                evidence=StoredEvidence(
                    source_key=source_key,
                    source_label=source_label(source_key),
                    source_domain=domain,
                    tier=tier_of(source_key),
                    url=(entry["uris"][0] if entry["uris"] else ""),
                    retrieved_at=Evidence.now_iso(),
                ),
            )
            if source_key not in source_keys:
                source_keys.append(source_key)

        if not claims:
            rejected.append(
                {
                    "name": finding.name,
                    "reason": "no_supported_claims",
                    "message": (
                        "No claim survived the allowlist and name-in-"
                        "retrieved-text checks. This person is not recorded."
                    ),
                    "claim_refusals": claim_refusals,
                }
            )
            continue

        record = AlumniRecord(
            name=finding.name,
            university=finding.university or university,
            claims=claims,
            source_keys=source_keys,
        )
        store, outcome = resolve_alumni_identity(store, record)
        admitted.append(
            {
                "name": finding.name,
                "university": record.university,
                "resolution": outcome,
                "evidence_strength": record.evidence_strength,
                "fields_stored": sorted(claims),
                "claim_refusals": claim_refusals,
            }
        )

    tool_context.state[STATE_ALUMNI] = store
    return {
        "status": "success" if admitted else "error",
        "admitted": admitted,
        "rejected": rejected,
        "note": (
            "Only admitted people may be named to the student. Rejected "
            "candidates do not exist for this conversation — report how "
            "many failed and why, never who."
        ),
    }


def get_alumni_signals(tool_context: ToolContext) -> dict:
    """Read the alumni store: per-university analysis plus student fit.

    Returns:
        Per-university career analysis with denominators (companies, role
        families, locations, research/startup/PhD counts), each resolved
        person with evidence and conflicts, and the strongest profile
        similarities to the student. Aggregate language rules: below the
        pattern threshold, report counts only.
    """
    stored = tool_context.state.get(STATE_ALUMNI)
    store = stored if isinstance(stored, dict) else {}
    if not store:
        return {
            "status": "success",
            "is_empty": True,
            "message": (
                "No verified alumni signals stored yet. Research alumni "
                "first via the alumni agent, then save findings."
            ),
        }

    records = [AlumniRecord.model_validate(r) for r in store.values()]
    profile = _read_profile(tool_context.state)

    by_university: dict[str, list[AlumniRecord]] = {}
    for record in records:
        by_university.setdefault(record.university, []).append(record)

    universities = {
        name: {
            "analysis": analyze_group(group),
            "people": [
                {
                    "name": r.name,
                    "evidence_strength": r.evidence_strength,
                    "sources": r.source_keys,
                    "possible_namesake_of": r.possible_namesake_of,
                    "facts": {
                        field: {
                            "value": c.value,
                            "source": c.evidence.source_label,
                            "tier": c.evidence.tier,
                            "url": c.evidence.url,
                            "retrieved_at": c.evidence.retrieved_at,
                            "conflicts": c.conflicts,
                        }
                        for field, c in r.claims.items()
                    },
                }
                for r in group
            ],
        }
        for name, group in by_university.items()
    }

    similarities = sorted(
        (similarity(profile, r) for r in records),
        key=lambda s: ("strong", "moderate", "weak", "none").index(s["band"]),
    )[:5]

    return {
        "status": "success",
        "is_empty": False,
        "universities": universities,
        "closest_to_student": [s for s in similarities if s["band"] != "none"],
        "presentation_rules": (
            "Distinguish alumni FACTS (a sourced claim) from PATTERNS "
            "(counts among found profiles, denominator stated) from your "
            "INFERENCE (labeled as such). Time-sensitive facts carry "
            "retrieved_at; conflicts are reported, never resolved silently."
        ),
    }
