"""Phase 7 — finance intelligence: planner, sources, extraction, cost model.

The rules pinned before implementation:

* **No static finance database.** The registry carries metadata and search
  strategies only — never a currency amount. All numbers arrive through
  the evidence gate or not at all.
* **Scope is preserved** (§29): a city living cost stays city-scoped, a
  university-wide estimate never becomes a program figure, a "scholarship
  up to X" never becomes "you will receive X".
* **Ranges survive** (§22): CAD 900–1,400 stays a range; a midpoint is
  never silently minted.
* **The Calculation Agent stays the only arithmetic engine** (§2): the
  cost model prepares typed inputs; sums, conversions, EMI and budget fit
  happen in app.calc — nothing here re-implements them.
* Legal work limits come from government sources only; expected earnings
  are a separate thing and never become "tuition funding" (§18).
"""

from __future__ import annotations

import re
from types import SimpleNamespace
from typing import Any

import pytest

from app.calc.finance import budget_fit, total_cost
from app.config.settings import STATE_EVIDENCE, STATE_FINANCE, STATE_PROFILE
from app.finance.analysis import (
    assess_money_freshness,
    build_cost_model,
    extract_money,
)
from app.finance.planner import classify_financial_intents, plan_finance_research
from app.finance.sources import FINANCE_SOURCE_REGISTRY, classify_finance_source
from app.models.finance import FINANCE_FIELDS, FinanceRecord
from app.models.program import PROGRAM_FIELDS, Program
from app.models.student import StudentProfile
from app.tools.finance_tools import (
    build_cost_breakdown,
    get_funding_options,
    plan_financial_research,
    save_finance_research,
)
from app.tools.university_tools import save_research


class StubToolContext:
    def __init__(self) -> None:
        self.state: dict[str, Any] = {}
        self.invocation_id = "test"
        self.session = SimpleNamespace(events=[])


def stub_evidence(context: StubToolContext, domain: str, segment: str) -> None:
    ledger = context.state.get(STATE_EVIDENCE) or []
    ledger.append(
        {
            "domain": domain,
            "uris": [f"https://{domain}/x"],
            "titles": [domain],
            "segments": [segment],
        }
    )
    context.state[STATE_EVIDENCE] = ledger


# --- Financial intent classification (§5) ------------------------------------


@pytest.mark.parametrize(
    ("question", "intent"),
    [
        ("Can I afford Waterloo with a 30 lakh budget?", "budget_fit"),
        ("How much money do I need for MS in Canada?", "total_cost"),
        ("How much tuition will I pay for the entire program?", "tuition"),
        ("What are the living expenses in Toronto?", "living_cost"),
        ("How much does housing cost near the university?", "housing"),
        ("How much does health insurance cost?", "insurance"),
        ("What scholarships can I get?", "scholarship"),
        ("What assistantships are available?", "assistantship"),
        ("Should I take a 30 lakh loan?", "loan"),
        ("What would my EMI be?", "loan"),
        ("Can I fund my MS through part-time work?", "part_time_work"),
        ("How much money do I need to show for the visa?", "visa_financial_requirement"),
        ("Compare the cost of Waterloo and UBC.", "university_comparison"),
        ("Which Canadian university is cheaper for MS CS?", "university_comparison"),
        ("What is the ROI of doing MS?", "roi"),
    ],
)
def test_questions_classify_to_their_financial_intent(
    question: str, intent: str
) -> None:
    assert intent in classify_financial_intents(question)


def test_a_question_can_carry_multiple_intents() -> None:
    intents = classify_financial_intents(
        "What would my EMI be for a loan covering Waterloo's tuition?"
    )
    assert "loan" in intents
    assert "tuition" in intents


def test_an_unmatched_question_plans_as_general_cost_with_a_note() -> None:
    plan = plan_finance_research(
        "Tell me about the weather", StudentProfile(), [], []
    )
    assert plan["intents"] == ["total_cost"]
    assert plan["intent_note"]


# --- The research planner (§5, §6, §7) ---------------------------------------


def profiled() -> StudentProfile:
    return StudentProfile.model_validate(
        {
            "target": {"country": "Canada", "specialization": "CS", "intake": "Fall 2027"},
            "preferences": {"budget": 3000000, "budget_currency": "INR"},
        }
    )


def waterloo(facts: dict[str, dict[str, str]]) -> Program:
    return Program.model_validate(
        {
            "university": "University of Waterloo",
            "name": "MMath Computer Science",
            "country": "Canada",
            "city": "Waterloo",
            "facts": {
                field: {
                    "value": spec["value"],
                    "status": spec.get("status", "verified"),
                    "evidence": {
                        "source_domain": spec.get("domain", "uwaterloo.ca"),
                        "source_type": spec.get("type", "official"),
                        "retrieved_at": "2026-08-11T00:00:00+00:00",
                    },
                }
                for field, spec in facts.items()
            },
        }
    )


def test_the_planner_researches_only_what_the_intent_needs() -> None:
    plan = plan_finance_research(
        "What scholarships can I get?", profiled(), [waterloo({})], []
    )
    program_fields = set(plan["research_requirements"][0]["missing_program_fields"])
    finance = {need["category"] for need in plan["finance_research"]}
    assert "scholarships" in program_fields
    assert "external_scholarships" in finance
    assert "housing_cost" not in program_fields
    assert "loan_terms" not in finance


def test_the_planner_skips_facts_already_stored() -> None:
    program = waterloo({"tuition": {"value": "CAD 15,858 per term"}})
    plan = plan_finance_research(
        "How much tuition will I pay?", profiled(), [program], []
    )
    assert "tuition" not in plan["research_requirements"][0]["missing_program_fields"]


def test_no_stored_programs_means_discovery_first() -> None:
    plan = plan_finance_research(
        "How much will an MS cost me?", profiled(), [], []
    )
    assert plan["needs_discovery"] is True


def test_a_missing_budget_is_the_one_next_question() -> None:
    plan = plan_finance_research(
        "Can I afford MS in Canada?", StudentProfile(), [], []
    )
    assert plan["next_question"] is not None
    assert plan["next_question"]["path"] == "preferences.budget"
    assert "budget" in plan["next_question"]["question"].casefold()


def test_questions_are_progressive_never_repeated() -> None:
    plan = plan_finance_research(
        "Can I afford MS in Canada?", profiled(), [], []
    )
    next_question = plan["next_question"]
    assert next_question is None or next_question["path"] not in (
        "preferences.budget",
        "preferences.budget_currency",
    )


def test_budget_questions_are_not_asked_for_component_questions() -> None:
    """A tuition lookup does not need the student's budget."""
    plan = plan_finance_research(
        "How much tuition will I pay?", StudentProfile(), [waterloo({})], []
    )
    next_question = plan["next_question"]
    assert next_question is None or next_question["path"] != "preferences.budget"


# --- The source registry (§3, §8, §9) ----------------------------------------


def test_the_registry_contains_no_financial_values() -> None:
    """Metadata and strategies only — a digit would be a smuggled number."""
    assert not re.search(r"\d", str(FINANCE_SOURCE_REGISTRY))


def test_every_registry_entry_carries_the_required_metadata() -> None:
    for entry in FINANCE_SOURCE_REGISTRY:
        assert entry["source_name"]
        assert entry["source_type"]
        assert entry["authority_level"] in ("primary", "institutional", "secondary", "community")
        assert entry["allowed_claim_types"]
        assert entry["search_strategy"]


@pytest.mark.parametrize(
    ("domain", "source_type", "level"),
    [
        ("canada.ca", "government", 1),
        ("ircc.canada.ca", "government", 1),
        ("cic.gc.ca", "government", 1),
        ("uwaterloo.ca", "official", 1),
        ("numbeo.com", "cost_of_living", 3),
        ("yocket.com", "aggregator", 3),
        ("reddit.com", "community", 4),
        ("some-blog.com", "other", 3),
    ],
)
def test_finance_sources_classify_by_authority(
    domain: str, source_type: str, level: int
) -> None:
    result = classify_finance_source(domain, university_website="uwaterloo.ca")
    assert result["source_type"] == source_type
    assert result["authority_level"] == level


# --- Money extraction (§12, §20, §22) ----------------------------------------


def test_a_single_amount_carries_currency_period_and_year() -> None:
    money = extract_money("Tuition is CAD 15,858 per term (2025)")
    assert money["currency"] == "CAD"
    assert money["amount"] == 15858
    assert money["period"] == "term"
    assert money["year"] == 2025
    assert money["is_range"] is False


def test_a_range_is_preserved_never_averaged() -> None:
    money = extract_money("Off-campus housing costs CAD 900–1,400 per month")
    assert money["is_range"] is True
    assert money["low"] == 900
    assert money["high"] == 1400
    assert money["amount"] is None  # no silent midpoint


def test_lakh_notation_is_understood() -> None:
    money = extract_money("My budget is ₹30 lakh")
    assert money["currency"] == "INR"
    assert money["amount"] == 3000000


def test_a_bare_dollar_sign_does_not_guess_the_currency() -> None:
    money = extract_money("The fee is $1,715 per term")
    assert money["amount"] == 1715
    assert money["currency"] is None  # USD? CAD? The text does not say.


def test_an_amount_before_its_currency_code_is_understood() -> None:
    """Live finding: sources also write '44,000 CAD', not only 'CAD 44,000'."""
    money = extract_money("Tuition is 44,000 CAD per year (2025)")
    assert money["amount"] == 44000
    assert money["currency"] == "CAD"
    assert money["period"] == "year"


def test_a_range_with_a_trailing_code_survives() -> None:
    money = extract_money("Rent runs 900–1,400 CAD monthly")
    assert money["is_range"] is True
    assert money["low"] == 900
    assert money["high"] == 1400
    assert money["currency"] == "CAD"


def test_dollar_abbreviations_name_their_country() -> None:
    assert extract_money("C$44,000 per year")["currency"] == "CAD"
    assert extract_money("US$44,000")["currency"] == "USD"


def test_a_year_before_a_code_is_not_an_amount() -> None:
    money = extract_money("For 2025 CAD figures see the fee page")
    assert money["amount"] is None


def test_an_academic_year_range_is_not_a_money_range() -> None:
    money = extract_money("Fees for 2025–2026 CAD amounts are listed per term")
    assert money["is_range"] is False
    assert money["low"] is None


def test_no_amount_stays_none() -> None:
    money = extract_money("Tuition is competitive for international students")
    assert money["amount"] is None
    assert money["low"] is None


# --- Freshness (§13) ----------------------------------------------------------


def test_a_stale_fee_year_is_flagged() -> None:
    result = assess_money_freshness("CAD 43,000 per year (2024-2025)", "Fall 2027")
    assert result["status"] == "stale"


def test_a_current_fee_year_is_accepted() -> None:
    result = assess_money_freshness("CAD 43,000 for 2026-2027", "Fall 2027")
    assert result["status"] == "appears_current"


def test_no_stated_year_is_unclear_never_current() -> None:
    result = assess_money_freshness("CAD 43,000 per year", "Fall 2027")
    assert result["status"] == "year_unclear"


# --- The finance evidence gate (§8, §11, §28) --------------------------------


def test_the_gate_refuses_claims_without_retrieval() -> None:
    context = StubToolContext()
    result = save_finance_research(
        "city",
        "Toronto",
        [{"field": "living_cost", "value": "CAD 2,000/month", "source_domain": "x.ca"}],
        context,
    )
    assert result["status"] == "error"
    assert result["reason"] == "no_sources_retrieved"


def test_an_unknown_category_is_refused() -> None:
    context = StubToolContext()
    stub_evidence(context, "canada.ca", "some text")
    result = save_finance_research(
        "country",
        "Canada",
        [{"field": "lottery_odds", "value": "high", "source_domain": "canada.ca"}],
        context,
    )
    assert result["refused_claims"][0]["reason"] == "unknown_field"


def test_an_invalid_scope_level_is_refused() -> None:
    context = StubToolContext()
    stub_evidence(context, "canada.ca", "text")
    result = save_finance_research("galaxy", "Milky Way", [], context)
    assert result["status"] == "error"
    assert result["reason"] == "invalid_scope"


def test_work_rules_from_community_sources_are_refused() -> None:
    context = StubToolContext()
    stub_evidence(context, "reddit.com", "students can work 40 hours")
    result = save_finance_research(
        "country",
        "Canada",
        [
            {
                "field": "part_time_work_rules",
                "value": "40 hours per week",
                "source_domain": "reddit.com",
            }
        ],
        context,
    )
    assert result["refused_claims"][0]["reason"] == "source_lacks_authority"


def test_work_rules_from_government_verify() -> None:
    context = StubToolContext()
    stub_evidence(
        context,
        "canada.ca",
        "Eligible students may work off campus up to 24 hours per week",
    )
    result = save_finance_research(
        "country",
        "Canada",
        [
            {
                "field": "part_time_work_rules",
                "value": "up to 24 hours per week",
                "source_domain": "canada.ca",
            }
        ],
        context,
    )
    assert result["graded_claims"][0]["verification_status"] == "verified"


def test_visa_funds_from_a_university_page_cap_at_partially_verified() -> None:
    """A university can relay the rule; only the government states it."""
    context = StubToolContext()
    stub_evidence(
        context, "uwaterloo.ca", "you must show CAD 20,635 in available funds"
    )
    result = save_finance_research(
        "country",
        "Canada",
        [
            {
                "field": "visa_financial_requirement",
                "value": "CAD 20,635 in available funds",
                "source_domain": "uwaterloo.ca",
            }
        ],
        context,
        university_website="uwaterloo.ca",
    )
    assert result["graded_claims"][0]["verification_status"] == "partially_verified"


def test_community_living_costs_are_context_never_verified() -> None:
    context = StubToolContext()
    stub_evidence(context, "reddit.com", "I spend about CAD 1,800 per month")
    result = save_finance_research(
        "city",
        "Toronto",
        [
            {
                "field": "living_cost",
                "value": "about CAD 1,800 per month",
                "source_domain": "reddit.com",
            }
        ],
        context,
    )
    assert result["graded_claims"][0]["verification_status"] == "unverified"


def test_cost_of_living_datasets_report_but_never_verify() -> None:
    context = StubToolContext()
    stub_evidence(context, "numbeo.com", "single person costs CAD 1,500 per month")
    result = save_finance_research(
        "city",
        "Toronto",
        [
            {
                "field": "living_cost",
                "value": "CAD 1,500 per month",
                "source_domain": "numbeo.com",
            }
        ],
        context,
    )
    assert result["graded_claims"][0]["verification_status"] == "partially_verified"


def test_a_differing_prior_value_is_kept_as_a_conflict() -> None:
    context = StubToolContext()
    stub_evidence(context, "canada.ca", "CAD 1,900 per month before rent")
    stub_evidence(context, "numbeo.com", "CAD 1,500 per month")
    for domain, value in (
        ("numbeo.com", "CAD 1,500 per month"),
        ("canada.ca", "CAD 1,900 per month before rent"),
    ):
        save_finance_research(
            "city",
            "Toronto",
            [{"field": "living_cost", "value": value, "source_domain": domain}],
            context,
        )
    record = FinanceRecord.model_validate(
        context.state[STATE_FINANCE]["city::toronto"]
    )
    assert record.facts["living_cost"].conflicts
    assert record.facts["living_cost"].conflicts[0]["source_domain"] == "numbeo.com"


# --- New program money slots (§11, §12) --------------------------------------


def test_the_money_slots_exist_on_programs() -> None:
    for field in (
        "mandatory_fees",
        "billing_structure",
        "living_cost_estimate",
        "housing_cost",
        "health_insurance_cost",
        "application_fee",
        "deposit",
        "assistantship_evidence",
        "funding_evidence",
    ):
        assert field in PROGRAM_FIELDS


def test_program_money_facts_demand_authoritative_sources() -> None:
    context = StubToolContext()
    stub_evidence(context, "youtube.com", "fees are CAD 8,000 per term")
    result = save_research(
        "University of Waterloo",
        "MMath Computer Science",
        "Canada",
        "",
        [
            {
                "field": "mandatory_fees",
                "value": "CAD 8,000 per term",
                "source_domain": "youtube.com",
            }
        ],
        context,
    )
    assert result["refused_claims"][0]["reason"] == "source_lacks_authority"


# --- The cost model (§21, §22, §23, §29) -------------------------------------


def city_living(value: str, domain: str = "canada.ca") -> FinanceRecord:
    return FinanceRecord.model_validate(
        {
            "scope_level": "city",
            "scope_name": "Waterloo",
            "facts": {
                "housing": {
                    "value": value,
                    "status": "verified",
                    "evidence": {
                        "source_domain": domain,
                        "source_type": "government",
                        "retrieved_at": "2026-08-11T00:00:00+00:00",
                    },
                }
            },
        }
    )


def test_unknown_components_are_named_never_invented() -> None:
    model = build_cost_model(
        waterloo({"tuition": {"value": "CAD 43,000 per year (2026)"}}), [], "Fall 2027"
    )
    assert "food" in model["unknown_components"]
    assert "health_insurance" in model["unknown_components"]
    rendered = str(model)
    assert "typical" not in rendered.casefold()


def test_a_range_survives_into_low_and_high_scenarios() -> None:
    model = build_cost_model(
        waterloo({"tuition": {"value": "CAD 43,000 per year (2026)"}}),
        [city_living("CAD 900–1,400 per month")],
        "Fall 2027",
    )
    inputs = model["calculation_inputs"]
    low = {i["label"]: i["amount"] for i in inputs["items_low"]}
    high = {i["label"]: i["amount"] for i in inputs["items_high"]}
    assert low["housing"] == 900 * 12
    assert high["housing"] == 1400 * 12
    assert not any(i["amount"] == 1150 * 12 for i in inputs["items_low"])


def test_monthly_amounts_annualize_with_their_basis_stated() -> None:
    model = build_cost_model(
        waterloo({"tuition": {"value": "CAD 43,000 per year (2026)"}}),
        [city_living("CAD 1,000 per month")],
        "Fall 2027",
    )
    item = next(
        i
        for i in model["calculation_inputs"]["items_low"]
        if i["label"] == "housing"
    )
    assert item["amount"] == 12000
    assert "12" in item["basis"]


def test_per_term_tuition_is_never_silently_annualized() -> None:
    model = build_cost_model(
        waterloo({"tuition": {"value": "CAD 15,858 per term (2026)"}}), [], "Fall 2027"
    )
    labels = {i["label"] for i in model["calculation_inputs"]["items_low"]}
    assert "tuition" not in labels
    excluded = {e["label"]: e["reason"] for e in model["calculation_inputs"]["excluded"]}
    assert "term" in excluded["tuition"].casefold()


def test_a_mismatched_currency_is_excluded_not_converted() -> None:
    model = build_cost_model(
        waterloo({"tuition": {"value": "CAD 43,000 per year (2026)"}}),
        [city_living("INR 90,000 per month")],
        "Fall 2027",
    )
    labels = {i["label"] for i in model["calculation_inputs"]["items_low"]}
    assert "housing" not in labels
    excluded = {e["label"]: e["reason"] for e in model["calculation_inputs"]["excluded"]}
    assert "convert" in excluded["housing"].casefold()


def test_one_time_costs_spread_across_known_duration() -> None:
    model = build_cost_model(
        waterloo(
            {
                "tuition": {"value": "CAD 43,000 per year (2026)"},
                "duration": {"value": "2 years"},
                "application_fee": {"value": "CAD 125"},
            }
        ),
        [],
        "Fall 2027",
    )
    item = next(
        i
        for i in model["calculation_inputs"]["items_low"]
        if i["label"] == "application_fee"
    )
    assert item["amount"] == pytest.approx(62.5)
    assert "one-time" in item["basis"].casefold()


def test_the_cost_model_output_feeds_the_calculation_agent() -> None:
    """Finance finds the numbers; app.calc computes with them (§2)."""
    model = build_cost_model(
        waterloo(
            {
                "tuition": {"value": "CAD 43,000 per year (2026)"},
                "duration": {"value": "2 years"},
            }
        ),
        [city_living("CAD 1,000 per month")],
        "Fall 2027",
    )
    inputs = model["calculation_inputs"]
    totals = total_cost(inputs["items_low"], inputs["years"], inputs["currency"])
    assert totals["result"] == (43000 + 12000) * 2
    fit = budget_fit(100000, totals["result"], inputs["currency"])
    assert fit["verdict"] == "shortfall"
    assert fit["result"] == 10000


def test_freshness_travels_with_each_component() -> None:
    model = build_cost_model(
        waterloo({"tuition": {"value": "CAD 40,000 per year (2024-2025)"}}),
        [],
        "Fall 2027",
    )
    tuition = next(c for c in model["components"] if c["component"] == "tuition")
    assert tuition["freshness"]["status"] == "stale"


def test_city_scope_stays_on_city_facts() -> None:
    model = build_cost_model(
        waterloo({"tuition": {"value": "CAD 43,000 per year (2026)"}}),
        [city_living("CAD 1,000 per month")],
        "Fall 2027",
    )
    housing = next(c for c in model["components"] if c["component"] == "housing")
    assert housing["scope"] == "city: Waterloo"


# --- The breakdown and funding tools (§16, §17, §18, §30) --------------------


def researched_context() -> StubToolContext:
    context = StubToolContext()
    context.state[STATE_PROFILE] = profiled().model_dump()
    stub_evidence(
        context,
        "uwaterloo.ca",
        "Tuition is CAD 43,000 per year (2026). The program takes 2 years. "
        "The President's Graduate Scholarship offers up to CAD 10,000 for "
        "students holding a Tri-Agency award. Graduate TA positions are "
        "available in the school each term.",
    )
    save_research(
        "University of Waterloo",
        "MMath Computer Science",
        "Canada",
        "",
        [
            {
                "field": "tuition",
                "value": "CAD 43,000 per year (2026)",
                "source_domain": "uwaterloo.ca",
            },
            {"field": "duration", "value": "2 years", "source_domain": "uwaterloo.ca"},
            {
                "field": "scholarships",
                "value": "President's Graduate Scholarship offers up to CAD "
                "10,000 for students holding a Tri-Agency award",
                "source_domain": "uwaterloo.ca",
            },
            {
                "field": "assistantship_evidence",
                "value": "Graduate TA positions are available in the school "
                "each term",
                "source_domain": "uwaterloo.ca",
            },
        ],
        context,
    )
    return context


def test_the_breakdown_reads_stored_evidence_only() -> None:
    context = researched_context()
    result = build_cost_breakdown(context)
    assert result["status"] == "success"
    university = result["universities"][0]
    tuition = next(
        c for c in university["components"] if c["component"] == "tuition"
    )
    assert tuition["source_domain"] == "uwaterloo.ca"
    assert tuition["retrieved_at"]


def test_no_financial_evidence_is_an_honest_error() -> None:
    context = StubToolContext()
    context.state[STATE_PROFILE] = profiled().model_dump()
    result = build_cost_breakdown(context)
    assert result["status"] == "error"
    assert result["reason"] == "no_financial_evidence"


def test_scholarships_are_possibilities_never_promises() -> None:
    context = researched_context()
    result = get_funding_options(context)
    rendered = str(result).casefold()
    assert "you will receive" not in rendered
    assert "guaranteed" not in rendered
    scholarship = result["scholarships"][0]
    assert scholarship["source_domain"] == "uwaterloo.ca"
    assert "eligib" in str(result["note"]).casefold()


def test_part_time_work_separates_law_from_earnings() -> None:
    context = researched_context()
    stub_evidence(context, "canada.ca", "work off campus up to 24 hours per week")
    save_finance_research(
        "country",
        "Canada",
        [
            {
                "field": "part_time_work_rules",
                "value": "up to 24 hours per week off campus",
                "source_domain": "canada.ca",
            }
        ],
        context,
    )
    result = get_funding_options(context)
    work = result["part_time_work"]
    assert work["legal_limit"]["source_domain"] == "canada.ca"
    assert work["expected_earnings"]["status"] == "unknown"
    assert "tuition" in work["note"].casefold()  # never assumed tuition funding


def test_no_funding_evidence_is_an_honest_error() -> None:
    context = StubToolContext()
    context.state[STATE_PROFILE] = profiled().model_dump()
    result = get_funding_options(context)
    assert result["status"] == "error"
    assert result["reason"] == "no_funding_evidence"


def test_the_planner_tool_reads_the_session() -> None:
    context = researched_context()
    result = plan_financial_research("Can I afford this program?", context)
    assert result["status"] == "success"
    assert "budget_fit" in result["plan"]["intents"]
    # Budget already stored — the planner must not re-ask for it.
    next_question = result["plan"]["next_question"]
    assert next_question is None or next_question["path"] != "preferences.budget"


# --- Nothing static, nothing invented (§3, §40) ------------------------------


def test_finance_fields_are_a_closed_set() -> None:
    with pytest.raises(ValueError):
        FinanceRecord.model_validate(
            {
                "scope_level": "city",
                "scope_name": "Toronto",
                "facts": {
                    "made_up_cost": {
                        "value": "x",
                        "evidence": {"source_domain": "a.b"},
                    }
                },
            }
        )
    assert "living_cost" in FINANCE_FIELDS
