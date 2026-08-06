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

"""Live agent tests for profile extraction and profile interaction.

**These assert invariants, not content.** Spec §11.1 forbids pytest
assertions on LLM response text because it is non-deterministic, and that
rule is respected here: nothing below asserts what the model *said*, or that
a particular value was extracted. What is asserted is what must hold for any
correct run whatsoever —

* every stored field name is on the registry allowlist;
* every stored student fact is tier `USER_STATED` and carries an evidence
  span that really appears in the student's own message;
* every derived value is tier `INFERENCE` and names its rule;
* nothing the student did not write ends up in state.

Whether the model extracted *well* is an eval question (spec §11), not a
pytest question.

Skipped automatically when no model backend is configured — see the
`live_model` fixture in `tests/conftest.py`.
"""

from __future__ import annotations

from typing import Any

import pytest
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.runners import InMemoryRunner
from google.genai import types

from app.agent import app as ms_buddy_app
from app.config import STATE_PROFILE
from app.profile_store import evidence_supports
from app.reference.profile_fields import DERIVED_FIELDS, FIELDS

APP_NAME = "app"
USER_ID = "test-student"

STUDENT_MESSAGE = (
    "Hi! I finished my BTech in Electronics with 8.1 CGPA out of 10. "
    "I scored 168 in GRE quant and 159 in verbal. I want to do a Data "
    "Science masters in Canada, starting Fall 2027."
)

# Names a two-digit intake year, which is genuinely ambiguous. The invariant
# is that ambiguity never becomes a stored guess.
AMBIGUOUS_MESSAGE = "I'm aiming for Fall 25 intake, doing my BTech in ECE right now."


def _run(message: str) -> tuple[dict[str, Any], str]:
    """Run one turn against the real root agent; return (profile, reply)."""
    runner = InMemoryRunner(app=ms_buddy_app, app_name=APP_NAME)
    session = runner.session_service.create_session_sync(
        app_name=APP_NAME, user_id=USER_ID
    )

    reply_chunks: list[str] = []
    for event in runner.run(
        user_id=USER_ID,
        session_id=session.id,
        new_message=types.Content(
            role="user", parts=[types.Part.from_text(text=message)]
        ),
        run_config=RunConfig(streaming_mode=StreamingMode.NONE),
    ):
        content = getattr(event, "content", None)
        if content is None or getattr(content, "role", None) == "user":
            continue
        for part in getattr(content, "parts", None) or []:
            if getattr(part, "text", None):
                reply_chunks.append(part.text)

    refreshed = runner.session_service.get_session_sync(
        app_name=APP_NAME, user_id=USER_ID, session_id=session.id
    )
    profile = (refreshed.state or {}).get(STATE_PROFILE) or {}
    return profile, "".join(reply_chunks)


@pytest.fixture(scope="module")
def stated_profile(live_model: None) -> dict[str, Any]:
    profile, reply = _run(STUDENT_MESSAGE)
    assert reply.strip(), "the agent produced no reply at all"
    return profile


def test_agent_records_something_from_a_detail_rich_message(
    stated_profile: dict[str, Any],
) -> None:
    """Not *what* was captured — only that the write path works end to end."""
    assert stated_profile.get("fields"), (
        "no profile fields were stored; the tool path may be broken"
    )


def test_only_allowlisted_fields_reach_state(
    stated_profile: dict[str, Any],
) -> None:
    permitted = set(FIELDS) | set(DERIVED_FIELDS)
    stored = set(stated_profile.get("fields", {}))
    assert stored <= permitted, f"unknown fields stored: {stored - permitted}"


def test_every_stored_student_fact_quotes_the_student(
    stated_profile: dict[str, Any],
) -> None:
    """The core C1 guarantee, checked against a real model's tool calls."""
    for name, entry in stated_profile.get("fields", {}).items():
        if entry["tier"] != "USER_STATED":
            continue
        span = entry.get("evidence_span")
        assert span, f"'{name}' stored with no evidence span"
        assert evidence_supports(span, STUDENT_MESSAGE), (
            f"'{name}' cites {span!r}, which is not in the student's message"
        )


def test_stored_values_are_only_user_stated_or_inference(
    stated_profile: dict[str, Any],
) -> None:
    for name, entry in stated_profile.get("fields", {}).items():
        assert entry["tier"] in ("USER_STATED", "INFERENCE"), (
            f"'{name}' has unexpected tier {entry['tier']}"
        )


def test_derived_values_name_their_rule_and_quote_nobody(
    stated_profile: dict[str, Any],
) -> None:
    for name, entry in stated_profile.get("fields", {}).items():
        if entry["tier"] != "INFERENCE":
            continue
        assert name in DERIVED_FIELDS, f"'{name}' is inference but not a derived field"
        assert entry["rule_id"], f"'{name}' is inference with no rule id"
        assert entry["evidence_span"] is None


def test_ambiguous_intake_year_is_never_stored_as_a_guess(
    live_model: None,
) -> None:
    """ "Fall 25" must produce a question, not a fabricated four-digit year."""
    profile, reply = _run(AMBIGUOUS_MESSAGE)
    assert reply.strip()
    stored_year = profile.get("fields", {}).get("target_intake_year")
    assert stored_year is None, (
        f"a year was invented from an ambiguous message: {stored_year}"
    )
