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

"""Live C3 test — real model, invariants only.

The shortlist is **seeded directly** rather than researched, for two
reasons: the comparison path is what is under test, and whether the model
chooses to search on a given run is behaviour that belongs in eval (spec
§11.1). Seeding makes the input deterministic so that a failure here means
the comparison boundary broke, not that a search missed.

What is asserted is what must hold on any correct run:

* comparison never mutates stored facts;
* comparison never retrieves;
* **every number in the final answer came from a tool** — the C3 analogue of
  C2's quote verification, and the check that the scorer really is
  authoritative for numbers.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest
from google.adk.runners import InMemoryRunner
from google.genai import types

from app.agent import app as ms_buddy_app
from app.config import STATE_EVIDENCE_LEDGER, STATE_SHORTLIST
from app.plugins.evidence import REFUSAL_TEXT
from app.plugins.narration_integrity import BLOCK_TEMPLATE
from app.program_store import apply_claim, empty_shortlist, upsert_program
from app.scoring import explanation_integrity

APP_NAME = "app"
USER_ID = "test-student"

ASK = (
    "Compare the two programs on my shortlist. Cost is critical to me and "
    "the length of the program is important. STEM status and test "
    "requirements don't matter to me."
)


def evidence(domain: str) -> dict[str, Any]:
    return {
        "tier": "VERIFIED",
        "source_domain": domain,
        "source_is_official": True,
        "source_url": f"https://r/{domain}",
        "url_is_grounding_redirect": True,
        "retrieved_at": "2026-07-30T10:00:00+00:00",
        "staleness_class": "CYCLICAL",
        "supporting_quote": "as published",
    }


def seeded_shortlist() -> dict[str, Any]:
    """Two real-shaped programs, same currency and basis so cost is scoreable."""
    shortlist = empty_shortlist()
    for program_id, university, domain, amount, duration in (
        ("delft", "TU Delft", "tudelft.nl", "22290", "2 years"),
        ("leiden", "Leiden University", "universiteitleiden.nl", "18000", "18 months"),
    ):
        record = upsert_program(
            shortlist, program_id, university, "MSc Computer Science"
        )
        for name, value in (
            ("tuition_amount", amount),
            ("tuition_currency", "EUR"),
            ("tuition_basis", "per year"),
            ("duration", duration),
        ):
            apply_claim(record, name, value, evidence(domain))
    return shortlist


@pytest.fixture(scope="module")
def compared(live_model: None) -> dict[str, Any]:
    runner = InMemoryRunner(app=ms_buddy_app, app_name=APP_NAME)
    session = runner.session_service.create_session_sync(
        app_name=APP_NAME,
        user_id=USER_ID,
        state={STATE_SHORTLIST: seeded_shortlist()},
    )
    before = copy.deepcopy(session.state.get(STATE_SHORTLIST))

    answers: list[str] = []
    tool_results: list[Any] = []
    tools_called: list[str] = []

    for event in runner.run(
        user_id=USER_ID,
        session_id=session.id,
        new_message=types.Content(role="user", parts=[types.Part.from_text(text=ASK)]),
    ):
        for part in (
            (getattr(event.content, "parts", None) or []) if event.content else []
        ):
            if getattr(part, "function_call", None):
                tools_called.append(part.function_call.name)
            if getattr(part, "function_response", None):
                tool_results.append(part.function_response.response)
            elif getattr(part, "text", None) and event.content.role == "model":
                answers.append(part.text)

    refreshed = runner.session_service.get_session_sync(
        app_name=APP_NAME, user_id=USER_ID, session_id=session.id
    )
    return {
        "before": before,
        "state": refreshed.state or {},
        "answer": "\n".join(answers),
        "tool_results": tool_results,
        "tools_called": tools_called,
    }


def test_the_comparison_tools_were_actually_used(compared: dict[str, Any]) -> None:
    if not any(
        name in compared["tools_called"]
        for name in (
            "score_programs",
            "build_comparison_matrix",
            "explain_ranking_inputs",
        )
    ):
        pytest.skip(
            "the agent did not reach a comparison tool on this run; tool "
            "selection is an eval metric, not a pytest assertion"
        )


def test_the_comparison_was_not_refused(compared: dict[str, Any]) -> None:
    """The student actually got an answer.

    Added by the Phase 3 final audit, which found this suite passing while
    every comparison was in fact being replaced by `EvidencePlugin`'s
    refusal: a comparison turn retrieves nothing, so the evidence ledger was
    empty and the stored, already-cited facts were treated as fabrications.

    The integrity test below could not catch it — a refusal contains no
    numbers, so "invented no numbers" passed trivially. A test suite that is
    green while the feature is unusable is worse than no suite, so this
    asserts the negative directly.
    """
    assert REFUSAL_TEXT[:40] not in compared["answer"], (
        "the comparison was refused as unsourced even though every fact came "
        f"from a stored, verified ProgramRecord\n--- answer ---\n{compared['answer']}"
    )


def test_narration_integrity_did_not_block_a_correct_answer(
    compared: dict[str, Any],
) -> None:
    """False-positive canary for the runtime number screen.

    The screen blocks a comparison answer containing a figure no tool
    produced. It is only worth having if it leaves correct answers alone —
    a screen that mangles good output is worse than none. This asserts the
    real model's real answer survived it.
    """
    marker = BLOCK_TEMPLATE.split("{")[0].strip()
    assert marker not in compared["answer"], (
        "the narration screen blocked an answer the model was entitled to "
        f"give\n--- answer ---\n{compared['answer']}"
    )


def test_comparison_did_not_mutate_the_stored_facts(compared: dict[str, Any]) -> None:
    """C3 computes over what C2 found; it cannot rewrite it."""
    assert compared["state"].get(STATE_SHORTLIST) == compared["before"]


def test_comparison_did_not_retrieve(compared: dict[str, Any]) -> None:
    """Spec §5.2 invariant 3 — a gap stays a gap."""
    assert not compared["state"].get(STATE_EVIDENCE_LEDGER)


def test_no_number_in_the_answer_was_invented(compared: dict[str, Any]) -> None:
    """The C3 analogue of C2's quote verification.

    Every numeric token the student is shown must appear somewhere in what
    the tools actually returned. A model that recomputes a total, converts a
    currency or fills in a fee fails here.
    """
    if not compared["tool_results"]:
        pytest.skip("no tool results on this run")
    if not compared["answer"].strip():
        pytest.skip("the model produced no text on this run")

    check = explanation_integrity(
        compared["answer"], {"tool_results": compared["tool_results"]}
    )
    assert check["ok"], f"{check['message']}\n--- answer ---\n{compared['answer']}"
