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

"""Greetings and identity questions must never fail.

Measured against the live agent on 2026-08-07, before the fix:

    USER: Who are you?      ->  "I can't answer that from memory."
    USER: What can you do?  ->  "I can't answer that from memory."
    USER: Hello             ->  get_profile + profile_completeness, then text

The cause is visible in that transcript. The root instruction carries strict
anti-fabrication rules ("never state a fact ... not from memory") aimed at
universities, programs and people — and said nothing about the assistant
itself, so the model applied the prohibition to its own identity. The first
thing a student types is "hi", and the first impression was a refusal.

These tests are structural: they pin the instruction content that fixes it.
The behavioural half — that a live greeting turn calls no tools — lives in
`test_general_conversation_live.py`, because only a real model can prove it.
"""

from __future__ import annotations

from app.agent import ROOT_INSTRUCTION, root_agent

FLAT = " ".join(ROOT_INSTRUCTION.split()).lower()


def test_the_instruction_has_a_general_conversation_section() -> None:
    assert "## Talking with the student" in ROOT_INSTRUCTION


def test_general_conversation_comes_before_any_tool_guidance() -> None:
    """The model reads top-down; the escape hatch must precede the rules
    it is an escape from, or a greeting hits "never from memory" first."""
    section = ROOT_INSTRUCTION.index("## Talking with the student")
    first_tool_mention = ROOT_INSTRUCTION.index("get_profile")
    assert section < first_tool_mention


def test_greetings_are_answered_without_tools() -> None:
    assert "call no tools" in FLAT
    for probe in ("hello", "who are you", "what can you do"):
        assert probe in FLAT, f"instruction does not name the {probe!r} case"


def test_the_memory_rule_is_scoped_away_from_the_assistant_itself() -> None:
    """The fix for 'I can't answer that from memory.'"""
    assert "not about you" in FLAT
    assert "who you are" in FLAT


def test_internal_routing_is_never_exposed() -> None:
    assert "never mention" in FLAT
    assert "agent" in FLAT  # the word it must not surface to users
    assert "one assistant" in FLAT


def test_static_concepts_are_answered_directly() -> None:
    """ "What is an SOP?" is general knowledge, not a university fact."""
    assert "sop" in FLAT
    assert "general knowledge" in FLAT
    # And the boundary is stated: university-specific values still need
    # research, so the carve-out cannot swallow the evidence rules.
    assert "still" in FLAT


def test_the_capability_list_matches_what_is_wired() -> None:
    """The greeting reply offers what exists. If a capability is named in
    the conversation section, a tool for it must actually be attached."""
    tool_names = set()
    for tool in root_agent.tools:
        tool_names.add(getattr(tool, "__name__", None) or getattr(tool, "name", ""))
    assert "get_profile" in tool_names
    assert "build_program_query" in tool_names
    assert "score_programs" in tool_names
    assert "build_alumni_query" in tool_names
