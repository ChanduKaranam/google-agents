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

"""The whole C4 path, end to end, with the network unplugged.

`test_alumni_tools.py` covers the admission gate one rule at a time. This
file covers the *path*: query → discovery output → admission → ranking →
read, in the order the root instruction actually calls them, against one
stubbed harvest. It is the offline half of the CEO demo — the same sequence
the live flows exercise, minus the model.

Grounding is stubbed in the shape `harvest_metadata` consumes, and redirect
resolution is replaced by a stub that always fails, so nothing here opens a
socket.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.config import MIN_PATTERN_N, STATE_ALUMNI_ANCHOR, STATE_PROFILE
from app.schemas import AlumniCandidate, AlumniClaimInput
from app.tools import alumni_tools
from app.tools.alumni_tools import (
    build_alumni_query,
    get_alumni,
    rank_alumni_by_affinity,
    save_alumni_records,
)

DELFT = "TU Delft"
DELFT_DOMAIN = "tudelft.nl"
BOOKING_DOMAIN = "booking.com"

# Each segment names the person *and* states the claim, because the
# same-segment rule is what stops a name in one sentence acquiring a fact
# from another.
ANNA_DELFT = (
    "Anna de Vries completed the MSc Computer Science at TU Delft in 2021, "
    "after a BTech in Computer Engineering at Anna University."
)
ANNA_BOOKING = (
    "Anna de Vries is a machine learning engineer at Booking.com, where she "
    "has worked since 2021."
)
BRAM_DELFT = "Bram Jansen graduated from the MSc Computer Science at TU Delft in 2020."
GHOST = "The Faculty of EEMCS publishes an annual alumni newsletter."

HARVEST: list[tuple[str, str, str]] = [
    (DELFT_DOMAIN, "https://x/1", ANNA_DELFT),
    (BOOKING_DOMAIN, "https://x/2", ANNA_BOOKING),
    (DELFT_DOMAIN, "https://x/3", BRAM_DELFT),
    (DELFT_DOMAIN, "https://x/4", GHOST),
]


def grounding_event(pairs: list[tuple[str, str, str]]) -> SimpleNamespace:
    chunks = [
        SimpleNamespace(web=SimpleNamespace(domain=None, title=d, uri=u))
        for d, u, _ in pairs
    ]
    supports = [
        SimpleNamespace(segment=SimpleNamespace(text=seg), grounding_chunk_indices=[i])
        for i, (_, _, seg) in enumerate(pairs)
    ]
    return SimpleNamespace(
        grounding_metadata=SimpleNamespace(
            grounding_chunks=chunks,
            grounding_supports=supports,
            web_search_queries=["tu delft msc computer science alumni"],
        )
    )


class StubToolContext:
    """Stand-in exposing only what the C4 tools use."""

    def __init__(self, events: list[Any] | None = None) -> None:
        self.state: dict[str, Any] = {}
        self.invocation_id = "test-invocation"
        self.session = SimpleNamespace(events=events or [])


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """No test in this module may open a socket."""
    monkeypatch.setattr(alumni_tools, "_head_location", lambda url: None)


@pytest.fixture
def context() -> StubToolContext:
    ctx = StubToolContext(events=[grounding_event(HARVEST)])
    ctx.state[STATE_PROFILE] = {
        "fields": {
            "undergrad_institution": {"value": "Anna University"},
            "undergrad_degree": {"value": "Computer Engineering"},
            "specialization_interest": {"value": "Computer Science"},
            "citizenship": {"value": "India"},
            "gpa_value": {"value": 8.1},
        }
    }
    return ctx


def claim(
    field: str, value: str, quote: str, domain: str = DELFT_DOMAIN
) -> AlumniClaimInput:
    return AlumniClaimInput(
        field_name=field, value=value, source_domain=domain, supporting_quote=quote
    )


def anna() -> AlumniCandidate:
    return AlumniCandidate(
        name="Anna de Vries",
        university=DELFT,
        claims=[
            claim("university_affiliation", "TU Delft", ANNA_DELFT),
            claim("program", "MSc Computer Science", ANNA_DELFT),
            claim("graduation_year", "2021", ANNA_DELFT),
            claim("prior_institution", "Anna University", ANNA_DELFT),
            claim("prior_degree", "Computer Engineering", ANNA_DELFT),
            claim("employer", "Booking.com", ANNA_BOOKING, domain=BOOKING_DOMAIN),
        ],
    )


def bram() -> AlumniCandidate:
    return AlumniCandidate(
        name="Bram Jansen",
        university=DELFT,
        claims=[
            claim("university_affiliation", "TU Delft", BRAM_DELFT),
            claim("program", "MSc Computer Science", BRAM_DELFT),
            claim("graduation_year", "2020", BRAM_DELFT),
        ],
    )


def fabricated() -> AlumniCandidate:
    """The failure C4 exists to prevent: a plausible person no source names."""
    return AlumniCandidate(
        name="Sanne Bakker",
        university=DELFT,
        claims=[
            claim("university_affiliation", "TU Delft", GHOST),
            claim("employer", "Google", GHOST),
        ],
    )


# --- Step 1: the query -----------------------------------------------------


def test_the_query_is_assembled_from_scope_terms_only(
    context: StubToolContext,
) -> None:
    result = build_alumni_query(DELFT, "MSc Computer Science", "", context)
    assert result["status"] == "success"
    assert result["query"] == "TU Delft MSc Computer Science alumni"


def test_the_query_refuses_to_carry_the_students_own_institution(
    context: StubToolContext,
) -> None:
    """The student's undergrad institution is theirs, not a search term."""
    result = build_alumni_query("Anna University", "", "", context)
    assert result["status"] == "error"
    assert result["reason"] == "profile_data_in_query"


def test_a_refused_query_leaves_no_anchor_behind(context: StubToolContext) -> None:
    build_alumni_query("Anna University", "", "", context)
    assert STATE_ALUMNI_ANCHOR not in context.state


# --- Step 2-3: admission ---------------------------------------------------


def test_the_whole_path_admits_the_supported_people_and_refuses_the_rest(
    context: StubToolContext,
) -> None:
    """One call, three candidates, and only the evidenced two survive."""
    result = save_alumni_records([anna(), bram(), fabricated()], context)

    assert result["status"] == "partial"
    assert sorted(a["name"] for a in result["admitted"]) == [
        "Anna de Vries",
        "Bram Jansen",
    ]
    assert [r["name"] for r in result["rejected"]] == ["Sanne Bakker"]


def test_the_fabricated_person_is_refused_for_being_in_no_source(
    context: StubToolContext,
) -> None:
    refusal = save_alumni_records([fabricated()], context)["rejected"][0]
    assert refusal["admitted"] is False
    assert refusal["reason"] == "no_verifiable_claim"
    assert [c["reason"] for c in refusal["rejected_claims"]] == [
        "name_not_in_source",
        "name_not_in_source",
    ]


def test_the_fabricated_person_reaches_no_stored_state(
    context: StubToolContext,
) -> None:
    save_alumni_records([anna(), fabricated()], context)
    stored = {p["name_as_published"] for p in get_alumni(context)["people"]}
    assert "Sanne Bakker" not in stored


def test_field_authority_is_applied_per_source(context: StubToolContext) -> None:
    """A university verifies what someone studied; an employer's own site
    verifies where they work. Neither verifies the other."""
    save_alumni_records([anna()], context)
    fields = get_alumni(context)["people"][0]["fields"]

    assert fields["program"]["tier"] == "VERIFIED"
    assert fields["program"]["source_domain"] == DELFT_DOMAIN
    assert fields["employer"]["tier"] == "VERIFIED"
    assert fields["employer"]["source_domain"] == BOOKING_DOMAIN


def test_the_university_page_could_not_have_verified_the_employer(
    context: StubToolContext,
) -> None:
    """The reverse claim, from the wrong source, is REPORTED at best."""
    candidate = AlumniCandidate(
        name="Anna de Vries",
        university=DELFT,
        claims=[
            claim("university_affiliation", "TU Delft", ANNA_DELFT),
            claim("employer", "Booking.com", ANNA_BOOKING, domain=BOOKING_DOMAIN),
        ],
    )
    save_alumni_records([candidate], context)
    # Re-stating the same employer from the university's own page must not
    # promote it, and must not be silently dropped either.
    assert get_alumni(context)["people"][0]["fields"]["employer"]["tier"] == "VERIFIED"


# --- Step 4: ranking -------------------------------------------------------


def test_ranking_puts_the_student_s_closest_match_first(
    context: StubToolContext,
) -> None:
    save_alumni_records([anna(), bram()], context)
    ranked = rank_alumni_by_affinity(context)["people"]

    assert ranked[0]["name_as_published"] == "Anna de Vries"
    assert [m["anchor"] for m in ranked[0]["matched_anchors"]] == [
        "undergrad_institution",
        "undergrad_field",
        "specialization",
    ]


def test_ranking_explains_each_match_in_words(context: StubToolContext) -> None:
    save_alumni_records([anna()], context)
    rationales = " ".join(
        m["rationale"]
        for m in rank_alumni_by_affinity(context)["people"][0]["matched_anchors"]
    )
    assert "Anna University" in rationales
    assert "same undergraduate institution" in rationales


def test_ranking_keeps_the_weaker_match_and_says_what_it_was(
    context: StubToolContext,
) -> None:
    """Affinity orders a result; it never filters one.

    Bram shares one anchor to Anna's three. He ranks second and stays, with
    the single match spelled out — including that his program is published
    with a qualifier the student's phrasing does not have.
    """
    save_alumni_records([anna(), bram()], context)
    ranked = rank_alumni_by_affinity(context)["people"]
    assert len(ranked) == 2
    assert ranked[1]["matched_anchors"] == [
        {
            "anchor": "specialization",
            "label": "same specialization",
            "student_value": "Computer Science",
            "alumni_value": "MSc Computer Science",
            "tier": "VERIFIED",
            "source_domain": DELFT_DOMAIN,
            "rationale": (
                "same specialization — you: Computer Science; them: MSc Computer Science"
            ),
        }
    ]


def test_ranking_never_anchors_on_a_protected_attribute(
    context: StubToolContext,
) -> None:
    """`citizenship` is in the stub profile and must never be matched on."""
    save_alumni_records([anna()], context)
    result = rank_alumni_by_affinity(context)
    assert "citizenship" not in result["anchors_matched_on"]
    assert "citizenship" not in str(result["people"][0]["matched_anchors"])


def test_ranking_an_empty_store_is_a_valid_answer(context: StubToolContext) -> None:
    result = rank_alumni_by_affinity(context)
    assert result["status"] == "success"
    assert result["is_empty"] is True
    assert result["people"] == []


# --- Step 5: the read, and what the root is handed -------------------------


def test_the_read_path_always_carries_the_denominator(
    context: StubToolContext,
) -> None:
    save_alumni_records([anna(), bram()], context)
    summary = get_alumni(context)["summary"]

    assert summary["person_count"] == 2
    assert summary["field_coverage"]["employer"] == {"known": 1, "of": 2}
    assert summary["selection_bias_notice"]


def test_a_small_result_forbids_pattern_language(context: StubToolContext) -> None:
    save_alumni_records([anna(), bram()], context)
    summary = get_alumni(context)["summary"]
    assert summary["may_use_pattern_language"] is False
    assert summary["pattern_language_threshold"] == MIN_PATTERN_N


def test_unknown_fields_are_named_rather_than_omitted(
    context: StubToolContext,
) -> None:
    save_alumni_records([bram()], context)
    person = get_alumni(context)["people"][0]
    assert "employer" in person["unknown_fields"]
    assert "role" in person["unknown_fields"]


def test_every_stored_fact_carries_its_source_and_quote(
    context: StubToolContext,
) -> None:
    """Nothing reaches the student without the evidence that admitted it."""
    save_alumni_records([anna(), bram()], context)
    for person in get_alumni(context)["people"]:
        for name, field in person["fields"].items():
            assert field["source_domain"], name
            assert field["supporting_quote"], name
            assert field["retrieved_at"], name
            assert field["tier"] in ("VERIFIED", "REPORTED"), name


def test_no_contact_detail_survives_the_path(context: StubToolContext) -> None:
    """The employer segment carries no address, but the rule is structural."""
    save_alumni_records([anna(), bram()], context)
    rendered = str(get_alumni(context))
    assert "@tudelft.nl" not in rendered
    assert "linkedin" not in rendered.lower()


# --- The path is idempotent and does not disturb C1-C3 ---------------------


def test_running_the_path_twice_stores_one_copy_of_each_person(
    context: StubToolContext,
) -> None:
    save_alumni_records([anna(), bram()], context)
    save_alumni_records([anna(), bram()], context)

    people = get_alumni(context)["people"]
    assert [p["name_as_published"] for p in people] == ["Anna de Vries", "Bram Jansen"]


def test_the_alumni_path_never_writes_to_the_profile(
    context: StubToolContext,
) -> None:
    before = dict(context.state[STATE_PROFILE])
    save_alumni_records([anna(), bram()], context)
    rank_alumni_by_affinity(context)
    assert context.state[STATE_PROFILE] == before
