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

"""Structural assertions on the agent tree. No network, no model.

These encode the architecture from `.agents-cli-spec.md` §4 so that a later
phase cannot quietly break it. The search-isolation check in particular
guards a constraint ADK does not validate itself: mixing `google_search` with
FunctionTools on one agent silently disables Automatic Function Calling and
fails at the Gemini API, sometimes only in production (spec §4.4, §12).
"""

from __future__ import annotations

import inspect
from typing import Any

from google.adk.agents import BaseAgent, LlmAgent
from google.adk.tools import BaseTool

from app.agent import app, root_agent
from app.reference.profile_fields import FIELDS
from app.tools import (
    clear_profile_fields,
    get_profile,
    normalize_gpa,
    profile_completeness,
    save_profile_fields,
)

PROFILE_TOOLS = [
    get_profile,
    save_profile_fields,
    profile_completeness,
    normalize_gpa,
    clear_profile_fields,
]


def walk_agents(agent: BaseAgent) -> list[BaseAgent]:
    """Every agent in the tree, root first.

    Descends through `sub_agents` **and** through agents wrapped in an
    `AgentTool`. The second path matters: as of C2 the search-only research
    agent is attached as an `AgentTool` rather than a sub-agent, and a walker
    that only followed `sub_agents` would quietly stop covering the very
    agent the isolation guard below exists to protect.
    """
    found = [agent]
    for child in getattr(agent, "sub_agents", None) or []:
        found.extend(walk_agents(child))
    for tool in getattr(agent, "tools", None) or []:
        wrapped = getattr(tool, "agent", None)
        if isinstance(wrapped, BaseAgent) and wrapped not in found:
            found.extend(walk_agents(wrapped))
    return found


def tool_name(tool: Any) -> str:
    if isinstance(tool, BaseTool):
        return tool.name
    return getattr(tool, "__name__", type(tool).__name__)


def is_builtin_grounding(tool: Any) -> bool:
    """True for model-internal grounding tools such as `google_search`."""
    return tool_name(tool) in {"google_search", "url_context", "vertex_ai_search"}


# --- App wiring ------------------------------------------------------------


def test_app_name_matches_the_agent_directory() -> None:
    """A mismatch breaks eval with "Session not found" (spec §4.4)."""
    assert app.name == "app"


def test_root_agent_is_the_app_root() -> None:
    assert app.root_agent is root_agent
    assert root_agent.name == "root_agent"


def test_profile_audit_plugin_is_registered() -> None:
    assert "profile_audit" in {p.name for p in app.plugins}


# --- Phase 1 component inventory (spec §4.2) -------------------------------


def test_root_exposes_exactly_the_five_profile_tools() -> None:
    names = {tool_name(t) for t in root_agent.tools}
    expected = {t.__name__ for t in PROFILE_TOOLS}
    assert expected <= names, f"missing profile tools: {expected - names}"


def test_profile_extractor_is_the_only_task_sub_agent() -> None:
    """Retrieval specialists attach as AgentTools, never as sub-agents."""
    assert [a.name for a in root_agent.sub_agents] == ["profile_extractor_agent"]


def test_profile_extractor_is_a_task_agent_with_both_schemas() -> None:
    extractor = root_agent.sub_agents[0]
    assert isinstance(extractor, LlmAgent)
    assert extractor.mode == "task"
    assert extractor.input_schema is not None
    assert extractor.output_schema is not None
    assert extractor.description, "task sub-agents need a description to delegate"


def test_extractor_is_wrapped_as_a_delegation_tool_on_the_root() -> None:
    assert "profile_extractor_agent" in {tool_name(t) for t in root_agent.tools}


def test_extractor_cannot_write_state() -> None:
    """It proposes; `save_profile_fields` decides. It holds no profile tools."""
    extractor = root_agent.sub_agents[0]
    names = {tool_name(t) for t in extractor.tools}
    assert names <= {"finish_task"}, f"extractor holds unexpected tools: {names}"


# --- Invariants that must survive later phases -----------------------------


def test_no_agent_mixes_grounding_with_function_tools() -> None:
    """Search-only isolation (spec §4.1, §4.4).

    Trivially true in Phase 1 because nothing holds `google_search` yet. It
    exists now so that C2/C4 cannot introduce the violation unnoticed.
    """
    for agent in walk_agents(root_agent):
        tools = getattr(agent, "tools", None) or []
        grounding = [tool_name(t) for t in tools if is_builtin_grounding(t)]
        if not grounding:
            continue
        others = [
            tool_name(t)
            for t in tools
            if not is_builtin_grounding(t) and tool_name(t) != "finish_task"
        ]
        assert not others, (
            f"agent '{agent.name}' mixes grounding {grounding} with "
            f"function tools {others}; this silently disables AFC"
        )


def test_retrieval_stays_out_of_the_profile_path() -> None:
    """C1 makes zero network calls — "deliberate isolation".

    C2 introduced retrieval, but only inside the research agent. Neither the
    root nor the profile extractor may hold a retrieval tool: the root
    because it reads the student's profile, the extractor because it handles
    their raw words.
    """
    protected = [root_agent, *root_agent.sub_agents]
    for agent in protected:
        for tool in getattr(agent, "tools", None) or []:
            assert not is_builtin_grounding(tool), (
                f"'{tool_name(tool)}' on '{agent.name}' is a retrieval tool; "
                "only the isolated research agent may reach the network"
            )


def test_every_agent_has_a_description() -> None:
    for agent in walk_agents(root_agent):
        assert agent.description, f"'{agent.name}' has no description"


# --- ADK function-tool contract --------------------------------------------


def test_profile_tools_follow_the_adk_signature_rules() -> None:
    """Type hints on every parameter, and no default values (spec §4.4)."""
    for func in PROFILE_TOOLS:
        signature = inspect.signature(func)
        for name, param in signature.parameters.items():
            assert param.annotation is not inspect.Parameter.empty, (
                f"{func.__name__}.{name} has no type hint"
            )
            assert param.default is inspect.Parameter.empty, (
                f"{func.__name__}.{name} has a default value"
            )
        assert signature.return_annotation is not inspect.Parameter.empty


def test_profile_tools_document_themselves_for_the_model() -> None:
    """The docstring is the contract the model reads."""
    for func in PROFILE_TOOLS:
        doc = inspect.getdoc(func) or ""
        assert len(doc) > 80, f"{func.__name__} docstring is too thin"
        assert "Returns:" in doc, f"{func.__name__} does not document its return"
        assert "tool_context" not in doc, (
            f"{func.__name__} mentions tool_context in its docstring"
        )


def test_root_instruction_states_what_is_not_built_yet() -> None:
    """The root must decline unsourced institutional answers, not improvise."""
    instruction = root_agent.instruction.lower()
    assert "not built yet" in instruction or "not available" in instruction
    assert "never" in instruction


def test_root_instruction_forbids_converting_a_gpa_by_hand() -> None:
    """A converted GPA must come from `normalize_gpa`, never from the model.

    Observed on the deployed agent 2026-08-06: asked to record an 8.1/10
    CGPA, the root answered "8.1 / 10 (approx. 3.24 / 4.0 US equivalent)"
    having called `get_profile`, `profile_extractor_agent` and
    `save_profile_fields` — and not `normalize_gpa`. It did the arithmetic
    itself.

    The number happened to be right because that scale is linear. The rule
    exists because most are not: `gpa_scales.py` holds per-scale conversion
    tables precisely so a 10-point CGPA is not simply multiplied by 0.4, and
    a model that reaches for the multiplication once will reach for it on a
    scale where it is wrong.

    "Never do arithmetic yourself" was already in the instruction and was not
    enough — it lives in a general rules list, far from where a GPA is
    actually discussed. So the prohibition is repeated where the temptation
    is, which is what this test pins.
    """
    instruction = root_agent.instruction
    gpa_section = instruction[instruction.index("normalize_gpa") :]
    nearby = gpa_section[:700].lower()
    assert "never convert" in nearby, (
        "the GPA guidance must forbid converting by hand at the point of use"
    )
    assert "arithmetic" in instruction.lower()


def test_extractor_instruction_lists_the_whole_field_registry() -> None:
    """Rendered from FIELDS so the prompt cannot drift from the allowlist."""
    instruction = root_agent.sub_agents[0].instruction
    for name in FIELDS:
        assert name in instruction, f"'{name}' missing from extractor instruction"
