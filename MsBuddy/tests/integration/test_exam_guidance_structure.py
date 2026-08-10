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

"""Exam and eligibility guidance — the capability the Lendi question needed.

The reported failure: "I am a CSE graduate at Lendi and I want to do MS in
Canada. Help me in finding which exams are suitable to go there." The
profile was extracted and then the conversation stalled, because nothing
told the root how to answer an exam question — the strict evidence rules
were all it had, and they only say what it must not do.

The design that fixes it, pinned here:

* Country-level exam guidance is general knowledge with hedges — English
  tests are commonly expected, GRE varies by program — answered directly,
  no search.
* A *specific* university's requirements are evidence: researched via the
  existing C2 path, whose registry already carries `test_requirements`.
* The answer always ends with the useful next step: offer to check named
  universities and report exactly what they require, with sources.
* Never a country-level generalization stated as a rule ("Canada requires
  GRE") — the instruction forbids exactly that sentence shape.
"""

from __future__ import annotations

from app.agent import ROOT_INSTRUCTION
from app.reference.program_fields import PROGRAM_FIELDS

FLAT = " ".join(ROOT_INSTRUCTION.split()).lower()


def test_the_instruction_has_an_exam_section() -> None:
    assert "## Exams and eligibility" in ROOT_INSTRUCTION


def test_country_level_guidance_is_answered_directly() -> None:
    section = FLAT[FLAT.index("exams and eligibility") :]
    assert "ielts" in section
    assert "toefl" in section
    assert "gre" in section
    assert "answer" in section


def test_university_specific_requirements_go_through_research() -> None:
    section = ROOT_INSTRUCTION[ROOT_INSTRUCTION.index("## Exams and eligibility") :]
    assert "test_requirements" in section
    assert "research" in section.lower()


def test_the_registry_actually_carries_the_field_the_section_names() -> None:
    """The offer must be honest: research can only store registry fields."""
    assert "test_requirements" in PROGRAM_FIELDS


def test_country_generalizations_are_forbidden() -> None:
    section = FLAT[FLAT.index("exams and eligibility") :]
    assert "canada requires" in section  # named as the forbidden shape
    assert "never" in section


def test_the_answer_ends_with_an_offer_not_a_dead_end() -> None:
    section = FLAT[FLAT.index("exams and eligibility") :]
    assert "offer" in section
