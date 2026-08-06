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

"""The comparison dimension registry (spec C3, Phase 3 §4).

A *dimension* is something programs can be ranked on. It is deliberately a
much shorter list than `program_fields`: most retrieved facts are worth
*showing* but are not orderable. `application_deadline` is the clearest
example — an earlier deadline is not "better", it is just earlier — so it is
normalized and displayed in the matrix but never scored.

Each dimension names the program fields it reads and the direction that
counts as better. Nothing here knows how to *parse* a value; that is
`app.normalize`. Nothing here knows how to *weigh* one; that is
`app.scoring`.
"""

from __future__ import annotations

from dataclasses import dataclass

VERSION = "comparison_dimensions:v1"

LOWER_IS_BETTER = "lower_is_better"
HIGHER_IS_BETTER = "higher_is_better"


@dataclass(frozen=True)
class Dimension:
    """One orderable axis of comparison."""

    key: str
    label: str
    kind: str
    direction: str
    source_field: str
    description: str
    # Fields that must agree across programs before this dimension can be
    # ranked at all. Cost is only comparable between programs quoted in the
    # same currency on the same basis; comparing EUR/year against USD/program
    # is the C3 failure case "comparing tuition figures from different
    # academic years or currencies as if equal".
    comparability_keys: tuple[str, ...] = ()


DIMENSIONS: dict[str, Dimension] = {
    "cost": Dimension(
        key="cost",
        label="Tuition cost",
        kind="money",
        direction=LOWER_IS_BETTER,
        source_field="tuition_amount",
        description=(
            "Published tuition. Comparable only between programs quoted in "
            "the same currency on the same basis — there is no exchange rate "
            "in this system, by design."
        ),
        comparability_keys=("currency", "basis"),
    ),
    "duration": Dimension(
        key="duration",
        label="Program length",
        kind="duration",
        direction=LOWER_IS_BETTER,
        source_field="duration",
        description=(
            "Program length in months. Shorter is treated as better because "
            "it costs less time and less living expense; a student who wants "
            "a longer program can weight this dimension to zero."
        ),
    ),
    "stem": Dimension(
        key="stem",
        label="STEM designation",
        kind="boolean",
        direction=HIGHER_IS_BETTER,
        source_field="stem_designation",
        description=(
            "Whether the institution publishes a STEM/OPT designation. "
            "Only meaningful for US programs; elsewhere it is normally "
            "unknown and drops out of scoring rather than counting against "
            "the program."
        ),
    ),
    "test_burden": Dimension(
        key="test_burden",
        label="Test requirement burden",
        kind="test_requirement",
        direction=LOWER_IS_BETTER,
        source_field="test_requirements",
        description=(
            "Whether a GRE/GMAT score is required. Not required scores "
            "better than optional, which scores better than required."
        ),
    ),
}

DIMENSION_KEYS: tuple[str, ...] = tuple(DIMENSIONS)

# Fields that are normalized for display in the comparison matrix but are
# never scored. Named explicitly so the omission reads as a decision rather
# than an oversight.
DISPLAY_ONLY_FIELDS: dict[str, str] = {
    "application_deadline": (
        "A deadline is a constraint, not a quality. It is shown with its "
        "normalized date so the student can plan, but ranking on it would "
        "assert that earlier is better, which is not true."
    ),
}
