"""Live calculation scenario (§32 scenario 4) — the root must not do math.

A purely mathematical question through the live model: the EMI must come
from the deterministic tool, and the exact figure the tool computed must be
the one the student is told. No research is needed or expected.
"""

from __future__ import annotations

import pytest
from google.adk.runners import InMemoryRunner
from google.genai import types

from app.agent import root_agent
from app.calc.finance import loan_emi

APP_NAME = "msbuddy"

EXPECTED = loan_emi(3_000_000, 9.0, 7)  # ₹30L @ 9% for 7 years


@pytest.fixture(scope="module")
def turn(live_model: None) -> dict:
    runner = InMemoryRunner(agent=root_agent, app_name=APP_NAME)
    session = runner.session_service.create_session_sync(
        app_name=APP_NAME, user_id="live-calc"
    )
    tool_calls: list[str] = []
    texts: list[str] = []
    for event in runner.run(
        user_id="live-calc",
        session_id=session.id,
        new_message=types.Content(
            role="user",
            parts=[
                types.Part.from_text(
                    text="If I borrow 3000000 rupees at 9% interest for 7 "
                    "years, what would my monthly EMI be?"
                )
            ],
        ),
    ):
        for part in getattr(event.content, "parts", None) or []:
            if getattr(part, "function_call", None):
                tool_calls.append(part.function_call.name)
            if getattr(part, "text", None) and not getattr(event, "partial", False):
                texts.append(part.text)
    return {"tool_calls": tool_calls, "text": " ".join(texts)}


def test_the_emi_tool_is_called_not_head_math(turn: dict) -> None:
    assert "calculate_loan_emi" in turn["tool_calls"]


def test_the_answer_carries_the_tools_exact_figure(turn: dict) -> None:
    # 48267.23 — accept common thousand-separator renderings of it.
    normalized = turn["text"].replace(",", "")
    assert "48267" in normalized, turn["text"][:300]
