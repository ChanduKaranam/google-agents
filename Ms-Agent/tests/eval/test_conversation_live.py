"""Live conversational-intelligence scenario (refactor §19K/§20).

The exact reported failure, reproduced with stale history SEEDED: the
stored profile says major = "Computer Science and Systems Engineering"
(from an old resume), and the student now says "I'm a CSE grad, 8.2 CGPA,
IELTS 7.0, targeting AI/ML in Canada, Fall 2027, budget 30 lakh. Which
universities should I apply to and what should I do next?"

Asserted: no reconciliation question, no re-asking of supplied facts, the
current statement supersedes history in state, and the agent routes to
research/strategy instead of restarting profile collection.
"""

from __future__ import annotations

from typing import Any

import pytest
from google.adk.runners import InMemoryRunner
from google.genai import types

from app.agent import root_agent
from app.config.settings import STATE_PROFILE, STATE_PROFILE_META
from app.models.student import StudentProfile

APP_NAME = "msbuddy"

OLD_MAJOR = "Computer Science and Systems Engineering"

FORBIDDEN_QUESTIONS = (
    "which should i use",
    "which one should i use",
    "or your old resume",
    "your resume says",
    "what is your cgpa",
    "what's your cgpa",
    "which country",
    "what country",
    "what is your budget",
    "what's your budget",
    "what ielts",
    "your ielts score?",
    "which intake",
    "what field are you",
)

ACTION_TOOLS = {
    "research_agent",
    "get_strategy_readiness",
    "build_recommendations",
    "build_action_plan",
    "match_programs",
    "plan_financial_research",
    "get_programs",
}

MESSAGE = (
    "I'm a CSE grad, 8.2 CGPA, IELTS 7.0, targeting AI/ML in Canada, "
    "Fall 2027, budget 30 lakh. Which universities should I apply to and "
    "what should I do next?"
)


@pytest.fixture(scope="module")
def stale_history_session(live_model: None) -> dict[str, Any]:
    runner = InMemoryRunner(agent=root_agent, app_name=APP_NAME)
    seeded_profile = StudentProfile.model_validate(
        {"education": {"major": OLD_MAJOR, "degree": "Bachelor's"}}
    )
    session = runner.session_service.create_session_sync(
        app_name=APP_NAME,
        user_id="live-conversation",
        state={
            STATE_PROFILE: seeded_profile.model_dump(),
            STATE_PROFILE_META: {
                "fields": {
                    "education.major": {
                        "source": "resume",
                        "status": "extracted",
                        "confidence": 1.0,
                    },
                    "education.degree": {
                        "source": "resume",
                        "status": "extracted",
                        "confidence": 1.0,
                    },
                },
                "inferred_domains": [],
            },
        },
    )
    calls: list[str] = []
    final = ""
    for event in runner.run(
        user_id="live-conversation",
        session_id=session.id,
        new_message=types.Content(
            role="user", parts=[types.Part.from_text(text=MESSAGE)]
        ),
    ):
        for part in getattr(event.content, "parts", None) or []:
            call = getattr(part, "function_call", None)
            if call is not None:
                calls.append(call.name)
            if getattr(part, "text", None):
                final = part.text
    refreshed = runner.session_service.get_session_sync(
        app_name=APP_NAME, user_id="live-conversation", session_id=session.id
    )
    return {
        "state": dict(refreshed.state or {}),
        "calls": calls,
        "final": final,
    }


def test_no_reconciliation_and_no_reasking(
    stale_history_session: dict[str, Any],
) -> None:
    answer = stale_history_session["final"].casefold()
    assert answer, "no final text produced"
    for phrase in FORBIDDEN_QUESTIONS:
        assert phrase not in answer, f"asked about known/superseded info: {phrase!r}"


def test_the_current_statement_supersedes_the_old_resume_value(
    stale_history_session: dict[str, Any],
) -> None:
    profile = stale_history_session["state"].get(STATE_PROFILE) or {}
    major = str(((profile.get("education") or {}).get("major")) or "")
    assert major.casefold() != OLD_MAJOR.casefold()
    assert "cse" in major.casefold() or "computer science" in major.casefold()


def test_the_turn_routes_to_action_not_profile_collection(
    stale_history_session: dict[str, Any],
) -> None:
    called = set(stale_history_session["calls"])
    assert called & ACTION_TOOLS, (
        f"no research/strategy action ran; called: {sorted(called)}"
    )
