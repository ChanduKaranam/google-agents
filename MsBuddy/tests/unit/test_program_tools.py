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

"""C2 tools: query isolation, citation verification, shortlist state."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.config import STATE_SHORTLIST
from app.schemas import ClaimTier, ExtractedField, ProgramClaim
from app.tools import (
    build_program_query,
    get_shortlist,
    save_profile_fields,
    save_program_record,
)

ETH_URI = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZ1"
AGG_URI = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZ2"

DEADLINE_TEXT = "The application deadline for the Autumn Semester is 15 December 2026."
TUITION_TEXT = "Tuition is CHF 1460 per semester for all students."


def grounding_event(pairs: list[tuple[str, str, str]]) -> SimpleNamespace:
    """pairs: (domain, uri, supported_segment)."""
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
            web_search_queries=["eth zurich msc computer science deadline"],
        )
    )


class StubToolContext:
    """Stand-in exposing only what the C2 tools use."""

    def __init__(self, events: list[Any] | None = None, student_text: str = "") -> None:
        self.state: dict[str, Any] = {}
        self.invocation_id = "test-invocation"
        self.user_content = SimpleNamespace(
            role="user", parts=[SimpleNamespace(text=student_text)]
        )
        self.session = SimpleNamespace(events=events or [])


@pytest.fixture
def grounded() -> StubToolContext:
    return StubToolContext(
        events=[
            grounding_event(
                [
                    ("ethz.ch", ETH_URI, DEADLINE_TEXT),
                    ("shiksha.com", AGG_URI, TUITION_TEXT),
                ]
            )
        ]
    )


def claim(field: str, value: str, domain: str, quote: str) -> ProgramClaim:
    return ProgramClaim(
        field_name=field, value=value, source_domain=domain, supporting_quote=quote
    )


# --- build_program_query: privacy isolation --------------------------------


def test_query_is_assembled_from_scoping_terms() -> None:
    ctx = StubToolContext()
    result = build_program_query(
        "ETH Zurich", "MSc Computer Science", "Switzerland", "Fall 2027", ctx
    )
    assert result["status"] == "success"
    assert result["query"] == "ETH Zurich MSc Computer Science Switzerland Fall 2027"


def test_empty_query_is_refused() -> None:
    assert build_program_query("", "", "", "", StubToolContext())["status"] == "error"


def test_query_containing_the_students_institution_is_refused() -> None:
    """Spec §5.2 invariant 1 — search agents never receive student PII."""
    ctx = StubToolContext(student_text="I studied at Anna University with 8.1 CGPA")
    save_profile_fields(
        [
            ExtractedField(
                field_name="undergrad_institution",
                value="Anna University",
                evidence_span="Anna University",
            )
        ],
        ctx,
    )
    result = build_program_query("Anna University", "MSc Data Science", "", "", ctx)
    assert result["status"] == "error"
    assert result["reason"] == "profile_data_in_query"
    assert "undergrad_institution" in result["message"]


def test_query_containing_the_students_citizenship_is_refused() -> None:
    ctx = StubToolContext(student_text="I am a citizen of Bangladesh")
    save_profile_fields(
        [
            ExtractedField(
                field_name="citizenship",
                value="Bangladesh",
                evidence_span="citizen of Bangladesh",
            )
        ],
        ctx,
    )
    assert build_program_query("", "MSc CS", "Bangladesh", "", ctx)["status"] == "error"


def test_scoping_fields_are_allowed_in_a_query() -> None:
    """Target country and specialisation are scope, not private data."""
    ctx = StubToolContext(student_text="I want Data Science in Canada")
    save_profile_fields(
        [
            ExtractedField(
                field_name="target_countries", value="Canada", evidence_span="in Canada"
            ),
            ExtractedField(
                field_name="specialization_interest",
                value="Data Science",
                evidence_span="Data Science",
            ),
        ],
        ctx,
    )
    result = build_program_query("UBC", "Data Science", "Canada", "", ctx)
    assert result["status"] == "success"


# --- save_program_record: citation verification ----------------------------


def test_verified_tier_for_an_official_source(grounded: StubToolContext) -> None:
    result = save_program_record(
        "ETH Zurich",
        "MSc Computer Science",
        [
            claim(
                "application_deadline",
                "15 December 2026",
                "ethz.ch",
                "deadline for the Autumn Semester is 15 December 2026",
            )
        ],
        grounded,
    )
    assert result["status"] == "success"
    assert result["saved"][0]["tier"] == ClaimTier.VERIFIED.value
    stored = grounded.state[STATE_SHORTLIST]["programs"]
    assert stored["eth-zurich-msc-computer-science"]["fields"]["application_deadline"]


def test_reported_tier_for_an_aggregator_source(grounded: StubToolContext) -> None:
    """An aggregator fact is recorded, but never as VERIFIED (spec §7.1)."""
    result = save_program_record(
        "ETH Zurich",
        "MSc Computer Science",
        [
            claim(
                "tuition_amount",
                "1460",
                "shiksha.com",
                "Tuition is CHF 1460 per semester",
            )
        ],
        grounded,
    )
    assert result["saved"][0]["tier"] == ClaimTier.REPORTED.value


def test_claim_quoting_text_that_was_never_retrieved_is_refused(
    grounded: StubToolContext,
) -> None:
    """The central C2 guarantee — a fabricated deadline cannot be stored."""
    result = save_program_record(
        "ETH Zurich",
        "MSc Computer Science",
        [
            claim(
                "application_deadline",
                "1 November 2026",
                "ethz.ch",
                "the deadline is 1 November 2026",
            )
        ],
        grounded,
    )
    assert result["status"] == "error"
    assert result["saved"] == []
    assert result["rejected"][0]["reason"] == "unsupported_claim"
    assert STATE_SHORTLIST not in grounded.state


def test_claim_naming_a_domain_that_was_never_fetched_is_refused(
    grounded: StubToolContext,
) -> None:
    result = save_program_record(
        "ETH Zurich",
        "MSc Computer Science",
        [
            claim(
                "application_deadline",
                "15 December 2026",
                "mit.edu",
                "deadline for the Autumn Semester is 15 December 2026",
            )
        ],
        grounded,
    )
    assert result["rejected"][0]["reason"] == "unsupported_claim"
    assert "ethz.ch" in result["rejected"][0]["message"]


def test_quote_cannot_be_re_attributed_to_a_more_trusted_domain(
    grounded: StubToolContext,
) -> None:
    """Aggregator text must not be laundered into a VERIFIED claim."""
    result = save_program_record(
        "ETH Zurich",
        "MSc Computer Science",
        [
            claim(
                "tuition_amount", "1460", "ethz.ch", "Tuition is CHF 1460 per semester"
            )
        ],
        grounded,
    )
    assert result["rejected"][0]["reason"] == "unsupported_claim"


def test_nothing_can_be_stored_when_no_search_happened() -> None:
    """No grounding in the session means every claim is model memory."""
    result = save_program_record(
        "ETH Zurich",
        "MSc Computer Science",
        [claim("application_deadline", "15 December 2026", "ethz.ch", "deadline")],
        StubToolContext(),
    )
    assert result["status"] == "error"
    assert result["reason"] == "no_sources_retrieved"


def test_unknown_program_field_is_refused(grounded: StubToolContext) -> None:
    result = save_program_record(
        "ETH Zurich",
        "MSc Computer Science",
        [
            claim(
                "acceptance_rate",
                "12%",
                "ethz.ch",
                "deadline for the Autumn Semester is 15 December 2026",
            )
        ],
        grounded,
    )
    assert result["rejected"][0]["reason"] == "unknown_field"


def test_partial_status_when_only_some_claims_verify(grounded: StubToolContext) -> None:
    result = save_program_record(
        "ETH Zurich",
        "MSc Computer Science",
        [
            claim(
                "application_deadline",
                "15 December 2026",
                "ethz.ch",
                "deadline for the Autumn Semester is 15 December 2026",
            ),
            claim("tuition_amount", "99999", "ethz.ch", "tuition is 99999 francs"),
        ],
        grounded,
    )
    assert result["status"] == "partial"
    assert len(result["saved"]) == 1
    assert len(result["rejected"]) == 1


def test_unknown_fields_are_named_not_omitted(grounded: StubToolContext) -> None:
    """C2: a gap in coverage must never read as an absence of a requirement."""
    result = save_program_record(
        "ETH Zurich",
        "MSc Computer Science",
        [
            claim(
                "application_deadline",
                "15 December 2026",
                "ethz.ch",
                "deadline for the Autumn Semester is 15 December 2026",
            )
        ],
        grounded,
    )
    unknown = result["record"]["unknown_fields"]
    assert "tuition_amount" in unknown
    assert "prerequisites" in unknown
    assert "application_deadline" not in unknown


def test_accepts_plain_dicts_as_well_as_models(grounded: StubToolContext) -> None:
    result = save_program_record(
        "ETH Zurich",
        "MSc Computer Science",
        [
            {
                "field_name": "application_deadline",
                "value": "15 December 2026",
                "source_domain": "ethz.ch",
                "supporting_quote": "deadline for the Autumn Semester is 15 December 2026",
            }
        ],
        grounded,
    )
    assert result["status"] == "success"


def test_empty_claim_list_is_an_error(grounded: StubToolContext) -> None:
    assert save_program_record("ETH", "MSc", [], grounded)["status"] == "error"


# --- get_shortlist ---------------------------------------------------------


def test_shortlist_starts_empty() -> None:
    result = get_shortlist(StubToolContext())
    assert result["is_empty"] is True
    assert result["program_count"] == 0


def test_shortlist_renders_provenance(grounded: StubToolContext) -> None:
    save_program_record(
        "ETH Zurich",
        "MSc Computer Science",
        [
            claim(
                "application_deadline",
                "15 December 2026",
                "ethz.ch",
                "deadline for the Autumn Semester is 15 December 2026",
            )
        ],
        grounded,
    )
    program = get_shortlist(grounded)["programs"][0]
    field = program["fields"]["application_deadline"]
    assert field["tier"] == "VERIFIED"
    assert field["source_domain"] == "ethz.ch"
    assert field["source_is_official"] is True
    assert field["is_stale"] is False
    assert field["supporting_quote"]
    assert program["verified_count"] == 1
