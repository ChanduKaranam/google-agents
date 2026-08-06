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

"""Stage F — deterministic affinity, the minimum needed to rank a result.

Affinity is overlap between *evidenced* anchors, which is countable. Every
test here runs on plain dicts: no ADK, no model, no network.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.affinity import (
    ANCHORS,
    anchor_values_from_profile,
    matched_anchors,
    rank_people,
)
from app.reference.alumni_fields import PROHIBITED_FIELDS


def person(name: str, **fields: str) -> dict[str, Any]:
    """A rendered alumni record, in the shape `render_person` produces."""
    return {
        "record_id": name.lower().replace(" ", "-"),
        "name_as_published": name,
        "university": "TU Delft",
        "fields": {
            key: {"value": value, "tier": "REPORTED"} for key, value in fields.items()
        },
    }


def profile(**fields: str) -> dict[str, Any]:
    return {"fields": {key: {"value": value} for key, value in fields.items()}}


ANNA = person(
    "Anna de Vries",
    prior_institution="Anna University",
    prior_degree="Computer Engineering",
    program="MSc Computer Science",
)
BRAM = person("Bram Jansen", program="MSc Computer Science")
CHEN = person("Chen Wu", employer="Booking.com")


# --- The anchor set --------------------------------------------------------


def test_every_anchor_names_a_real_profile_field_and_a_real_alumni_field() -> None:
    """An anchor pointing at a field that does not exist can never match."""
    from app.reference.alumni_fields import ALUMNI_FIELDS
    from app.reference.profile_fields import FIELDS

    for anchor in ANCHORS:
        assert anchor.profile_field in FIELDS, anchor.profile_field
        assert anchor.alumni_field in ALUMNI_FIELDS, anchor.alumni_field


def test_no_anchor_rests_on_a_protected_attribute() -> None:
    """Architecture §12: matching on citizenship is discrimination, not affinity."""
    for anchor in ANCHORS:
        assert anchor.profile_field not in PROHIBITED_FIELDS
        assert anchor.alumni_field not in PROHIBITED_FIELDS


def test_citizenship_is_never_an_anchor() -> None:
    """Named explicitly because it is the one the spec calls out."""
    assert "citizenship" not in {a.profile_field for a in ANCHORS}


def test_anchor_values_ignore_profile_fields_that_are_not_anchors() -> None:
    """Only the anchor fields are read; nothing else about the student is used."""
    values = anchor_values_from_profile(
        profile(
            undergrad_institution="Anna University",
            citizenship="India",
            gpa_value="8.1",
        )
    )
    assert values == {"undergrad_institution": "Anna University"}


# --- Matching --------------------------------------------------------------


def test_a_shared_undergraduate_institution_matches() -> None:
    matches = matched_anchors(
        anchor_values_from_profile(profile(undergrad_institution="Anna University")),
        ANNA,
    )
    assert [m["anchor"] for m in matches] == ["undergrad_institution"]


def test_a_match_carries_a_rationale_naming_both_sides() -> None:
    """The rationale is the useful part — a bare count hides what matched."""
    match = matched_anchors(
        anchor_values_from_profile(profile(undergrad_institution="Anna University")),
        ANNA,
    )[0]
    assert "Anna University" in match["rationale"]
    assert match["student_value"] == "Anna University"
    assert match["alumni_value"] == "Anna University"


def test_matching_ignores_case_spacing_and_punctuation() -> None:
    """`anna university` and `Anna University.` are the same institution."""
    matches = matched_anchors(
        anchor_values_from_profile(
            profile(undergrad_institution="  anna  UNIVERSITY.")
        ),
        ANNA,
    )
    assert len(matches) == 1


def test_a_qualifier_does_not_break_a_specialization_match() -> None:
    """`Computer Science` must match a program published as `MSc Computer Science`."""
    matches = matched_anchors(
        anchor_values_from_profile(profile(specialization_interest="Computer Science")),
        ANNA,
    )
    assert [m["anchor"] for m in matches] == ["specialization"]


def test_different_institutions_do_not_match() -> None:
    assert (
        matched_anchors(
            anchor_values_from_profile(profile(undergrad_institution="IIT Bombay")),
            ANNA,
        )
        == []
    )


def test_a_person_missing_the_alumni_side_matches_nothing() -> None:
    """Absence is not agreement. Chen has no prior_institution claim at all."""
    assert (
        matched_anchors(
            anchor_values_from_profile(
                profile(undergrad_institution="Anna University")
            ),
            CHEN,
        )
        == []
    )


def test_an_empty_profile_matches_nobody() -> None:
    """No anchors on the student side is a valid state, not an error."""
    assert matched_anchors(anchor_values_from_profile(profile()), ANNA) == []


@pytest.mark.parametrize("tier", ["VERIFIED", "REPORTED"])
def test_both_evidenced_tiers_may_anchor(tier: str) -> None:
    candidate = person("X Y", prior_institution="Anna University")
    candidate["fields"]["prior_institution"]["tier"] = tier
    assert (
        matched_anchors(
            anchor_values_from_profile(
                profile(undergrad_institution="Anna University")
            ),
            candidate,
        )
        != []
    )


def test_no_anchor_may_rest_on_an_inference() -> None:
    """Architecture §12: an inferred value is not evidence of anything."""
    candidate = person("X Y", prior_institution="Anna University")
    candidate["fields"]["prior_institution"]["tier"] = "INFERENCE"
    assert (
        matched_anchors(
            anchor_values_from_profile(
                profile(undergrad_institution="Anna University")
            ),
            candidate,
        )
        == []
    )


# --- Ranking ---------------------------------------------------------------


def test_more_matched_anchors_ranks_higher() -> None:
    ranked = rank_people(
        [BRAM, ANNA],
        anchor_values_from_profile(
            profile(
                undergrad_institution="Anna University",
                specialization_interest="Computer Science",
            )
        ),
    )
    assert [r["name_as_published"] for r in ranked] == ["Anna de Vries", "Bram Jansen"]
    assert [r["rank"] for r in ranked] == [1, 2]


def test_ties_stay_ties() -> None:
    """Same rule as Phase 3: competition ranking, no arbitrary tiebreak."""
    ranked = rank_people(
        [ANNA, BRAM, CHEN],
        anchor_values_from_profile(profile(specialization_interest="Computer Science")),
    )
    assert [r["rank"] for r in ranked] == [1, 1, 3]


def test_ranking_is_order_independent() -> None:
    """The same people in a different order must produce the same ranking."""
    values = anchor_values_from_profile(
        profile(undergrad_institution="Anna University")
    )
    forward = rank_people([ANNA, BRAM, CHEN], values)
    backward = rank_people([CHEN, BRAM, ANNA], values)
    assert [r["record_id"] for r in forward] == [r["record_id"] for r in backward]
    assert [r["rank"] for r in forward] == [r["rank"] for r in backward]


def test_ranking_is_deterministic_across_repeated_calls() -> None:
    values = anchor_values_from_profile(
        profile(undergrad_institution="Anna University")
    )
    assert rank_people([ANNA, BRAM, CHEN], values) == rank_people(
        [ANNA, BRAM, CHEN], values
    )


def test_nobody_is_dropped_for_matching_nothing() -> None:
    """Affinity orders a result; it never filters one.

    A person with no shared anchor is still a real alumnus of the program,
    and hiding them would make the list look more relevant than it is.
    """
    ranked = rank_people(
        [ANNA, BRAM, CHEN],
        anchor_values_from_profile(profile(undergrad_institution="Anna University")),
    )
    assert len(ranked) == 3
    assert ranked[-1]["matched_anchors"] == []


def test_ranking_with_no_student_anchors_preserves_everyone_at_one_rank() -> None:
    ranked = rank_people([ANNA, BRAM, CHEN], {})
    assert [r["rank"] for r in ranked] == [1, 1, 1]
    assert all(r["matched_anchors"] == [] for r in ranked)


def test_no_composite_score_is_produced() -> None:
    """Architecture §12: a single number would hide which anchor matched."""
    ranked = rank_people(
        [ANNA],
        anchor_values_from_profile(profile(undergrad_institution="Anna University")),
    )
    assert "score" not in ranked[0]
    assert "confidence" not in ranked[0]


def test_ranking_does_not_mutate_the_people_it_was_given() -> None:
    before = dict(ANNA)
    rank_people(
        [ANNA],
        anchor_values_from_profile(profile(undergrad_institution="Anna University")),
    )
    assert ANNA == before
    assert "matched_anchors" not in ANNA


def test_an_empty_list_ranks_to_an_empty_list() -> None:
    assert rank_people([], {"undergrad_institution": "Anna University"}) == []
