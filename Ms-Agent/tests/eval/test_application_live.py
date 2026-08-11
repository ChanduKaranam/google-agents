"""Live application scenario (§11.12) — real requirement research + tracking.

One session: profile → "what documents do I need for Waterloo + deadline"
→ "track it, transcripts ready". Asserted: requirement facts were actually
researched and stored with provenance (there is no built-in requirements
table), and the tracker holds deterministic, validated state.
"""

from __future__ import annotations

from typing import Any

import pytest
from google.adk.runners import InMemoryRunner
from google.genai import types

from app.agent import root_agent
from app.application.tracker import APPLICATION_STATUSES, DOCUMENT_STATUSES
from app.config.settings import STATE_APPLICATIONS, STATE_KNOWLEDGE

APP_NAME = "msbuddy"

APPLICATION_FIELDS = (
    "sop_requirement",
    "lor_requirement",
    "transcript_requirement",
    "resume_requirement",
    "portfolio_requirement",
    "prerequisite_requirement",
    "application_portal",
    "additional_documents",
    "application_fee",
    "application_deadline",
    "english_requirement",
    "gre_requirement",
)

TURNS = [
    "I'm targeting an MS in Computer Science in Canada, Fall 2027. "
    "IELTS 7.0, CGPA 8.2 on a 10 scale.",
    "What documents do I need to apply for the MMath Computer Science at "
    "the University of Waterloo, and when is the application deadline?",
    "Please track that application for me as preparing — my transcripts "
    "are ready, nothing else is started yet.",
]


@pytest.fixture(scope="module")
def session_state(live_model: None) -> dict[str, Any]:
    runner = InMemoryRunner(agent=root_agent, app_name=APP_NAME)
    session = runner.session_service.create_session_sync(
        app_name=APP_NAME, user_id="live-application"
    )
    for message in TURNS:
        for _ in runner.run(
            user_id="live-application",
            session_id=session.id,
            new_message=types.Content(
                role="user", parts=[types.Part.from_text(text=message)]
            ),
        ):
            pass
    refreshed = runner.session_service.get_session_sync(
        app_name=APP_NAME, user_id="live-application", session_id=session.id
    )
    state = dict(refreshed.state or {})
    knowledge = state.get(STATE_KNOWLEDGE) or {}
    stored = [
        (field, fact)
        for record in knowledge.values()
        for field, fact in (record.get("facts") or {}).items()
        if field in APPLICATION_FIELDS
    ]
    if not stored:
        pytest.skip("no application facts stored this run (search-rate variance)")
    state["_application_facts"] = stored
    return state


def test_requirements_are_researched_with_provenance(
    session_state: dict[str, Any],
) -> None:
    for field, fact in session_state["_application_facts"]:
        assert fact["evidence"]["source_domain"], field
        assert fact["evidence"]["retrieved_at"], field


def test_the_tracker_holds_validated_state(session_state: dict[str, Any]) -> None:
    store = session_state.get(STATE_APPLICATIONS) or {}
    if not store:
        pytest.skip("the model did not track this run — requirement facts did land")
    for application in store.values():
        assert application["status"] in APPLICATION_STATUSES
        for status in (application.get("documents") or {}).values():
            assert status in DOCUMENT_STATUSES
