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

"""Stage G — a person the admission gate refused must not reach the student.

The storage gate already makes it impossible to *record* an unverified
person. This closes the remaining path: naming one in prose on the way past
(architecture §14, failure mode 12).

The check is deliberately narrow. It never tries to detect "a person's name"
in free text — that is a heuristic and would misfire. It looks for the exact
strings `save_alumni_records` itself reported as refused, which makes a hit
a determinable violation rather than a guess. The second half of this file
matters more than the first: a screen that blocks correct answers is worse
than no screen.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from app.plugins.narration_integrity import (
    NarrationIntegrityPlugin,
    refused_person_names,
)

INVOCATION = "inv-1"

ADMITTED_ONLY = {
    "status": "success",
    "admitted": [{"name": "Anna de Vries", "admitted": True}],
    "rejected": [],
}

ONE_REFUSED = {
    "status": "partial",
    "admitted": [{"name": "Anna de Vries", "admitted": True}],
    "rejected": [
        {
            "name": "Sanne Bakker",
            "admitted": False,
            "reason": "no_verifiable_claim",
        }
    ],
}

ALL_REFUSED = {
    "status": "error",
    "admitted": [],
    "rejected": [
        {"name": "Sanne Bakker", "admitted": False, "reason": "no_verifiable_claim"},
        {
            "name": "Pieter Groot",
            "admitted": False,
            "reason": "source_cannot_originate",
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
    def __init__(
        self, events: list[Any], said: str = "", agent_name: str = "root_agent"
    ) -> None:
        self.agent_name = agent_name
        self.invocation_id = INVOCATION
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


def alumni_ctx(payload: Any = ONE_REFUSED, said: str = "") -> Ctx:
    return Ctx([event("save_alumni_records", payload)], said=said)


def blocked(result: Any) -> bool:
    return result is not None


# --- It catches what it exists to catch ------------------------------------


def test_naming_a_refused_person_is_blocked() -> None:
    result = screen(
        alumni_ctx(),
        "I found Anna de Vries, and also Sanne Bakker who may work at Google.",
    )
    assert blocked(result)


def test_the_block_message_does_not_repeat_the_name_it_just_suppressed() -> None:
    """Re-emitting the name in the refusal would defeat the whole point."""
    result = screen(alumni_ctx(), "Sanne Bakker is a TU Delft graduate.")
    text = result.content.parts[0].text
    assert "Sanne Bakker" not in text
    assert "could not verify" in text


def test_the_block_message_offers_the_honest_alternative() -> None:
    text = screen(alumni_ctx(), "Sanne Bakker studied there.").content.parts[0].text
    assert "how many candidates" in text


def test_a_refused_name_is_caught_regardless_of_casing() -> None:
    assert blocked(screen(alumni_ctx(), "i also saw sanne bakker mentioned."))


def test_every_refused_name_counts_not_just_the_first() -> None:
    result = screen(alumni_ctx(ALL_REFUSED), "Pieter Groot also came up.")
    assert blocked(result)
    assert "1 person/people" in result.content.parts[0].text


def test_the_count_reflects_how_many_leaked() -> None:
    result = screen(
        alumni_ctx(ALL_REFUSED), "Sanne Bakker and Pieter Groot both appeared."
    )
    assert "2 person/people" in result.content.parts[0].text


# --- It leaves correct answers alone ---------------------------------------


def test_naming_only_admitted_people_passes_through() -> None:
    assert not blocked(
        screen(
            alumni_ctx(),
            "I found one verified alumna: Anna de Vries, per tudelft.nl. "
            "One other candidate did not meet the evidence bar.",
        )
    )


def test_reporting_the_refusals_without_naming_anyone_passes_through() -> None:
    """The behaviour the root instruction actually asks for."""
    assert not blocked(
        screen(
            alumni_ctx(ALL_REFUSED),
            "I could not verify any alumni for that program. Two candidates "
            "came back but no source named them, so I am not going to list "
            "them.",
        )
    )


def test_an_empty_answer_is_not_screened() -> None:
    assert not blocked(screen(alumni_ctx(), "   "))


def test_a_turn_with_no_alumni_tool_is_untouched() -> None:
    """Scope stays narrow: ordinary conversation is not screened at all."""
    ctx = Ctx([event("get_profile", {"status": "success"})])
    assert not blocked(screen(ctx, "Sanne Bakker sounds like a nice name."))


def test_a_name_admitted_elsewhere_in_the_same_turn_may_be_used() -> None:
    """Two candidates can share a name and only one survive.

    The one that survived is a real person the sources support, and refusing
    to name them because a namesake failed would suppress a correct answer.
    """
    payload = {
        "status": "partial",
        "admitted": [{"name": "Bob Smith", "admitted": True}],
        "rejected": [{"name": "Bob Smith", "admitted": False, "reason": "x"}],
    }
    assert not blocked(screen(alumni_ctx(payload), "Bob Smith graduated in 2019."))


def test_a_non_root_agent_is_not_screened() -> None:
    ctx = Ctx([event("save_alumni_records", ONE_REFUSED)], agent_name="other")
    assert not blocked(screen(ctx, "Sanne Bakker"))


def test_an_event_from_an_earlier_turn_does_not_screen_this_one() -> None:
    """A candidate refused ten minutes ago is not this answer's business."""
    ctx = Ctx([event("save_alumni_records", ONE_REFUSED, invocation_id="older")])
    assert not blocked(screen(ctx, "Sanne Bakker"))


# --- The name extraction itself --------------------------------------------


def test_refused_names_excludes_anyone_also_admitted() -> None:
    payload = {
        "admitted": [{"name": "Bob Smith"}],
        "rejected": [{"name": "Bob Smith"}, {"name": "Sanne Bakker"}],
    }
    assert refused_person_names([payload]) == ["Sanne Bakker"]


@pytest.mark.parametrize("short", ["Li", "Wu", "Al"])
def test_a_very_short_name_is_not_matched(short: str) -> None:
    """It would hit inside ordinary words and block correct answers."""
    assert refused_person_names([{"rejected": [{"name": short}]}]) == []


def test_malformed_payloads_are_ignored_rather_than_raising() -> None:
    assert refused_person_names(["not a dict", None, {}, {"rejected": None}]) == []


def test_a_payload_with_no_names_yields_nothing() -> None:
    assert refused_person_names([{"rejected": [{"reason": "x"}]}]) == []
