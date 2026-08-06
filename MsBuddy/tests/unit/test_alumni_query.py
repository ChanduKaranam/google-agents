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

"""Alumni query construction and the privacy screen (C4, Stage D).

Pure and offline: no LLM, no search, no HTTP. The screen is the whole point
of the tool, so most of what follows asserts a refusal.

The student's data is checked against the *assembled* string rather than
against the arguments, because the leak that matters is whatever would
actually reach a search engine.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.config import STATE_ALUMNI_ANCHOR, STATE_PROFILE
from app.profile_store import empty_profile, write_profile
from app.schemas import ExtractedField
from app.tools.alumni_tools import ALUMNI_SCOPE_TERM, build_alumni_query
from app.tools.profile_tools import save_profile_fields
from app.tools.program_tools import (
    QUERY_SAFE_PROFILE_FIELDS,
    SENSITIVE_PROFILE_FIELDS,
)

DELFT = "TU Delft"
PROGRAM = "MSc Computer Science"
FIELD = "data science"


class StubToolContext:
    """Stand-in exposing only what the C1/C4 tools use."""

    def __init__(self, student_text: str = "") -> None:
        self.state: dict[str, Any] = {}
        self.invocation_id = "test-invocation"
        self.user_content = SimpleNamespace(
            role="user", parts=[SimpleNamespace(text=student_text)]
        )
        self.session = SimpleNamespace(events=[])


@pytest.fixture
def ctx() -> StubToolContext:
    return StubToolContext()


def with_profile(ctx: StubToolContext, **fields: str) -> StubToolContext:
    """Store profile values through the real C1 path, not by hand.

    C1 refuses any value the student did not actually say, so the stub is
    given matching words first. Writing the store directly would let these
    tests pass against a profile shape the real tools never produce.
    """
    ctx.user_content = SimpleNamespace(
        role="user", parts=[SimpleNamespace(text=" ".join(fields.values()))]
    )
    result = save_profile_fields(
        [
            ExtractedField(field_name=name, value=value, evidence_span=value)
            for name, value in fields.items()
        ],
        ctx,
    )
    # A fixture that quietly stores nothing would make every screen test
    # pass for the wrong reason.
    assert result.get("saved"), result
    return ctx


# --- The anchor is required ------------------------------------------------


def test_a_query_without_an_institution_is_refused(ctx: StubToolContext) -> None:
    """No anchor, no search. This is what stops it being people-search."""
    result = build_alumni_query("", PROGRAM, FIELD, ctx)

    assert result["status"] == "error"
    assert result["reason"] == "no_university_anchor"
    assert STATE_ALUMNI_ANCHOR not in ctx.state


def test_whitespace_is_not_an_institution(ctx: StubToolContext) -> None:
    assert build_alumni_query("   ", PROGRAM, FIELD, ctx)["reason"] == (
        "no_university_anchor"
    )


def test_the_institution_alone_is_enough(ctx: StubToolContext) -> None:
    """Program and field are optional; the documented flow scopes by field."""
    result = build_alumni_query(DELFT, "", "", ctx)

    assert result["status"] == "success"
    assert result["query"] == f"{DELFT} {ALUMNI_SCOPE_TERM}"


def test_institution_and_field_without_a_program(ctx: StubToolContext) -> None:
    """Mirrors the architecture's own example: 'TU Delft ... data science'."""
    result = build_alumni_query(DELFT, "", FIELD, ctx)

    assert result["query"] == f"{DELFT} {FIELD} {ALUMNI_SCOPE_TERM}"


# --- Assembly --------------------------------------------------------------


def test_all_three_scoping_terms_are_assembled_in_order(
    ctx: StubToolContext,
) -> None:
    result = build_alumni_query(DELFT, PROGRAM, FIELD, ctx)

    assert result["status"] == "success"
    assert result["query"] == f"{DELFT} {PROGRAM} {FIELD} {ALUMNI_SCOPE_TERM}"


def test_surrounding_whitespace_is_trimmed(ctx: StubToolContext) -> None:
    result = build_alumni_query(f"  {DELFT} ", f" {PROGRAM}", f"{FIELD}  ", ctx)

    assert result["query"] == f"{DELFT} {PROGRAM} {FIELD} {ALUMNI_SCOPE_TERM}"


def test_the_query_asks_for_people_not_for_the_program(
    ctx: StubToolContext,
) -> None:
    """Without a scoping word this returns a program search, not an alumni one."""
    assert build_alumni_query(DELFT, PROGRAM, "", ctx)["query"].endswith(
        ALUMNI_SCOPE_TERM
    )


# --- The privacy screen ----------------------------------------------------


def test_citizenship_can_never_reach_a_query(ctx: StubToolContext) -> None:
    """A protected attribute, and named explicitly by the Stage D plan."""
    with_profile(ctx, citizenship="Bangladesh")

    result = build_alumni_query(DELFT, "MSc for Bangladesh students", "", ctx)

    assert result["status"] == "error"
    assert result["reason"] == "profile_data_in_query"
    assert "citizenship" in result["message"]
    assert STATE_ALUMNI_ANCHOR not in ctx.state


def test_undergrad_institution_can_never_reach_a_query(
    ctx: StubToolContext,
) -> None:
    with_profile(ctx, undergrad_institution="Anna University")

    result = build_alumni_query("Anna University", PROGRAM, "", ctx)

    assert result["reason"] == "profile_data_in_query"
    assert "undergrad_institution" in result["message"]


def test_a_test_score_cannot_be_smuggled_into_the_field(
    ctx: StubToolContext,
) -> None:
    with_profile(ctx, gre_quant="168")

    result = build_alumni_query(DELFT, PROGRAM, "students scoring 168", ctx)

    assert result["reason"] == "profile_data_in_query"
    assert "gre_quant" in result["message"]


def test_the_screen_reads_the_assembled_string_not_one_argument(
    ctx: StubToolContext,
) -> None:
    """The leak is whatever reaches the search engine, wherever it came from."""
    with_profile(ctx, undergrad_institution="Anna University")

    for args in (
        (DELFT, "programme for Anna University graduates", ""),
        ("Anna University", PROGRAM, ""),
        (DELFT, PROGRAM, "Anna University alumni networks"),
    ):
        result = build_alumni_query(*args, ctx)
        assert result["reason"] == "profile_data_in_query", args


def test_a_numeric_profile_value_is_not_caught_by_the_screen(
    ctx: StubToolContext,
) -> None:
    """A known gap in C2's screen, inherited rather than introduced here.

    `budget_ceiling` normalises to the float 25000.0, so the screen compares
    "25000.0" against a query saying "25000" and finds no match. Every
    string-valued sensitive field is caught; only the numeric ones slip, and
    those are the least likely to be phrased into an alumni search.

    Pinned rather than fixed: the screen belongs to C2, and changing it
    would alter C1-C3 behaviour, which Stage D may not do. This test should
    start failing the moment that screen is tightened.
    """
    with_profile(ctx, budget_ceiling="25000")

    assert (
        build_alumni_query(DELFT, "25000 euro programmes", "", ctx)["status"]
        == "success"
    )


@pytest.mark.parametrize("safe", sorted(QUERY_SAFE_PROFILE_FIELDS))
def test_scoping_fields_are_not_treated_as_leaks(
    ctx: StubToolContext, safe: str
) -> None:
    """A student may search in their own target country or specialism.

    These four are scoping terms, not identity. Refusing them would make the
    tool useless without protecting anything.
    """
    values = {
        "target_countries": "Netherlands",
        "specialization_interest": "machine learning",
        "target_intake_term": "Fall",
        "target_intake_year": "2027",
    }
    with_profile(ctx, **{safe: values[safe]})

    result = build_alumni_query(DELFT, PROGRAM, values[safe], ctx)

    assert result["status"] == "success"


def test_an_empty_profile_does_not_block_a_query(ctx: StubToolContext) -> None:
    write_profile(ctx.state, STATE_PROFILE, empty_profile())

    assert build_alumni_query(DELFT, PROGRAM, FIELD, ctx)["status"] == "success"


def test_no_profile_at_all_does_not_crash(ctx: StubToolContext) -> None:
    assert build_alumni_query(DELFT, PROGRAM, FIELD, ctx)["status"] == "success"


def test_the_screen_covers_every_sensitive_registry_field(
    ctx: StubToolContext,
) -> None:
    """Guards the set itself, so a new profile field cannot quietly opt out.

    `citizenship` and `undergrad_institution` are named by the Stage D plan;
    the rest are covered because the screen reads the whole sensitive set
    rather than a hand-listed subset.
    """
    assert "citizenship" in SENSITIVE_PROFILE_FIELDS
    assert "undergrad_institution" in SENSITIVE_PROFILE_FIELDS
    assert not (SENSITIVE_PROFILE_FIELDS & QUERY_SAFE_PROFILE_FIELDS)


# --- The anchor is recorded for the stages that follow ---------------------


def test_a_successful_query_records_its_anchor(ctx: StubToolContext) -> None:
    result = build_alumni_query(DELFT, PROGRAM, FIELD, ctx)

    assert result["anchor"] == {
        "university": DELFT,
        "program": PROGRAM,
        "field": FIELD,
    }
    assert ctx.state[STATE_ALUMNI_ANCHOR] == result["anchor"]


def test_a_refused_query_leaves_no_anchor_behind(ctx: StubToolContext) -> None:
    """A refused query scopes nothing, so nothing may pick it up later."""
    with_profile(ctx, citizenship="Bangladesh")
    build_alumni_query(DELFT, PROGRAM, FIELD, ctx)
    assert STATE_ALUMNI_ANCHOR in ctx.state  # first call succeeded

    ctx.state.pop(STATE_ALUMNI_ANCHOR)
    build_alumni_query("Bangladesh Institute", PROGRAM, FIELD, ctx)

    assert STATE_ALUMNI_ANCHOR not in ctx.state


def test_a_later_query_replaces_the_anchor(ctx: StubToolContext) -> None:
    build_alumni_query(DELFT, PROGRAM, FIELD, ctx)
    build_alumni_query("ETH Zurich", "MSc Robotics", "", ctx)

    assert ctx.state[STATE_ALUMNI_ANCHOR] == {
        "university": "ETH Zurich",
        "program": "MSc Robotics",
        "field": "",
    }


def test_the_anchor_is_session_scoped_not_user_scoped() -> None:
    """The scope belongs to the question, not to the student."""
    assert not STATE_ALUMNI_ANCHOR.startswith("user:")


# --- Determinism -----------------------------------------------------------


def test_repeated_calls_produce_identical_output(ctx: StubToolContext) -> None:
    first = build_alumni_query(DELFT, PROGRAM, FIELD, ctx)
    second = build_alumni_query(DELFT, PROGRAM, FIELD, ctx)

    assert first == second


def test_two_independent_contexts_agree() -> None:
    def run() -> dict[str, Any]:
        ctx = StubToolContext()
        with_profile(ctx, gpa_value="8.1", citizenship="India")
        return build_alumni_query(DELFT, PROGRAM, FIELD, ctx)

    assert run() == run()


def test_the_tool_makes_no_network_call(
    ctx: StubToolContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Stage D is offline by contract."""
    import urllib.request

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("Stage D must not touch the network")

    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    monkeypatch.setattr(urllib.request, "build_opener", forbidden)

    assert build_alumni_query(DELFT, PROGRAM, FIELD, ctx)["status"] == "success"


# --- Stage A-C regression --------------------------------------------------


def test_query_construction_does_not_disturb_c1_to_c3_state(
    ctx: StubToolContext,
) -> None:
    with_profile(ctx, gpa_value="8.1")
    before = dict(ctx.state[STATE_PROFILE])
    ctx.state["shortlist"] = {"programs": ["delft-cs"]}

    build_alumni_query(DELFT, PROGRAM, FIELD, ctx)

    assert ctx.state[STATE_PROFILE] == before
    assert ctx.state["shortlist"] == {"programs": ["delft-cs"]}


def test_stage_d_stores_no_alumni_records(ctx: StubToolContext) -> None:
    """Query construction is not an admission path."""
    from app.config import STATE_ALUMNI

    build_alumni_query(DELFT, PROGRAM, FIELD, ctx)

    assert STATE_ALUMNI not in ctx.state


# --- Recall: a query must not fight itself ---------------------------------
#
# Found in the first live run. The root passed program='MSc Computer Science'
# and field='Computer Science', which assembled to "TU Delft MSc Computer
# Science Computer Science alumni" — a query so over-constrained that a
# program with real, indexed alumni pages returned nobody. Repeating a term
# adds no scope and costs recall, and recall is what makes an empty result
# honest rather than an artifact.


def test_a_term_repeated_across_scope_arguments_appears_once(
    ctx: StubToolContext,
) -> None:
    result = build_alumni_query(DELFT, "MSc Computer Science", "Computer Science", ctx)
    assert result["query"] == "TU Delft MSc Computer Science alumni"


def test_deduplication_is_case_insensitive(ctx: StubToolContext) -> None:
    result = build_alumni_query(DELFT, "MSc Computer Science", "computer science", ctx)
    assert result["query"] == "TU Delft MSc Computer Science alumni"


def test_a_field_that_adds_scope_is_kept(ctx: StubToolContext) -> None:
    result = build_alumni_query(DELFT, "MSc Computer Science", "data science", ctx)
    assert result["query"] == "TU Delft MSc Computer Science data science alumni"


def test_a_partly_overlapping_phrase_survives_intact(
    ctx: StubToolContext,
) -> None:
    """Only a fully-covered part is dropped; a phrase is never half-eaten.

    Trimming the shared word would leave `data`, which is not the field
    anyone asked about.
    """
    result = build_alumni_query(DELFT, "MSc Computer Science", "data science", ctx)
    assert "data science" in result["query"]


def test_the_university_is_never_dropped_by_deduplication(
    ctx: StubToolContext,
) -> None:
    """The anchor leads the query even when a later part repeats it."""
    result = build_alumni_query("Delft", "Delft MSc", "", ctx)
    assert result["query"].startswith("Delft ")
    assert result["query"].endswith(ALUMNI_SCOPE_TERM)


def test_the_anchor_still_records_what_was_asked_for(ctx: StubToolContext) -> None:
    """Deduplication changes the query, never the recorded scope."""
    result = build_alumni_query(DELFT, "MSc Computer Science", "Computer Science", ctx)
    assert result["anchor"] == {
        "university": DELFT,
        "program": "MSc Computer Science",
        "field": "Computer Science",
    }
    assert ctx.state[STATE_ALUMNI_ANCHOR]["field"] == "Computer Science"
