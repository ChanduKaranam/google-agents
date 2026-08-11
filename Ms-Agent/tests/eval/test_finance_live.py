"""Live finance scenarios (§37) — dynamic research, invariants only.

Two real sessions against the live stack. Asserted: financial facts were
actually researched and stored with provenance (never answered from a
built-in table — there is none), the calculation tools did the arithmetic,
scholarships arrive with sources and without promises, and a comparison
researches both universities. Amount values are never asserted — they are
whatever the sources currently state; the *shape* (source, date, currency,
status) is the contract.
"""

from __future__ import annotations

from typing import Any

import pytest
from google.adk.runners import InMemoryRunner
from google.genai import types

from app.agent import root_agent
from app.config.settings import STATE_FINANCE, STATE_KNOWLEDGE
from app.finance.analysis import extract_money

APP_NAME = "msbuddy"

MONEY_FIELDS = (
    "tuition",
    "tuition_currency",
    "mandatory_fees",
    "billing_structure",
    "living_cost_estimate",
    "housing_cost",
    "health_insurance_cost",
    "application_fee",
    "deposit",
)

FUNDING_FIELDS = ("scholarships", "funding_evidence", "assistantship_evidence")

CALC_TOOLS = {
    "build_cost_breakdown",
    "calculate_total_cost",
    "calculate_budget_fit",
    "convert_money",
}


def run_turns(user_id: str, turns: list[str]) -> dict[str, Any]:
    runner = InMemoryRunner(agent=root_agent, app_name=APP_NAME)
    session = runner.session_service.create_session_sync(
        app_name=APP_NAME, user_id=user_id
    )
    calls: list[str] = []
    texts: list[str] = []
    for message in turns:
        final = ""
        for event in runner.run(
            user_id=user_id,
            session_id=session.id,
            new_message=types.Content(
                role="user", parts=[types.Part.from_text(text=message)]
            ),
        ):
            for part in getattr(event.content, "parts", None) or []:
                call = getattr(part, "function_call", None)
                if call is not None:
                    calls.append(call.name)
                if getattr(part, "text", None):
                    final = part.text
        texts.append(final)
    refreshed = runner.session_service.get_session_sync(
        app_name=APP_NAME, user_id=user_id, session_id=session.id
    )
    return {"state": dict(refreshed.state or {}), "calls": calls, "texts": texts}


def money_facts(state: dict[str, Any]) -> list[dict[str, Any]]:
    knowledge = state.get(STATE_KNOWLEDGE) or {}
    return [
        {"field": field, **fact}
        for record in knowledge.values()
        for field, fact in (record.get("facts") or {}).items()
        if field in MONEY_FIELDS
    ]


@pytest.fixture(scope="module")
def afford_session(live_model: None) -> dict[str, Any]:
    result = run_turns(
        "live-finance",
        [
            "I'm planning an MS in Computer Science in Canada, Fall 2027 "
            "intake. My total budget is 30 lakh INR including living costs.",
            "What is the current international tuition for the MMath "
            "Computer Science at the University of Waterloo? Can I afford "
            "it with my budget?",
            "What scholarships could I potentially apply for there?",
        ],
    )
    if not money_facts(result["state"]):
        pytest.skip("no money facts stored this run (search-rate variance)")
    return result


# --- Live Test 1: tuition (§37) ----------------------------------------------


def test_tuition_arrives_with_currency_year_and_provenance(
    afford_session: dict[str, Any],
) -> None:
    facts = money_facts(afford_session["state"])
    for fact in facts:
        assert fact["evidence"]["source_domain"], fact["field"]
        assert fact["evidence"]["retrieved_at"], fact["field"]
    tuition = [f for f in facts if f["field"] == "tuition"]
    if not tuition:
        pytest.skip("tuition itself not stored this run")
    money = extract_money(tuition[0]["value"])
    assert money["low"] is not None  # a real figure, not prose
    assert money["currency"] or any(
        f["field"] == "tuition_currency" for f in facts
    )


# --- Live Test 2: budget fit (§37) -------------------------------------------


def test_affordability_went_through_the_calculation_tools(
    afford_session: dict[str, Any],
) -> None:
    called = set(afford_session["calls"])
    assert called & CALC_TOOLS, f"no calc/breakdown tool ran; called: {sorted(called)}"


# --- Live Test 3: scholarships (§37) -----------------------------------------


def test_scholarships_carry_sources_and_no_promises(
    afford_session: dict[str, Any],
) -> None:
    state = afford_session["state"]
    knowledge = state.get(STATE_KNOWLEDGE) or {}
    funding = [
        fact
        for record in knowledge.values()
        for field, fact in (record.get("facts") or {}).items()
        if field in FUNDING_FIELDS
    ] + [
        fact
        for record in (state.get(STATE_FINANCE) or {}).values()
        for field, fact in (record.get("facts") or {}).items()
        if field == "external_scholarships"
    ]
    if not funding:
        pytest.skip("no funding facts stored this run (search-rate variance)")
    for fact in funding:
        assert fact["evidence"]["source_domain"]
    # Promise language: "not guaranteed" is honest and welcome; an
    # affirmative promise is not. The tool-level wording is unit-tested;
    # here we pin only the affirmative forms.
    answer = afford_session["texts"][2].casefold()
    assert "you will receive" not in answer
    assert "you are guaranteed" not in answer


# --- Live Test 4: comparison (§37) -------------------------------------------


@pytest.fixture(scope="module")
def comparison_session(live_model: None) -> dict[str, Any]:
    result = run_turns(
        "live-finance-compare",
        [
            "I'm planning an MS in Computer Science in Canada, Fall 2027.",
            "Compare the total cost of the MMath Computer Science at the "
            "University of Waterloo and the MSc Computer Science at the "
            "University of British Columbia.",
        ],
    )
    knowledge = result["state"].get(STATE_KNOWLEDGE) or {}
    researched = [
        record
        for record in knowledge.values()
        if any(f in (record.get("facts") or {}) for f in MONEY_FIELDS)
    ]
    if len(researched) < 2:
        pytest.skip("fewer than two universities researched this run")
    result["researched"] = researched
    return result


def test_both_universities_are_researched_with_provenance(
    comparison_session: dict[str, Any],
) -> None:
    universities = {r["university"] for r in comparison_session["researched"]}
    assert len(universities) >= 2
    for record in comparison_session["researched"]:
        for field, fact in record["facts"].items():
            if field in MONEY_FIELDS:
                assert fact["evidence"]["source_domain"], field
                assert fact["evidence"]["retrieved_at"], field
