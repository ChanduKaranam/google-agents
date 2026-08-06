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

"""Stage G — the aggregate must be incapable of stating a placement rate.

Architecture §11 draws the line between a fact, an aggregate and an
interpretation. The control is not a rule the model is asked to follow: the
aggregate returns counts *with their denominator* and no ratio, so the
sentence "70% of graduates get data jobs" cannot be assembled from it.
"""

from __future__ import annotations

from typing import Any

from app.alumni_store import render_alumni_store, summarize_alumni
from app.config import MIN_PATTERN_N


def person(name: str, **fields: str) -> dict[str, Any]:
    return {
        "record_id": name.lower().replace(" ", "-"),
        "name_as_published": name,
        "university": "TU Delft",
        "fields": {
            key: {"value": value, "tier": "REPORTED"} for key, value in fields.items()
        },
        "unknown_fields": [],
        "possible_namesakes": [],
    }


THREE = [
    person("Anna de Vries", employer="Booking.com", graduation_year="2021"),
    person("Bram Jansen", employer="Booking.com"),
    person("Chen Wu", graduation_year="2020"),
]


# --- Counts always carry their denominator ---------------------------------


def test_the_denominator_is_the_number_of_people_found() -> None:
    assert summarize_alumni(THREE)["person_count"] == 3


def test_every_field_count_is_reported_against_that_denominator() -> None:
    """A bare "2 work at Booking" invites reading it as "2 out of everyone"."""
    coverage = summarize_alumni(THREE)["field_coverage"]
    assert coverage["employer"] == {"known": 2, "of": 3}
    assert coverage["graduation_year"] == {"known": 2, "of": 3}


def test_a_field_nobody_published_is_reported_as_zero_not_omitted() -> None:
    """A coverage gap must never read as an absence."""
    coverage = summarize_alumni(THREE)["field_coverage"]
    assert coverage["role"] == {"known": 0, "of": 3}


def test_employers_are_counted_with_the_denominator_attached() -> None:
    summary = summarize_alumni(THREE)
    assert summary["employers"] == [{"value": "Booking.com", "count": 2}]
    assert summary["person_count"] == 3


def test_employer_counting_is_case_and_spacing_insensitive() -> None:
    people = [
        person("A A", employer="Booking.com"),
        person("B B", employer="  booking.com "),
    ]
    assert summarize_alumni(people)["employers"] == [
        {"value": "Booking.com", "count": 2}
    ]


# --- The control: no ratio can be expressed --------------------------------


def test_the_aggregate_contains_no_ratio_percentage_or_rate() -> None:
    """The whole point of Stage G. A rate is a claim a convenience sample
    cannot support, so the tool must be unable to produce one."""
    summary = summarize_alumni(THREE)

    def walk(value: Any) -> None:
        if isinstance(value, float):
            raise AssertionError(f"the aggregate produced a float: {value}")
        if isinstance(value, dict):
            for key, item in value.items():
                assert "rate" not in key, f"'{key}' reads as a rate"
                assert "percent" not in key, f"'{key}' reads as a percentage"
                walk(item)
        if isinstance(value, list):
            for item in value:
                walk(item)

    walk(summary)


def test_no_key_in_the_aggregate_suggests_an_outcome_claim() -> None:
    summary = summarize_alumni(THREE)
    for forbidden in ("placement", "salary", "success", "typical", "likelihood"):
        assert not any(forbidden in key for key in summary), forbidden


# --- Pattern language is gated on n ----------------------------------------


def test_pattern_language_is_refused_below_the_threshold() -> None:
    """ "2 of 2 work in data" invites exactly the generalisation to avoid."""
    assert summarize_alumni(THREE)["may_use_pattern_language"] is False


def test_pattern_language_is_permitted_once_there_are_enough_people() -> None:
    many = [person(f"P{i}", employer="Booking.com") for i in range(MIN_PATTERN_N)]
    assert summarize_alumni(many)["may_use_pattern_language"] is True


def test_the_threshold_is_named_so_the_root_can_explain_the_refusal() -> None:
    assert summarize_alumni(THREE)["pattern_language_threshold"] == MIN_PATTERN_N


# --- Mandated disclosures --------------------------------------------------


def test_the_selection_bias_disclosure_is_returned_not_left_to_the_model() -> None:
    """Architecture §11: this is a standing sentence, not a footnote."""
    notice = summarize_alumni(THREE)["selection_bias_notice"].lower()
    assert "not a placement rate" in notice
    assert "representative" in notice


def test_the_disclosure_survives_an_empty_result() -> None:
    """An empty result is the case most likely to be papered over."""
    summary = summarize_alumni([])
    assert summary["person_count"] == 0
    assert summary["is_empty"] is True
    assert summary["selection_bias_notice"]
    assert summary["may_use_pattern_language"] is False


def test_an_empty_result_still_names_every_field_as_zero() -> None:
    coverage = summarize_alumni([])["field_coverage"]
    assert coverage["employer"] == {"known": 0, "of": 0}


# --- Wiring into the read path ---------------------------------------------


def test_the_store_rendering_always_carries_the_summary() -> None:
    """So the root cannot read alumni without also holding the denominator."""
    store = {
        "people": {p["record_id"]: _as_stored(p) for p in THREE},
    }
    rendered = render_alumni_store(store)
    assert rendered["summary"]["person_count"] == 3
    assert rendered["summary"]["selection_bias_notice"]


def _as_stored(rendered: dict[str, Any]) -> dict[str, Any]:
    """Turn a rendered person back into the stored shape `render_person` reads."""
    return {
        "record_id": rendered["record_id"],
        "identity_key": rendered["record_id"],
        "name_as_published": rendered["name_as_published"],
        "university": rendered["university"],
        "fields": {
            name: {
                "value": entry["value"],
                "tier": entry["tier"],
                "evidence": {
                    "source_domain": "tudelft.nl",
                    "staleness_class": "PERSON",
                    "retrieved_at": "2026-08-06T00:00:00+00:00",
                },
                "sources": [],
            }
            for name, entry in rendered["fields"].items()
        },
        "possible_namesakes": [],
    }
