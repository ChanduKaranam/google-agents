"""Live scenarios — real model, invariants only.

These run only when a model backend is configured (see conftest). They
assert what must hold on any correct run — tool choices, state effects,
no fabrication — never exact wording, which is an eval concern, not a
pytest one.
"""

from __future__ import annotations

from typing import Any

import pytest
from google.adk.runners import InMemoryRunner
from google.genai import types

from app.agent import root_agent
from app.config.settings import STATE_KNOWLEDGE, STATE_PROFILE

APP_NAME = "msbuddy"


class Conversation:
    def __init__(self, user_id: str) -> None:
        self.runner = InMemoryRunner(agent=root_agent, app_name=APP_NAME)
        self.user_id = user_id
        self.session = self.runner.session_service.create_session_sync(
            app_name=APP_NAME, user_id=user_id
        )
        self.tool_calls: list[str] = []
        self.texts: list[str] = []

    def say(self, message: str) -> None:
        for event in self.runner.run(
            user_id=self.user_id,
            session_id=self.session.id,
            new_message=types.Content(
                role="user", parts=[types.Part.from_text(text=message)]
            ),
        ):
            for part in getattr(event.content, "parts", None) or []:
                if getattr(part, "function_call", None):
                    self.tool_calls.append(part.function_call.name)
                if getattr(part, "text", None) and not getattr(event, "partial", False):
                    self.texts.append(part.text)

    def state(self) -> dict[str, Any]:
        refreshed = self.runner.session_service.get_session_sync(
            app_name=APP_NAME, user_id=self.user_id, session_id=self.session.id
        )
        return dict(refreshed.state or {})


def test_greetings_call_no_tools_and_are_not_refused(live_model: None) -> None:
    chat = Conversation("live-greeting")
    chat.say("Hello")
    chat.say("What can you do?")
    assert chat.tool_calls == []
    text = " ".join(chat.texts).lower()
    assert text.strip()
    assert "from memory" not in text


def test_scenario_1_profile_lands_in_state(live_model: None) -> None:
    chat = Conversation("live-profile")
    chat.say("I'm a CSE graduate from Lendi with 8.2 CGPA. I want MS in Canada.")
    profile = chat.state().get(STATE_PROFILE) or {}
    education = profile.get("education") or {}
    target = profile.get("target") or {}
    assert education.get("cgpa") == 8.2
    assert (target.get("country") or "").lower() == "canada"
    # And nothing was invented alongside.
    assert profile.get("test_scores", {}).get("ielts") is None


def test_scenario_4_recommendation_pipeline_stores_graded_facts(
    live_model: None,
) -> None:
    chat = Conversation("live-recommend")
    chat.say(
        "I'm a CSE graduate with 8.2 CGPA out of 10, IELTS 7.5, targeting "
        "an MS in Computer Science in Canada for Fall 2027."
    )
    chat.say(
        "Research the MSc in Computer Science at the University of Toronto "
        "and tell me how well I fit."
    )
    state = chat.state()
    knowledge = state.get(STATE_KNOWLEDGE) or {}
    if not knowledge:
        pytest.skip("research stored nothing this run (search rate is an eval metric)")
    for program in knowledge.values():
        for fact in (program.get("facts") or {}).values():
            assert fact["status"] in ("verified", "partially_verified", "unverified")
            assert fact["evidence"]["source_domain"]
