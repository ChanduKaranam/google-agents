"""Finance tools — plan the research, gate the evidence, assemble the picture.

Four tools, one discipline (§2 of the Phase 7 brief): the planner decides
what a financial question needs; `save_finance_research` is the admission
gate for place/provider-scoped money facts (program-priced facts keep
using `save_research`); the breakdown and funding tools read stored,
graded evidence only. Arithmetic stays in app.calc — nothing here sums,
converts, or compares a single number.
"""

from __future__ import annotations

from typing import Any

from google.adk.tools import ToolContext

from app.config.settings import STATE_FINANCE, STATE_KNOWLEDGE
from app.finance.analysis import build_cost_model
from app.finance.planner import plan_finance_research
from app.finance.sources import classify_finance_source
from app.models.finance import FINANCE_FIELDS, FINANCE_SCOPE_LEVELS, FinanceRecord
from app.models.program import Program
from app.services.research_service import build_fact
from app.tools.profile_tools import _read_profile
from app.tools.university_tools import _collect_evidence

# Rules of law and government policy: only a government source states them;
# a university may relay them (capped below verified); nobody else may.
_GOVERNMENT_FACTS = frozenset({"part_time_work_rules", "visa_financial_requirement"})


def _stored_records(state: dict[str, Any] | Any) -> list[FinanceRecord]:
    stored = state.get(STATE_FINANCE)
    stored = stored if isinstance(stored, dict) else {}
    return [FinanceRecord.model_validate(raw) for raw in stored.values()]


def _stored_programs(state: dict[str, Any] | Any) -> list[Program]:
    knowledge = state.get(STATE_KNOWLEDGE)
    knowledge = knowledge if isinstance(knowledge, dict) else {}
    return [Program.model_validate(raw) for raw in knowledge.values()]


def plan_financial_research(question: str, tool_context: ToolContext) -> dict:
    """Plan what a financial question needs before researching anything.

    Args:
        question: The student's financial question, verbatim.

    Returns:
        The financial intents the question carries, the program fields and
        scoped finance facts still missing for them, the calculations that
        will close the loop, and at most ONE profile question worth asking
        the student now. Research only what it names; ask only that
        question.
    """
    profile = _read_profile(tool_context.state)
    plan = plan_finance_research(
        question,
        profile,
        _stored_programs(tool_context.state),
        _stored_records(tool_context.state),
    )
    return {"status": "success", "plan": plan}


def save_finance_research(
    scope_level: str,
    scope_name: str,
    claims: list[dict],
    tool_context: ToolContext,
    university_website: str = "",
) -> dict:
    """Store researched financial facts at their real scope, graded.

    For money facts that belong to a place, provider or market — NOT to
    one program (those go through `save_research`). Every claim is graded
    against what was genuinely retrieved this session.

    Args:
        scope_level: `city`, `country`, `provider`, or `market`.
        scope_name: e.g. `Toronto`, `Canada`, a lender's name.
        claims: One dict per fact: `{"field": <category>, "value": <as
            published>, "source_domain": <domain>, "quote": <optional>}`.
            Valid categories: living_cost, housing, food, transport,
            utilities, health_insurance, part_time_work_rules,
            visa_financial_requirement, loan_terms, interest_rate,
            exchange_rate, external_scholarships, travel_cost.
        university_website: The relevant university's official domain, if
            known — improves source classification.

    Returns:
        Per-claim verification statuses and refusals. Work rules and visa
        fund requirements demand government sources; community posts and
        cost-of-living datasets can report living costs, never verify
        them.
    """
    if scope_level not in FINANCE_SCOPE_LEVELS:
        return {
            "status": "error",
            "reason": "invalid_scope",
            "message": f"scope_level must be one of {FINANCE_SCOPE_LEVELS}.",
        }
    if not scope_name.strip():
        return {
            "status": "error",
            "reason": "missing_scope_name",
            "message": "Name the city/country/provider this fact belongs to.",
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
        if field not in FINANCE_FIELDS:
            refused.append(
                {
                    "field": field,
                    "reason": "unknown_field",
                    "valid_fields": sorted(FINANCE_FIELDS),
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
            university_website=university_website,
            quote=str(claim.get("quote", "")),
        )
        authority = classify_finance_source(domain, university_website)
        if field in _GOVERNMENT_FACTS:
            if authority["source_type"] == "official":
                # A university page can relay the rule; only the government
                # states it.
                if fact.status == "verified":
                    fact = fact.model_copy(update={"status": "partially_verified"})
            elif authority["source_type"] != "government":
                refused.append(
                    {
                        "field": field,
                        "reason": "source_lacks_authority",
                        "message": (
                            f"'{fact.evidence.source_domain}' cannot establish "
                            f"'{field}' — legal and visa rules come from the "
                            "official government source."
                        ),
                    }
                )
                continue
        elif authority["source_type"] == "community":
            # Lived experience is context, never verification.
            fact = fact.model_copy(update={"status": "unverified"})
        elif (
            authority["source_type"] in ("aggregator", "cost_of_living")
            and fact.status == "verified"
        ):
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

    entry = FinanceRecord(
        scope_level=scope_level, scope_name=scope_name.strip(), facts=stored_facts
    )
    finance = tool_context.state.get(STATE_FINANCE)
    finance = dict(finance) if isinstance(finance, dict) else {}
    existing = finance.get(entry.key)
    if isinstance(existing, dict):
        merged = FinanceRecord.model_validate(existing)
        merged_facts = dict(merged.facts)
        for field, new_fact in stored_facts.items():
            prior = merged_facts.get(field)
            if (
                prior is not None
                and prior.value.strip() != new_fact.value.strip()
                and prior.evidence.source_domain != new_fact.evidence.source_domain
            ):
                new_fact.conflicts.append(
                    {
                        "value": prior.value,
                        "source_domain": prior.evidence.source_domain,
                        "retrieved_at": prior.evidence.retrieved_at,
                    }
                )
            merged_facts[field] = new_fact
        entry = entry.model_copy(update={"facts": merged_facts})
    finance[entry.key] = entry.model_dump()
    tool_context.state[STATE_FINANCE] = finance

    return {
        "status": "success"
        if graded and not refused
        else ("partial" if graded else "error"),
        "scope": entry.key,
        "graded_claims": graded,
        "refused_claims": refused,
        "note": (
            "Present each fact at its stored scope — a city figure is a "
            "city figure, never a program figure. Unverified claims are "
            "context with a named source, never facts."
        ),
    }


def build_cost_breakdown(tool_context: ToolContext) -> dict:
    """Assemble the researched cost picture per university, with provenance.

    Reads stored program facts and scoped finance facts only. Every
    component carries its source, status, scope and freshness; unknown
    components are named as unknown, never filled in. `calculation_inputs`
    (typed low/high line items, duration, currency) feed
    `calculate_total_cost` and then `calculate_budget_fit` — relay their
    excluded items and assumptions alongside any total.

    Returns:
        Per-university cost models, or an honest error when nothing
        financial has been researched yet.
    """
    programs = _stored_programs(tool_context.state)
    records = _stored_records(tool_context.state)
    if not programs and not records:
        return {
            "status": "error",
            "reason": "no_financial_evidence",
            "message": (
                "No financial evidence is stored yet. Research the "
                "program's tuition/fees and the city's living costs "
                "first, then rebuild the breakdown."
            ),
        }
    profile = _read_profile(tool_context.state)
    intake = profile.target.intake or ""
    return {
        "status": "success",
        "universities": [
            build_cost_model(program, records, intake) for program in programs
        ],
        "finance_facts_on_record": [
            {"scope": record.key, "categories": sorted(record.facts)}
            for record in records
        ],
        "note": (
            "Totals come from calculate_total_cost and affordability from "
            "calculate_budget_fit; a range stays a range (low/high "
            "scenarios); a stale year is said as its year. Nothing here "
            "is a promise of cost, funding or approval."
        ),
    }


def get_funding_options(tool_context: ToolContext) -> dict:
    """Read the stored funding evidence: scholarships, TA/RA, work, loans.

    Returns:
        Published funding evidence with sources and statuses. Scholarships
        are eligibility criteria the student may meet — never a promised
        award. Part-time work carries the government-sourced legal limit
        separately from earnings, which stay unknown unless evidenced.
    """
    scholarships: list[dict[str, Any]] = []
    assistantships: list[dict[str, Any]] = []
    loans: list[dict[str, Any]] = []
    legal_limit: dict[str, Any] = {
        "status": "unknown",
        "note": "No government-sourced work rule stored yet.",
    }

    def cell(fact: Any, **extra: Any) -> dict[str, Any]:
        return {
            "value": fact.value,
            "verification_status": fact.status,
            "source_domain": fact.evidence.source_domain,
            "url": fact.evidence.url,
            "retrieved_at": fact.evidence.retrieved_at,
            **extra,
        }

    for program in _stored_programs(tool_context.state):
        where = {"university": program.university, "program": program.name}
        for field, bucket in (
            ("scholarships", scholarships),
            ("funding_evidence", scholarships),
            ("assistantship_evidence", assistantships),
        ):
            if field in program.facts:
                bucket.append(cell(program.facts[field], **where))

    for record in _stored_records(tool_context.state):
        scope = {"scope": record.key}
        if "external_scholarships" in record.facts:
            scholarships.append(cell(record.facts["external_scholarships"], **scope))
        for field in ("loan_terms", "interest_rate"):
            if field in record.facts:
                loans.append(cell(record.facts[field], field=field, **scope))
        if "part_time_work_rules" in record.facts:
            legal_limit = cell(record.facts["part_time_work_rules"], **scope)

    if not (scholarships or assistantships or loans) and "value" not in legal_limit:
        return {
            "status": "error",
            "reason": "no_funding_evidence",
            "message": (
                "No funding evidence is stored yet. Research the "
                "university's scholarship/assistantship pages, external "
                "providers, and the government's work rules first."
            ),
        }

    return {
        "status": "success",
        "scholarships": scholarships,
        "assistantships": assistantships,
        "loans": loans,
        "part_time_work": {
            "legal_limit": legal_limit,
            "expected_earnings": {
                "status": "unknown",
                "note": (
                    "Potential earnings need labour-market evidence and "
                    "are never assumed."
                ),
            },
            "note": (
                "The legal work limit and expected earnings are separate "
                "things. Part-time work may help with living expenses; it "
                "is never assumed to cover tuition."
            ),
        },
        "note": (
            "Published criteria only: the student may be eligible where "
            "the stated conditions fit their profile — award decisions "
            "belong to the providers, and researched loan terms feed "
            "calculate_loan_emi for the numbers. Nothing here promises an "
            "award, an approval, or an income."
        ),
    }
