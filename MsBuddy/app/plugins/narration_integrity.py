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

"""`NarrationIntegrityPlugin` — runtime enforcement of the C3 number boundary.

Phase 3 put every calculation in Python, and the Phase 3 audit found the one
place that guarantee stopped being structural: the narration. The *computed*
score was already immutable — it lives in a tool result the model cannot
reach — but nothing stopped the model from **restating** it wrongly, or from
adding a figure the scorer never produced. Instruction text and a unit test
are not enforcement, so this plugin closes that gap.

**The rule.** When a comparison tool has run in this turn, every number in
the answer must appear in something the turn actually produced: a tool
result, or the student's own message. A number that appears in neither has
no provenance, and in a ranked list an untraceable number is exactly the
confident mistake that costs a student a decision.

**Why this is allowed to block when `EvidencePlugin` mostly does not.**
`EvidencePlugin` deals with prose claims, where detection is heuristic and a
false positive would mangle a correct answer (spec §16.4). Here the
comparison is arithmetic against a closed set: the turn's tool outputs are
known exactly, so "this number came from nowhere" is a determinable fact
rather than a guess. That is what makes blocking defensible.

**Scope is deliberately narrow.** The plugin does nothing at all unless a
C3 tool ran this turn. Profile conversations, research turns and ordinary
chat are untouched, so the blast radius is confined to the one capability
whose whole value rests on its numbers being trustworthy.

Provenance is read from `session.events` rather than accumulated in state:
the events already carry every `function_response` for the invocation, so
the plugin holds no memory of its own and cannot leak between turns.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_response import LlmResponse
from google.adk.plugins.base_plugin import BasePlugin
from google.genai import types

from app.scoring import explanation_integrity

logger = logging.getLogger("msbuddy.narration_integrity")

ROOT_AGENT_NAME = "root_agent"

# Only these turns are screened. The guarantee being enforced is C3's.
COMPARISON_TOOLS = frozenset(
    {
        "score_programs",
        "build_comparison_matrix",
        "explain_ranking_inputs",
    }
)

BLOCK_TEMPLATE = (
    "I need to stop and correct myself before you read that.\n\n"
    "My draft comparison contained {count} figure(s) that the scoring tool "
    "did not produce: {numbers}. Everything in a ranking is supposed to "
    "trace back to a computed result you could check by hand, and those "
    "do not.\n\n"
    "Ask me to run the comparison again and I'll report only what the "
    "scorer returns, with the arithmetic shown."
)

# --- C4: a person the admission gate refused must not be named -------------

ALUMNI_ADMISSION_TOOL = "save_alumni_records"

# A refused name has to be long enough that finding it in prose means
# something. Two- and three-character names would match inside ordinary
# words and block correct answers for no gain.
MIN_REFUSED_NAME_LENGTH = 4

PERSON_BLOCK_TEMPLATE = (
    "I need to stop myself there.\n\n"
    "My draft named {count} person/people whose existence I could not verify "
    "against a source that actually named them. I'm not going to show you a "
    "name I can't stand behind — you might try to contact them, and I have no "
    "evidence they are who the search suggested.\n\n"
    "What I can tell you is how many candidates came back and why each was "
    "refused. Ask me and I'll go through that, or I can search again with a "
    "narrower program or year."
)


def refused_person_names(payloads: list[Any]) -> list[str]:
    """Names `save_alumni_records` refused this turn, and did not also admit.

    The whole check rests on this being an exact, closed set. Detecting "a
    person's name" in free prose is a heuristic and would misfire; detecting
    *these particular strings* is a substring search over names the gate
    itself produced, so a hit is a determinable violation rather than a
    guess — the same standard the number rule above is held to.

    A name can appear on both lists in one turn: two candidates may share a
    name and only one survive. The admitted one is real and may be named.
    """
    refused: set[str] = set()
    admitted: set[str] = set()

    for payload in payloads:
        if not isinstance(payload, dict):
            continue
        for key, sink in (("rejected", refused), ("admitted", admitted)):
            for entry in payload.get(key) or []:
                if not isinstance(entry, dict):
                    continue
                name = str(entry.get("name") or "").strip()
                if len(name) >= MIN_REFUSED_NAME_LENGTH:
                    sink.add(name)

    admitted_folded = {n.casefold() for n in admitted}
    return sorted(n for n in refused if n.casefold() not in admitted_folded)


def named_in(text: str, names: list[str]) -> list[str]:
    """Which of `names` the answer actually mentions."""
    lowered = text.casefold()
    return [name for name in names if name.casefold() in lowered]


def turn_tool_results(
    invocation: Any, invocation_id: str | None
) -> tuple[set[str], list[Any]]:
    """Tool names and payloads produced during this invocation.

    Read from the session's own events, which is where ADK records every
    function response. Events from earlier turns are excluded by
    `invocation_id`: a figure the scorer produced ten minutes ago is not
    evidence for the answer being written now.
    """
    names: set[str] = set()
    payloads: list[Any] = []

    for event in getattr(getattr(invocation, "session", None), "events", None) or []:
        if invocation_id and getattr(event, "invocation_id", None) != invocation_id:
            continue
        content = getattr(event, "content", None)
        for part in getattr(content, "parts", None) or []:
            response = getattr(part, "function_response", None)
            if response is None:
                continue
            name = getattr(response, "name", None)
            if name:
                names.add(str(name))
            payload = getattr(response, "response", None)
            if payload is not None:
                payloads.append(payload)

    return names, payloads


def student_text(callback_context: CallbackContext) -> str:
    """The student's own words this turn.

    Included so that repeating back a number the student supplied — a GPA, a
    budget, a test score — is never mistaken for a fabrication.
    """
    content = getattr(callback_context, "user_content", None)
    if content is None or getattr(content, "role", None) != "user":
        return ""
    return " ".join(
        part.text
        for part in (getattr(content, "parts", None) or [])
        if getattr(part, "text", None)
    )


def _response_text(llm_response: LlmResponse) -> str:
    content = getattr(llm_response, "content", None)
    if content is None:
        return ""
    return "".join(
        part.text
        for part in (getattr(content, "parts", None) or [])
        if getattr(part, "text", None)
    )


class NarrationIntegrityPlugin(BasePlugin):
    """Blocks a comparison answer that states a number no tool produced."""

    def __init__(self, name: str = "narration_integrity") -> None:
        super().__init__(name=name)

    async def after_model_callback(
        self,
        *,
        callback_context: CallbackContext,
        llm_response: LlmResponse,
    ) -> LlmResponse | None:
        """Screen a comparison answer. Returns a replacement only when blocking."""
        try:
            if getattr(callback_context, "agent_name", None) != ROOT_AGENT_NAME:
                return None
            if getattr(llm_response, "partial", False):
                return None

            text = _response_text(llm_response)
            if not text.strip():
                return None

            invocation_id = getattr(callback_context, "invocation_id", None)
            invocation = callback_context.get_invocation_context()
            called, payloads = turn_tool_results(invocation, invocation_id)

            if ALUMNI_ADMISSION_TOOL in called:
                blocked = self._screen_people(
                    text, payloads, invocation_id, sorted(called)
                )
                if blocked is not None:
                    return blocked

            # Nothing further to enforce outside a comparison turn.
            if not called & COMPARISON_TOOLS:
                return None

            check = explanation_integrity(
                text,
                {
                    "tool_results": payloads,
                    "student_text": student_text(callback_context),
                },
            )

            record: dict[str, Any] = {
                "event": "narration_integrity",
                "invocation_id": invocation_id,
                "comparison_tools": sorted(called & COMPARISON_TOOLS),
                "tool_results_seen": len(payloads),
                "unsupported_numbers": check["unsupported_numbers"],
                "blocked": not check["ok"],
                "alarm": not check["ok"],
            }

            if check["ok"]:
                logger.info(json.dumps(record))
                return None

            logger.warning(json.dumps(record))
            unsupported = check["unsupported_numbers"]
            return LlmResponse(
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part.from_text(
                            text=BLOCK_TEMPLATE.format(
                                count=len(unsupported),
                                numbers=", ".join(unsupported),
                            )
                        )
                    ],
                )
            )
        # Broad by intent: a screening failure must not break the turn. It
        # fails open, which leaves the deterministic scorer — the actual
        # source of the numbers — completely unaffected.
        except Exception:
            logger.exception("narration integrity screening failed")
            return None

    def _screen_people(
        self,
        text: str,
        payloads: list[Any],
        invocation_id: str | None,
        called: list[str],
    ) -> LlmResponse | None:
        """Block an answer that names someone the admission gate refused.

        Architecture §13 and §14 failure mode 12: the storage gate already
        makes it impossible to *record* an unverified person, but nothing
        stopped the model listing one in prose on the way past. This closes
        that, and it is the alumni analogue of the number rule — the refused
        names are known exactly, so there is no detection heuristic here.
        """
        refused = refused_person_names(payloads)
        leaked = named_in(text, refused)

        record: dict[str, Any] = {
            "event": "narration_person_integrity",
            "invocation_id": invocation_id,
            "tools_called": called,
            "refused_candidates": len(refused),
            "leaked_names": len(leaked),
            "blocked": bool(leaked),
            "alarm": bool(leaked),
        }

        if not leaked:
            logger.info(json.dumps(record))
            return None

        # The names themselves stay out of the log. Refused candidates are
        # people who may not exist, and writing them to a durable log would
        # be the dossier accumulation §13 forbids.
        logger.warning(json.dumps(record))
        return LlmResponse(
            content=types.Content(
                role="model",
                parts=[
                    types.Part.from_text(
                        text=PERSON_BLOCK_TEMPLATE.format(count=len(leaked))
                    )
                ],
            )
        )
