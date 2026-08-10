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

"""Structural wiring for the planning slice: matching, documents, progress.

Three deterministic tools joined the root in the refinement pass —
`match_universities`, `get_application_plan`, `set_document_status`. These
tests pin that they are attached, that the instruction teaches them at the
point of use, and that the boundary that keeps them honest is stated: the
reference dataset is typical data for exploring, research is where current
facts come from, and deadlines are only ever the stored, verified ones.
"""

from __future__ import annotations

from app.agent import ROOT_INSTRUCTION, root_agent

FLAT = " ".join(ROOT_INSTRUCTION.split()).lower()


def _tool_names() -> set[str]:
    return {
        getattr(t, "__name__", None) or getattr(t, "name", "") for t in root_agent.tools
    }


def test_the_three_planning_tools_are_attached() -> None:
    names = _tool_names()
    for wanted in ("match_universities", "get_application_plan", "set_document_status"):
        assert wanted in names, f"{wanted} is not wired to the root"


def test_the_instruction_teaches_matching_before_research() -> None:
    """Matching is discovery; research is evidence. The instruction says so."""
    assert "match_universities" in ROOT_INSTRUCTION
    assert "typical" in FLAT
    assert ROOT_INSTRUCTION.index("match_universities") < ROOT_INSTRUCTION.index(
        "build_program_query"
    )


def test_matching_output_is_never_presented_as_current_fact() -> None:
    assert "not an admission" in FLAT
    assert "never" in FLAT


def test_the_instruction_teaches_documents_and_progress() -> None:
    assert "get_application_plan" in ROOT_INSTRUCTION
    assert "set_document_status" in ROOT_INSTRUCTION


def test_deadlines_are_the_stored_ones_only() -> None:
    """The plan surfaces verified deadlines; the model must not add any."""
    plan_section = ROOT_INSTRUCTION[ROOT_INSTRUCTION.index("get_application_plan") :]
    flat_section = " ".join(plan_section.split()).lower()
    assert "deadline" in flat_section
    assert "research" in flat_section


def test_the_capability_summary_no_longer_says_four_things() -> None:
    """The greeting promises what exists; the count moved on."""
    assert "four things" not in FLAT
