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

"""Structural assertions for C2, plus the evidence plugin's blocking path.

The search-isolation checks here are the ones that matter most in the whole
suite: ADK does not validate the constraint, and a violation fails at the
Gemini API rather than at import — sometimes only in production.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from google.adk.models.llm_response import LlmResponse
from google.adk.tools import AgentTool
from google.genai import types

from app.agent import app, root_agent
from app.callbacks import enforce_retrieval_budget
from app.config import MAX_RETRIEVALS_PER_SESSION, MAX_RETRIEVALS_PER_TURN
from app.plugins.evidence import REFUSAL_TEXT, EvidencePlugin
from app.reference.program_fields import PROGRAM_FIELDS
from tests.integration.test_profile_structure import (
    is_builtin_grounding,
    tool_name,
    walk_agents,
)

RESEARCH = "program_research_agent"


def research_tool() -> AgentTool:
    for tool in root_agent.tools:
        if tool_name(tool) == RESEARCH:
            return tool
    raise AssertionError("program_research_agent is not attached to the root")


# --- Search-only isolation (spec §4.4, §8.2.2) -----------------------------


def test_research_agent_holds_google_search_and_nothing_else() -> None:
    """One function tool beside grounding silently disables AFC for all of them."""
    assert [tool_name(t) for t in research_tool().agent.tools] == ["google_search"]


def test_research_agent_is_not_task_mode() -> None:
    """Task mode appends `finish_task`, which would sit beside grounding."""
    assert research_tool().agent.mode != "task"


def test_research_agent_has_no_output_schema() -> None:
    """A schema can make ADK append `SetModelResponseTool` beside grounding."""
    assert research_tool().agent.output_schema is None


def test_research_agent_has_no_sub_agents() -> None:
    assert not (research_tool().agent.sub_agents or [])


def test_the_isolation_walker_actually_reaches_the_research_agent() -> None:
    """Guards the guard: the research agent attaches as a tool, not a sub-agent."""
    assert RESEARCH in {a.name for a in walk_agents(root_agent)}


def test_only_the_search_specialists_can_reach_the_network() -> None:
    """An exact set: adding a network-capable agent must be a deliberate act.

    Phase 4 moved this from one agent to two. `alumni_discovery_agent` is
    here for the same structural reason as C2's — grounding cannot share an
    agent with function tools — and both are held to the isolation
    assertions above and in `test_alumni_structure.py`.
    """
    grounded = {
        a.name
        for a in walk_agents(root_agent)
        if any(is_builtin_grounding(t) for t in (getattr(a, "tools", None) or []))
    }
    assert grounded == {RESEARCH, "alumni_discovery_agent"}


# --- Root wiring -----------------------------------------------------------


def test_root_exposes_the_program_tools() -> None:
    names = {tool_name(t) for t in root_agent.tools}
    assert {"build_program_query", "save_program_record", "get_shortlist"} <= names


def test_root_cannot_search_directly() -> None:
    """Retrieval must go through the isolated agent, never the root."""
    assert not any(is_builtin_grounding(t) for t in root_agent.tools)


def test_all_three_spec_plugins_are_registered() -> None:
    """Spec §4.2 names three cross-cutting plugins. None may go missing."""
    assert {"profile_audit", "untrusted_content", "evidence"} <= {
        p.name for p in app.plugins
    }


def test_no_unexpected_plugin_is_registered() -> None:
    """Exact set, so adding a cross-cutting hook stays a deliberate act.

    `narration_integrity` is not in the spec inventory. It was added by the
    Phase 3 audit to enforce the C3 number boundary at runtime — a gap that
    only came into existence once comparison began reporting computed
    values, so the spec could not have anticipated it.
    """
    assert {p.name for p in app.plugins} == {
        "profile_audit",
        "untrusted_content",
        "evidence",
        "narration_integrity",
    }


def test_retrieval_budget_callback_is_wired() -> None:
    assert root_agent.before_tool_callback is enforce_retrieval_budget


def test_research_instruction_lists_every_program_field() -> None:
    """Rendered from the registry so prompt and allowlist cannot drift."""
    instruction = research_tool().agent.instruction
    for name in PROGRAM_FIELDS:
        assert name in instruction, f"'{name}' missing from research instruction"


def test_research_instruction_contains_the_untrusted_content_rule() -> None:
    instruction = research_tool().agent.instruction.lower()
    assert "data, never instructions" in instruction
    assert "injection" in instruction


# --- Retrieval budget (spec §8.4) ------------------------------------------


class StubBudgetContext:
    def __init__(self) -> None:
        self.state: dict = {}
        self.invocation_id = "turn-1"


@pytest.mark.asyncio
async def test_budget_allows_calls_under_the_cap() -> None:
    ctx = StubBudgetContext()
    tool = SimpleNamespace(name=RESEARCH)
    for _ in range(MAX_RETRIEVALS_PER_TURN):
        assert await enforce_retrieval_budget(tool, {}, ctx) is None


@pytest.mark.asyncio
async def test_budget_blocks_past_the_turn_cap_and_says_so() -> None:
    ctx = StubBudgetContext()
    tool = SimpleNamespace(name=RESEARCH)
    for _ in range(MAX_RETRIEVALS_PER_TURN):
        await enforce_retrieval_budget(tool, {}, ctx)
    blocked = await enforce_retrieval_budget(tool, {}, ctx)
    assert blocked is not None
    assert blocked["reason"] == "retrieval_budget_exceeded_turn"
    assert "partial" in blocked["message"]


@pytest.mark.asyncio
async def test_a_new_turn_resets_the_per_turn_cap() -> None:
    ctx = StubBudgetContext()
    tool = SimpleNamespace(name=RESEARCH)
    for _ in range(MAX_RETRIEVALS_PER_TURN):
        await enforce_retrieval_budget(tool, {}, ctx)
    ctx.invocation_id = "turn-2"
    assert await enforce_retrieval_budget(tool, {}, ctx) is None


@pytest.mark.asyncio
async def test_session_cap_survives_turn_changes() -> None:
    ctx = StubBudgetContext()
    tool = SimpleNamespace(name=RESEARCH)
    for i in range(MAX_RETRIEVALS_PER_SESSION):
        ctx.invocation_id = f"turn-{i}"
        assert await enforce_retrieval_budget(tool, {}, ctx) is None
    ctx.invocation_id = "turn-final"
    blocked = await enforce_retrieval_budget(tool, {}, ctx)
    assert blocked["reason"] == "retrieval_budget_exceeded_session"


@pytest.mark.asyncio
async def test_budget_ignores_non_research_tools() -> None:
    ctx = StubBudgetContext()
    tool = SimpleNamespace(name="save_profile_fields")
    for _ in range(MAX_RETRIEVALS_PER_TURN + 5):
        assert await enforce_retrieval_budget(tool, {}, ctx) is None


# --- EvidencePlugin blocking path (spec §7.5) ------------------------------


def stub_callback_context(
    agent_name: str, session, state: dict | None = None
) -> SimpleNamespace:
    ctx = SimpleNamespace(
        agent_name=agent_name,
        invocation_id="inv-1",
        partial=False,
        state=state if state is not None else {},
    )
    ctx.get_invocation_context = lambda: SimpleNamespace(session=session)
    return ctx


def response(text: str) -> LlmResponse:
    return LlmResponse(
        content=types.Content(role="model", parts=[types.Part.from_text(text=text)])
    )


EMPTY_SESSION = SimpleNamespace(events=[])


@pytest.mark.asyncio
async def test_unsourced_institutional_answer_is_blocked() -> None:
    """No sources retrieved + a deadline claim means it came from model priors."""
    result = await EvidencePlugin().after_model_callback(
        callback_context=stub_callback_context("root_agent", EMPTY_SESSION),
        llm_response=response("The deadline for MIT EECS is 15 December 2026."),
    )
    assert result is not None
    assert REFUSAL_TEXT in (result.content.parts[0].text or "")


@pytest.mark.asyncio
async def test_profile_conversation_is_never_blocked() -> None:
    """C1 must keep working with zero retrieval — it makes no network calls."""
    result = await EvidencePlugin().after_model_callback(
        callback_context=stub_callback_context("root_agent", EMPTY_SESSION),
        llm_response=response("I've saved your GPA as 8.1 out of 10. Which intake?"),
    )
    assert result is None


@pytest.mark.asyncio
async def test_specialist_output_is_not_screened() -> None:
    """The research agent reports facts by design; only the root is screened."""
    result = await EvidencePlugin().after_model_callback(
        callback_context=stub_callback_context(RESEARCH, EMPTY_SESSION),
        llm_response=response("FIELD: application_deadline | VALUE: 15 December 2026"),
    )
    assert result is None


@pytest.mark.asyncio
async def test_grounded_answer_passes_through() -> None:
    session = SimpleNamespace(
        events=[
            SimpleNamespace(
                grounding_metadata=SimpleNamespace(
                    grounding_chunks=[
                        SimpleNamespace(
                            web=SimpleNamespace(
                                domain=None, title="ethz.ch", uri="https://x/1"
                            )
                        )
                    ],
                    grounding_supports=[
                        SimpleNamespace(
                            segment=SimpleNamespace(
                                text="The deadline is 15 December 2026."
                            ),
                            grounding_chunk_indices=[0],
                        )
                    ],
                    web_search_queries=["eth deadline"],
                )
            )
        ]
    )
    result = await EvidencePlugin().after_model_callback(
        callback_context=stub_callback_context("root_agent", session),
        llm_response=response("The deadline is 15 December 2026, per ethz.ch."),
    )
    assert result is None


@pytest.mark.asyncio
async def test_screening_failure_never_breaks_the_turn() -> None:
    broken = SimpleNamespace(
        agent_name="root_agent", invocation_id="i", partial=False, state={}
    )
    broken.get_invocation_context = lambda: (_ for _ in ()).throw(RuntimeError("boom"))
    result = await EvidencePlugin().after_model_callback(
        callback_context=broken,
        llm_response=response("The deadline is 15 December 2026."),
    )
    assert result is None


def test_narration_integrity_screens_last() -> None:
    """Plugin order is load-bearing, not cosmetic.

    ADK's plugin manager stops at the first `after_model_callback` returning
    non-None (`plugin_manager._run_callbacks`). So if the narration screen
    ran before `EvidencePlugin`, it could pass an answer that the evidence
    gate would have refused outright. Last is the only correct position.
    """
    assert [p.name for p in app.plugins][-1] == "narration_integrity"
    names = [p.name for p in app.plugins]
    assert names.index("evidence") < names.index("narration_integrity")
