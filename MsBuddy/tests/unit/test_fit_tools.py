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

"""`match_universities` — the reference dataset meets the stored profile."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.config import STATE_PROFILE
from app.fit import FIT_BANDS
from app.reference.universities import UNIVERSITIES
from app.tools.fit_tools import match_universities


class StubToolContext:
    def __init__(self) -> None:
        self.state: dict[str, Any] = {}
        self.invocation_id = "test-invocation"
        self.session = SimpleNamespace(events=[])


def profile_state(**overrides) -> dict[str, Any]:
    values = {
        "gpa_value": 8.1,
        "gpa_scale": "cgpa_10",
        "ielts_overall": 7.0,
        "specialization_interest": "Computer Science",
        "citizenship": "India",
    }
    values.update(overrides)
    return {"fields": {k: {"value": v} for k, v in values.items() if v is not None}}


@pytest.fixture
def context() -> StubToolContext:
    ctx = StubToolContext()
    ctx.state[STATE_PROFILE] = profile_state()
    return ctx


def test_country_filter_scopes_the_matches(context: StubToolContext) -> None:
    result = match_universities("USA", "", context)
    assert result["status"] == "success"
    usa_count = sum(1 for u in UNIVERSITIES if u["country"] == "USA")
    assert len(result["matches"]) == usa_count
    assert all(m["country"] == "USA" for m in result["matches"])


def test_every_match_carries_a_band_and_factors(context: StubToolContext) -> None:
    for match in match_universities("USA", "", context)["matches"]:
        assert match["band"] in FIT_BANDS
        assert match["factors"]
        assert match["website"].startswith("https://")


def test_matches_are_ordered_strongest_band_first(context: StubToolContext) -> None:
    bands = [m["band"] for m in match_universities("", "", context)["matches"]]
    indices = [FIT_BANDS.index(b) for b in bands]
    assert indices == sorted(indices)


def test_the_program_filter_narrows_by_subject(context: StubToolContext) -> None:
    result = match_universities("", "Robotics", context)
    names = {m["university"] for m in result["matches"]}
    assert names  # someone teaches robotics
    for match in result["matches"]:
        entry = next(u for u in UNIVERSITIES if u["name"] == match["university"])
        assert any("robotics" in p.lower() for p in entry["programs"])


def test_an_uncovered_country_is_an_honest_empty(context: StubToolContext) -> None:
    result = match_universities("Wakanda", "", context)
    assert result["status"] == "success"
    assert result["matches"] == []
    assert "Wakanda" not in str(result["available_countries"])
    assert result["note"]


def test_a_missing_gpa_asks_for_it(context: StubToolContext) -> None:
    context.state[STATE_PROFILE] = profile_state(gpa_value=None)
    result = match_universities("USA", "", context)
    assert result["status"] == "error"
    assert result["reason"] == "gpa_missing"


def test_the_disclaimer_travels_with_every_result(context: StubToolContext) -> None:
    result = match_universities("USA", "", context)
    assert "typical" in result["disclaimer"].lower()
    assert "research" in result["disclaimer"].lower()


def test_citizenship_never_reaches_the_output(context: StubToolContext) -> None:
    rendered = str(match_universities("", "", context)).lower()
    assert "citizenship" not in rendered
    assert "india" not in rendered


def test_matching_writes_no_state(context: StubToolContext) -> None:
    before = dict(context.state)
    match_universities("USA", "Computer Science", context)
    assert context.state == before
