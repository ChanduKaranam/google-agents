# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Live proof that greetings are conversations, not tool invocations.

The structural half lives in `test_general_conversation.py`; this file runs
the real model and asserts behaviour: a greeting turn calls **zero** tools,
produces a non-empty answer, and never surfaces the "from memory" refusal
that identity questions used to hit (observed live 2026-08-07).

One session, three turns, so the whole file costs three model calls and no
search. Assertions are invariants, not phrasing: what the model says is
style, that it says something and touches nothing is the contract.
"""

from __future__ import annotations

from typing import Any

import pytest
from google.adk.runners import InMemoryRunner
from google.genai import types

from app.agent import app as ms_buddy_app

APP_NAME = "app"

GREETINGS = ["Hello", "Who are you?", "What can you do?"]


@pytest.fixture(scope="module")
def turns(live_model: None) -> list[dict[str, Any]]:
    """One live session; returns per-turn tool calls and final text."""
    runner = InMemoryRunner(app=ms_buddy_app, app_name=APP_NAME)
    session = runner.session_service.create_session_sync(
        app_name=APP_NAME, user_id="live-greetings"
    )
    collected: list[dict[str, Any]] = []
    for message in GREETINGS:
        tool_calls: list[str] = []
        texts: list[str] = []
        for event in runner.run(
            user_id="live-greetings",
            session_id=session.id,
            new_message=types.Content(
                role="user", parts=[types.Part.from_text(text=message)]
            ),
        ):
            for part in getattr(event.content, "parts", None) or []:
                if getattr(part, "function_call", None):
                    tool_calls.append(part.function_call.name)
                if getattr(part, "text", None) and not getattr(event, "partial", False):
                    texts.append(part.text)
        collected.append(
            {"message": message, "tool_calls": tool_calls, "text": " ".join(texts)}
        )
    return collected


def test_every_greeting_gets_an_answer(turns: list[dict[str, Any]]) -> None:
    for turn in turns:
        assert turn["text"].strip(), f"{turn['message']!r} got an empty reply"


def test_no_greeting_calls_any_tool(turns: list[dict[str, Any]]) -> None:
    for turn in turns:
        assert turn["tool_calls"] == [], (
            f"{turn['message']!r} called {turn['tool_calls']} — a greeting "
            "is a conversation, not a task"
        )


def test_identity_questions_are_not_refused_as_memory(
    turns: list[dict[str, Any]],
) -> None:
    """The exact live failure this work fixed."""
    for turn in turns:
        assert "from memory" not in turn["text"].lower(), (
            f"{turn['message']!r} was refused as a memory question: "
            f"{turn['text'][:120]!r}"
        )


def test_no_internal_machinery_is_exposed(turns: list[dict[str, Any]]) -> None:
    for turn in turns:
        lowered = turn["text"].lower()
        for leak in ("root_agent", "agenttool", "delegat", "orchestrat"):
            assert leak not in lowered, f"{turn['message']!r} leaked {leak!r}"
