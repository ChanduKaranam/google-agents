"""Live exams scenario — real research, invariants only (§27-28).

Scenario 1+3 combined: a GRE question for a specific program, then a
"is my IELTS enough?" follow-up. Asserted are the facts and evidence
structure, never wording: requirement facts land in the knowledge store
with sources, and the deterministic checker produces statuses from the
six-value enum with evidence trails.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from google.adk.runners import InMemoryRunner
from google.genai import types

from app.agent import root_agent
from app.config.settings import STATE_KNOWLEDGE
from app.exams.requirements import REQUIREMENT_STATUSES
from app.tools.exam_tools import check_exam_requirements

APP_NAME = "msbuddy"

TURNS = [
    "I have IELTS 7.0 and I'm applying for Fall 2027.",
    "Do I need the GRE for the MSc in Computer Science at the University "
    "of Toronto? And is my IELTS enough for it?",
]


@pytest.fixture(scope="module")
def researched(live_model: None) -> dict[str, Any]:
    runner = InMemoryRunner(agent=root_agent, app_name=APP_NAME)
    session = runner.session_service.create_session_sync(
        app_name=APP_NAME, user_id="live-exams"
    )
    for message in TURNS:
        for _ in runner.run(
            user_id="live-exams",
            session_id=session.id,
            new_message=types.Content(
                role="user", parts=[types.Part.from_text(text=message)]
            ),
        ):
            pass
    refreshed = runner.session_service.get_session_sync(
        app_name=APP_NAME, user_id="live-exams", session_id=session.id
    )
    state = dict(refreshed.state or {})
    if not (state.get(STATE_KNOWLEDGE) or {}):
        pytest.skip(
            "research stored nothing this run (search rate is an eval "
            "metric, not an invariant)"
        )
    return state


def test_exam_facts_land_with_evidence(researched: dict[str, Any]) -> None:
    knowledge = researched[STATE_KNOWLEDGE]
    exam_fields = [
        (record["university"], field, fact)
        for record in knowledge.values()
        for field, fact in (record.get("facts") or {}).items()
        if field in ("english_requirement", "gre_requirement", "test_requirements")
    ]
    assert exam_fields, "no exam-requirement facts were stored"
    for university, field, fact in exam_fields:
        assert fact["evidence"]["source_domain"], (university, field)
        assert fact["evidence"]["retrieved_at"], (university, field)
        assert fact["status"] in ("verified", "partially_verified", "unverified")


def test_the_checker_interprets_stored_requirements(
    researched: dict[str, Any],
) -> None:
    context = SimpleNamespace(
        state=dict(researched), invocation_id="t", session=SimpleNamespace(events=[])
    )
    result = check_exam_requirements(context)
    assert result["status"] == "success"
    for row in result["programs"]:
        assert row["english"]["status"] in REQUIREMENT_STATUSES
        assert row["gre"]["status"] in REQUIREMENT_STATUSES
        assert "student" in row["english"]
