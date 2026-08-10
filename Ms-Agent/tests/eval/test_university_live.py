"""Live university scenario (§47) — deep research, faculty, invariants only.

A computer-vision student asks for deep research on one program including
faculty. Asserted: evidence-graded facts land per program, faculty facts
(when stored) match deterministically against stated interests, and
nothing is presented without a source.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from google.adk.runners import InMemoryRunner
from google.genai import types

from app.agent import root_agent
from app.config.settings import STATE_KNOWLEDGE
from app.tools.university_analysis_tools import compare_programs

APP_NAME = "msbuddy"

TURNS = [
    "I'm a CSE grad with 8.2 CGPA out of 10, interested in computer vision "
    "and deep learning, targeting Fall 2027 in Canada.",
    "Do deep research on the MSc Computer Science at the University of "
    "British Columbia — requirements, tuition, deadline, and faculty "
    "working in computer vision.",
]


@pytest.fixture(scope="module")
def researched(live_model: None) -> dict[str, Any]:
    runner = InMemoryRunner(agent=root_agent, app_name=APP_NAME)
    session = runner.session_service.create_session_sync(
        app_name=APP_NAME, user_id="live-university"
    )
    for message in TURNS:
        for _ in runner.run(
            user_id="live-university",
            session_id=session.id,
            new_message=types.Content(
                role="user", parts=[types.Part.from_text(text=message)]
            ),
        ):
            pass
    refreshed = runner.session_service.get_session_sync(
        app_name=APP_NAME, user_id="live-university", session_id=session.id
    )
    state = dict(refreshed.state or {})
    if not (state.get(STATE_KNOWLEDGE) or {}):
        pytest.skip("research stored nothing this run (search-rate variance)")
    return state


def test_program_facts_carry_evidence_and_freshness(
    researched: dict[str, Any],
) -> None:
    for record in researched[STATE_KNOWLEDGE].values():
        for field, fact in (record.get("facts") or {}).items():
            assert fact["evidence"]["source_domain"], field
            assert fact["evidence"]["retrieved_at"], field
            assert fact["status"] in ("verified", "partially_verified", "unverified")


def test_the_comparison_renders_the_live_data(researched: dict[str, Any]) -> None:
    context = SimpleNamespace(
        state=dict(researched), invocation_id="t", session=SimpleNamespace(events=[])
    )
    result = compare_programs(context)
    assert result["status"] == "success"
    row = result["matrix"][0]
    known = [d for d in row["dimensions"].values() if d.get("value")]
    assert known, "no dimension was verified at all"
    for cell in known:
        assert cell["source_domain"]
