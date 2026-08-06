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

"""The program field registry — C2's allowlist and staleness map.

Same shape and same purpose as `profile_fields`: a field absent from
`PROGRAM_FIELDS` cannot be written. Each field additionally declares the
staleness class that governs how long its value stays trustworthy (spec
§7.3), because a deadline and a department name age at completely different
rates.

C2 requires missing fields to be returned as `UNKNOWN` rather than omitted,
so `ALL_FIELD_NAMES` is the checklist a ProgramRecord is completed against.
"""

from __future__ import annotations

from dataclasses import dataclass

VERSION = "program_fields:v1"


@dataclass(frozen=True)
class ProgramFieldSpec:
    """One retrievable fact about a program."""

    name: str
    staleness_class: str
    description: str


PROGRAM_FIELDS: dict[str, ProgramFieldSpec] = {
    "program_url": ProgramFieldSpec(
        name="program_url",
        staleness_class="SLOW",
        description="The official program page, as published by the institution.",
    ),
    "degree_title": ProgramFieldSpec(
        name="degree_title",
        staleness_class="SLOW",
        description="The exact awarded degree title, e.g. 'MSc Computer Science'.",
    ),
    "department": ProgramFieldSpec(
        name="department",
        staleness_class="SLOW",
        description="The department or faculty that runs the program.",
    ),
    "duration": ProgramFieldSpec(
        name="duration",
        staleness_class="CYCLICAL",
        description="Program length as stated, e.g. '2 years' or '18 months'.",
    ),
    "tuition_amount": ProgramFieldSpec(
        name="tuition_amount",
        staleness_class="CYCLICAL",
        description="Tuition figure exactly as published, digits only.",
    ),
    "tuition_currency": ProgramFieldSpec(
        name="tuition_currency",
        staleness_class="CYCLICAL",
        description="Currency of the tuition figure, ISO-4217 where stated.",
    ),
    "tuition_basis": ProgramFieldSpec(
        name="tuition_basis",
        staleness_class="CYCLICAL",
        description=(
            "What the tuition figure covers as published — per year, per "
            "term, or whole program. Never assume; a per-year figure read as "
            "a whole-program figure understates cost by the program length."
        ),
    ),
    "tuition_academic_year": ProgramFieldSpec(
        name="tuition_academic_year",
        staleness_class="CYCLICAL",
        description="The academic year the tuition figure applies to, e.g. '2026/27'.",
    ),
    "application_deadline": ProgramFieldSpec(
        name="application_deadline",
        staleness_class="VOLATILE",
        description=(
            "A published application deadline, quoted with its full date and "
            "the intake it belongs to."
        ),
    ),
    "deadline_round": ProgramFieldSpec(
        name="deadline_round",
        staleness_class="VOLATILE",
        description="Which round or applicant category the deadline applies to.",
    ),
    "test_requirements": ProgramFieldSpec(
        name="test_requirements",
        staleness_class="CYCLICAL",
        description="Stated GRE/GMAT/English test requirements, including waivers.",
    ),
    "prerequisites": ProgramFieldSpec(
        name="prerequisites",
        staleness_class="CYCLICAL",
        description="Stated academic background or coursework prerequisites.",
    ),
    "stem_designation": ProgramFieldSpec(
        name="stem_designation",
        staleness_class="CYCLICAL",
        description="STEM/OPT designation where the institution publishes one.",
    ),
}

ALL_FIELD_NAMES: tuple[str, ...] = tuple(PROGRAM_FIELDS)


def is_writable(field_name: str) -> bool:
    """True if `field_name` may be stored on a ProgramRecord."""
    return field_name in PROGRAM_FIELDS


def staleness_class_for(field_name: str) -> str:
    """Staleness class governing this field, defaulting to the safest useful one."""
    spec = PROGRAM_FIELDS.get(field_name)
    return spec.staleness_class if spec else "VOLATILE"
