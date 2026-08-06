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

"""Runtime enforcement of the C3 number boundary.

The Phase 3 audit flagged narration as the one guarantee resting on prompt
text plus a test rather than on code. These exercise the plugin that closes
it, in both directions: a fabricated figure must be caught, and a correct
answer must survive untouched. The second half matters more — a screen that
blocks good answers is worse than no screen.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from app.plugins.narration_integrity import (
    NarrationIntegrityPlugin,
    student_text,
    turn_tool_results,
)

INVOCATION = "inv-1"

SCORE_RESULT = {
    "status": "success",
    "ranking": [
        {"rank": 1, "program_id": "leiden", "total": 1.0},
        {"rank": 2, "program_id": "delft", "total": 0.0},
    ],
    "programs": [
        {
            "program_id": "leiden",
            "total": 1.0,
            "contributions": {
                "cost": {
                    "raw_value": 18000.0,
                    "published_value": "18000",
                    "weight": 4.0,
                }
            },
            "arithmetic": ["total = 6.0 / 6.0 = 1.0"],
        },
        {
            "program_id": "delft",
            "total": 0.0,
            "contributions": {
                "cost": {
                    "raw_value": 22290.0,
                    "published_value": "22290",
                    "weight": 4.0,
                }
            },
            "arithmetic": ["total = 0.0 / 6.0 = 0.0"],
        },
    ],
}


def response(text: str) -> SimpleNamespace:
    return SimpleNamespace(
        content=SimpleNamespace(role="model", parts=[SimpleNamespace(text=text)]),
        partial=False,
    )


def event(name: str, payload: Any, invocation_id: str = INVOCATION) -> SimpleNamespace:
    return SimpleNamespace(
        invocation_id=invocation_id,
        content=SimpleNamespace(
            parts=[
                SimpleNamespace(
                    function_response=SimpleNamespace(name=name, response=payload)
                )
            ]
        ),
    )


class Ctx:
    """Callback context exposing only what the plugin reads."""

    def __init__(
        self,
        events: list[Any],
        said: str = "",
        agent_name: str = "root_agent",
        invocation_id: str = INVOCATION,
    ) -> None:
        self.agent_name = agent_name
        self.invocation_id = invocation_id
        self.state: dict[str, Any] = {}
        self.user_content = (
            SimpleNamespace(role="user", parts=[SimpleNamespace(text=said)])
            if said
            else None
        )
        self._invocation = SimpleNamespace(session=SimpleNamespace(events=events))

    def get_invocation_context(self) -> Any:
        return self._invocation


def screen(ctx: Ctx, text: str) -> Any:
    return asyncio.run(
        NarrationIntegrityPlugin().after_model_callback(
            callback_context=ctx, llm_response=response(text)
        )
    )


def blocked(result: Any) -> bool:
    return result is not None


def scored_ctx(said: str = "") -> Ctx:
    return Ctx([event("score_programs", SCORE_RESULT)], said=said)


# --- It catches what it exists to catch ------------------------------------


def test_a_recomputed_total_is_blocked() -> None:
    result = screen(scored_ctx(), "Weighing it up, Delft really scores 0.72 overall.")
    assert blocked(result)
    assert "0.72" in result.content.parts[0].text


def test_an_invented_fee_is_blocked() -> None:
    result = screen(scored_ctx(), "Leiden costs about 43000 EUR per year.")
    assert blocked(result)
    assert "43000" in result.content.parts[0].text


def test_a_converted_currency_is_blocked() -> None:
    """There is no exchange rate in this system; a converted figure is invented."""
    assert blocked(screen(scored_ctx(), "That is roughly 19500 US dollars."))


def test_the_block_message_names_the_offending_figures() -> None:
    result = screen(scored_ctx(), "Delft scores 0.72 and costs 43000.")
    text = result.content.parts[0].text
    assert "0.72" in text and "43000" in text
    assert "scoring tool did not produce" in text


# --- It leaves correct answers alone ---------------------------------------


def test_a_faithful_narration_passes_untouched() -> None:
    assert (
        screen(
            scored_ctx(),
            "Leiden ranks 1 with a total of 1.0; Delft is 2 on 0.0. "
            "Leiden's tuition is 18000 against Delft's 22290.",
        )
        is None
    )


def test_a_thousands_separator_is_not_a_fabrication() -> None:
    """The formatting bug that made the first real live answer look invented."""
    assert screen(scored_ctx(), "Delft charges 22,290 per year.") is None


def test_a_rounded_or_percentage_restatement_passes() -> None:
    assert screen(scored_ctx(), "Leiden scores 100% and Delft 0%.") is None


def test_the_students_own_numbers_can_be_repeated() -> None:
    """Reading a GPA back to the student is not a fabricated comparison figure."""
    ctx = scored_ctx(said="My GPA is 8.1 and I got 168 on GRE quant.")
    assert screen(ctx, "With your 8.1 GPA and 168 quant, Leiden ranks 1.") is None


def test_the_arithmetic_can_be_relayed() -> None:
    assert screen(scored_ctx(), "The arithmetic was 6.0 / 6.0 = 1.0.") is None


# --- Scope: it does nothing outside a comparison turn ----------------------


def test_a_profile_turn_is_not_screened() -> None:
    ctx = Ctx([event("save_profile_fields", {"status": "success"})])
    assert screen(ctx, "Recorded your GPA of 8.1 and GRE 168.") is None


def test_a_research_turn_is_not_screened() -> None:
    """C2 answers are `EvidencePlugin`'s job, and the rules there differ."""
    ctx = Ctx([event("save_program_record", {"status": "success"})])
    assert screen(ctx, "The deadline is 15 December 2026 and tuition is 22290.") is None


def test_a_turn_with_no_tools_is_not_screened() -> None:
    assert (
        screen(Ctx([]), "Let's talk about what matters to you. Maybe 3 things?") is None
    )


def test_only_the_root_agents_output_is_screened() -> None:
    ctx = Ctx(
        [event("score_programs", SCORE_RESULT)], agent_name="program_research_agent"
    )
    assert screen(ctx, "Total is 0.72.") is None


def test_a_partial_streaming_chunk_is_not_screened() -> None:
    ctx = scored_ctx()
    partial = response("0.72")
    partial.partial = True
    result = asyncio.run(
        NarrationIntegrityPlugin().after_model_callback(
            callback_context=ctx, llm_response=partial
        )
    )
    assert result is None


def test_an_empty_answer_is_not_screened() -> None:
    assert screen(scored_ctx(), "   ") is None


# --- Provenance is scoped to this turn -------------------------------------


def test_an_earlier_turns_result_does_not_license_a_number() -> None:
    """A figure the scorer produced ten minutes ago is not evidence now."""
    ctx = Ctx(
        [
            event("score_programs", SCORE_RESULT, invocation_id="inv-0"),
            event("score_programs", {"status": "success", "ranking": []}),
        ]
    )
    assert blocked(screen(ctx, "Delft's tuition is 22290."))


def test_turn_tool_results_reads_names_and_payloads() -> None:
    names, payloads = turn_tool_results(
        SimpleNamespace(
            session=SimpleNamespace(
                events=[
                    event("score_programs", SCORE_RESULT),
                    event("get_profile", {"fields": {}}, invocation_id="other"),
                ]
            )
        ),
        INVOCATION,
    )
    assert names == {"score_programs"}
    assert payloads == [SCORE_RESULT]


def test_student_text_ignores_model_content() -> None:
    ctx = scored_ctx()
    ctx.user_content = SimpleNamespace(
        role="model", parts=[SimpleNamespace(text="43000")]
    )
    assert student_text(ctx) == ""


# --- It fails open ---------------------------------------------------------


def test_a_screening_failure_never_breaks_the_turn() -> None:
    """The scorer is the source of truth; a broken screen must not block it."""

    class Broken(Ctx):
        def get_invocation_context(self) -> Any:
            raise RuntimeError("invocation context unavailable")

    assert screen(Broken([]), "Leiden ranks 1 on 1.0.") is None


@pytest.mark.parametrize("events", [None, [], [SimpleNamespace(content=None)]])
def test_malformed_event_streams_are_tolerated(events: Any) -> None:
    ctx = Ctx(events if events is not None else [])
    assert screen(ctx, "Anything at all.") is None
