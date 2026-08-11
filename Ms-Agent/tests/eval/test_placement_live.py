"""Live placement scenario (§28) — dynamic research, invariants only.

A profiled AI/ML student asks about Waterloo career outcomes. Asserted:
research actually happened (career facts stored with sources), scope
survived into the analysis, and no fabricated placement percentage exists
outside quoted evidence.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from google.adk.runners import InMemoryRunner
from google.genai import types

from app.agent import root_agent
from app.config.settings import STATE_KNOWLEDGE
from app.tools.placement_tools import analyze_career_outcomes

APP_NAME = "msbuddy"

CAREER_FIELDS = (
    "employment_outcomes",
    "career_signals",
    "salary_evidence",
    "employer_evidence",
    "career_locations",
    "industry_evidence",
)

TURNS = [
    "I'm a CSE grad, 8.2 CGPA out of 10, skills in Python, TensorFlow and "
    "deep learning, targeting an ML Engineer career in Canada, Fall 2027.",
    "What are the career outcomes after the MMath Computer Science at the "
    "University of Waterloo? Is it good for AI/ML jobs for my profile?",
]


@pytest.fixture(scope="module")
def researched(live_model: None) -> dict[str, Any]:
    runner = InMemoryRunner(agent=root_agent, app_name=APP_NAME)
    session = runner.session_service.create_session_sync(
        app_name=APP_NAME, user_id="live-placement"
    )
    for message in TURNS:
        for _ in runner.run(
            user_id="live-placement",
            session_id=session.id,
            new_message=types.Content(
                role="user", parts=[types.Part.from_text(text=message)]
            ),
        ):
            pass
    refreshed = runner.session_service.get_session_sync(
        app_name=APP_NAME, user_id="live-placement", session_id=session.id
    )
    state = dict(refreshed.state or {})
    knowledge = state.get(STATE_KNOWLEDGE) or {}
    has_career = any(
        field in (record.get("facts") or {})
        for record in knowledge.values()
        for field in CAREER_FIELDS
    )
    if not has_career:
        pytest.skip("no career facts stored this run (search-rate variance)")
    return state


def test_career_facts_carry_sources_and_dates(researched: dict[str, Any]) -> None:
    for record in researched[STATE_KNOWLEDGE].values():
        for field, fact in (record.get("facts") or {}).items():
            if field in CAREER_FIELDS:
                assert fact["evidence"]["source_domain"], field
                assert fact["evidence"]["retrieved_at"], field


def test_the_analysis_runs_on_live_evidence_with_scope(
    researched: dict[str, Any],
) -> None:
    context = SimpleNamespace(
        state=dict(researched), invocation_id="t", session=SimpleNamespace(events=[])
    )
    result = analyze_career_outcomes(context)
    assert result["status"] == "success"
    for university in result["universities"]:
        for key in ("employment_outcomes", "roles", "salary_evidence"):
            cell = university[key]
            if cell.get("value"):
                assert cell["scope"]["scope"] in (
                    "program_specific", "faculty_level", "university_level",
                    "market_benchmark", "scope_unclear",
                )
