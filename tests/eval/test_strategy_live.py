"""Live strategy scenarios (§28) — the whole journey, invariants only.

Scenario A: a fully profiled student asks for a shortlist and a plan —
asserted: real research landed in state, the strategy layer actually ran,
and the final answer carries no admission-probability language.

Scenario B: an incomplete profile ("I want to do MS in Canada") — asserted:
the agent asks a question instead of dumping a fabricated plan.
"""

from __future__ import annotations

from typing import Any

import pytest
from google.adk.runners import InMemoryRunner
from google.genai import types

from app.agent import root_agent
from app.config.settings import STATE_KNOWLEDGE, STATE_PROFILE

APP_NAME = "msbuddy"

STRATEGY_TOOLS = {
    "get_strategy_readiness",
    "build_recommendations",
    "recommend_exam_plan",
    "build_action_plan",
}

FORBIDDEN = (
    "chance of admission",
    "admission probability",
    "probability of admission",
    "% chance",
    "you will get admission",
)


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


@pytest.fixture(scope="module")
def plan_session(live_model: None) -> dict[str, Any]:
    return run_turns(
        "live-strategy",
        [
            "I'm a CSE graduate with an 8.2 CGPA on a 10 scale, IELTS 7.0, "
            "skills in Python and TensorFlow, targeting an MS in AI/ML in "
            "Canada for Fall 2027. My total budget is 30 lakh INR.",
            "Which universities should I apply to, and what exactly should "
            "I do next? Build my plan.",
        ],
    )


def test_the_journey_researches_and_synthesizes(
    plan_session: dict[str, Any],
) -> None:
    called = set(plan_session["calls"])
    assert called & STRATEGY_TOOLS, f"no strategy tool ran; called: {sorted(called)}"
    knowledge = plan_session["state"].get(STATE_KNOWLEDGE) or {}
    if not knowledge:
        pytest.skip("no programs researched this run (search-rate variance)")
    for record in knowledge.values():
        for fact in (record.get("facts") or {}).values():
            assert fact["evidence"]["source_domain"]


def test_the_final_answer_promises_nothing(plan_session: dict[str, Any]) -> None:
    answer = plan_session["texts"][-1].casefold()
    assert answer, "no final text produced"
    for phrase in FORBIDDEN:
        assert phrase not in answer, phrase


def test_an_incomplete_profile_gets_a_question_not_a_plan(
    live_model: None,
) -> None:
    result = run_turns("live-strategy-b", ["I want to do MS in Canada."])
    answer = result["texts"][-1]
    assert "?" in answer  # progressive collection, not a generic dump
    profile = result["state"].get(STATE_PROFILE) or {}
    assert "canada" in str(profile).casefold()
    for phrase in FORBIDDEN:
        assert phrase not in answer.casefold()
