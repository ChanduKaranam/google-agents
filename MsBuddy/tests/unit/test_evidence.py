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

"""Grounding harvest, evidence records and staleness (spec §7.2, §7.3)."""

from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

from app.config import MAX_RETRIEVED_SEGMENT_CHARS
from app.evidence import (
    STALENESS_TTL_DAYS,
    evaluate_staleness,
    find_supporting_source,
    harvest_grounding,
    make_claim_id,
    make_evidence_record,
    retrieved_domains,
    tier_for_source,
)
from app.schemas import ClaimTier


def chunk(domain_title: str, uri: str) -> SimpleNamespace:
    """A grounding chunk shaped like the real thing: `domain` is None."""
    return SimpleNamespace(
        web=SimpleNamespace(domain=None, title=domain_title, uri=uri)
    )


def support(text: str, indices: list[int]) -> SimpleNamespace:
    return SimpleNamespace(
        segment=SimpleNamespace(text=text), grounding_chunk_indices=indices
    )


def session_with(chunks: list, supports: list, queries: list[str]) -> SimpleNamespace:
    return SimpleNamespace(
        events=[
            SimpleNamespace(
                grounding_metadata=SimpleNamespace(
                    grounding_chunks=chunks,
                    grounding_supports=supports,
                    web_search_queries=queries,
                )
            )
        ]
    )


ETH_URI = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZ123"
AGG_URI = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZ456"


# --- Harvest ---------------------------------------------------------------


def test_domain_is_read_from_title_when_domain_is_none() -> None:
    """Vertex leaves `domain` empty and puts the host in `title`."""
    session = session_with(
        [chunk("ethz.ch", ETH_URI)],
        [support("The deadline is 15 December 2026.", [0])],
        ["eth zurich msc deadline"],
    )
    harvest = harvest_grounding(session)
    assert retrieved_domains(harvest) == {"ethz.ch"}
    assert harvest[0]["is_official"] is True
    assert harvest[0]["uris"] == [ETH_URI]
    assert harvest[0]["queries"] == ["eth zurich msc deadline"]


def test_official_and_aggregator_sources_are_separated() -> None:
    session = session_with(
        [chunk("ethz.ch", ETH_URI), chunk("libertify.com", AGG_URI)],
        [support("Tuition is CHF 1460 per year.", [0, 1])],
        ["eth tuition"],
    )
    harvest = harvest_grounding(session)
    by_domain = {e["domain"]: e for e in harvest}
    assert by_domain["ethz.ch"]["is_official"] is True
    assert by_domain["libertify.com"]["source_class"] == "aggregator"
    assert by_domain["libertify.com"]["is_official"] is False


def test_segments_attach_to_the_chunks_that_supported_them() -> None:
    session = session_with(
        [chunk("ethz.ch", ETH_URI), chunk("shiksha.com", AGG_URI)],
        [support("Official text.", [0]), support("Aggregator text.", [1])],
        [],
    )
    by_domain = {e["domain"]: e for e in harvest_grounding(session)}
    assert by_domain["ethz.ch"]["segments"] == ["Official text."]
    assert by_domain["shiksha.com"]["segments"] == ["Aggregator text."]


def test_google_redirect_host_is_never_treated_as_a_source() -> None:
    session = session_with([chunk("vertexaisearch.cloud.google.com", ETH_URI)], [], [])
    assert harvest_grounding(session) == []


def test_events_without_grounding_are_ignored() -> None:
    session = SimpleNamespace(
        events=[SimpleNamespace(grounding_metadata=None), SimpleNamespace()]
    )
    assert harvest_grounding(session) == []


def test_harvest_tolerates_a_missing_session() -> None:
    assert harvest_grounding(None) == []
    assert harvest_grounding(SimpleNamespace()) == []


def test_long_segments_are_truncated() -> None:
    session = session_with([chunk("ethz.ch", ETH_URI)], [support("x" * 9000, [0])], [])
    segment = harvest_grounding(session)[0]["segments"][0]
    assert len(segment) < 9000
    assert segment.endswith("truncated]")
    assert len(segment) <= MAX_RETRIEVED_SEGMENT_CHARS + 20


# --- Supporting-source lookup ----------------------------------------------


def make_harvest() -> list[dict]:
    return harvest_grounding(
        session_with(
            [chunk("ethz.ch", ETH_URI)],
            [support("The application deadline is 15 December 2026.", [0])],
            ["eth deadline"],
        )
    )


def test_quote_present_on_the_named_domain_is_supported() -> None:
    assert find_supporting_source(
        make_harvest(), "deadline is 15 December 2026", "ethz.ch"
    )


def test_quote_matching_is_case_and_space_insensitive() -> None:
    assert find_supporting_source(
        make_harvest(), "DEADLINE   IS 15 december 2026", "ethz.ch"
    )


def test_quote_absent_from_the_source_is_not_supported() -> None:
    """A plausible but never-retrieved deadline must find no support."""
    assert (
        find_supporting_source(make_harvest(), "deadline is 1 November 2026", "ethz.ch")
        is None
    )


def test_right_quote_but_wrong_domain_is_not_supported() -> None:
    """A real quote cannot be re-attributed to a source that never said it."""
    assert (
        find_supporting_source(
            make_harvest(), "deadline is 15 December 2026", "shiksha.com"
        )
        is None
    )


def test_empty_quote_is_not_supported() -> None:
    assert find_supporting_source(make_harvest(), "   ", "ethz.ch") is None


# --- Tiers and records -----------------------------------------------------


def test_tier_follows_source_class() -> None:
    assert tier_for_source("official") is ClaimTier.VERIFIED
    assert tier_for_source("aggregator") is ClaimTier.REPORTED
    assert tier_for_source("unknown") is ClaimTier.REPORTED


def test_claim_id_is_stable_and_value_sensitive() -> None:
    first = make_claim_id("eth-msc-cs", "application_deadline", "15 Dec 2026")
    assert first == make_claim_id("eth-msc-cs", "application_deadline", "15 Dec 2026")
    assert first != make_claim_id("eth-msc-cs", "application_deadline", "1 Nov 2026")


def test_evidence_record_carries_the_full_spec_field_set() -> None:
    source = make_harvest()[0]
    record = make_evidence_record(
        "eth-msc-cs",
        "application_deadline",
        "15 December 2026",
        "deadline is 15 December 2026",
        source,
        "VOLATILE",
        "program_research_agent",
    )
    for key in (
        "claim_id",
        "claim_text",
        "tier",
        "source_url",
        "source_domain",
        "source_is_official",
        "retrieved_at",
        "content_date",
        "retrieval_query",
        "agent_name",
        "staleness_class",
        "superseded_by",
    ):
        assert key in record, f"spec §7.2 field '{key}' missing"
    assert record["tier"] == "VERIFIED"
    assert record["source_domain"] == "ethz.ch"


def test_record_flags_that_the_url_is_a_google_redirect() -> None:
    """The reader must not be misled about what the citation links to."""
    record = make_evidence_record(
        "p",
        "duration",
        "2 years",
        "deadline is 15 December 2026",
        make_harvest()[0],
        "CYCLICAL",
        "program_research_agent",
    )
    assert record["url_is_grounding_redirect"] is True


# --- Staleness -------------------------------------------------------------


def aged_record(days: int, klass: str) -> dict:
    stamp = dt.datetime.now(dt.UTC) - dt.timedelta(days=days)
    return {
        "retrieved_at": stamp.isoformat(timespec="seconds"),
        "staleness_class": klass,
    }


def test_fresh_records_carry_no_notice() -> None:
    result = evaluate_staleness(aged_record(1, "VOLATILE"))
    assert result["is_stale"] is False
    assert result["notice"] is None


def test_deadlines_go_stale_within_a_fortnight() -> None:
    result = evaluate_staleness(aged_record(10, "VOLATILE"))
    assert result["is_stale"] is True
    assert "re-check" in result["notice"].lower()


def test_each_class_uses_its_own_ttl() -> None:
    for klass, ttl in STALENESS_TTL_DAYS.items():
        assert evaluate_staleness(aged_record(ttl - 1, klass))["is_stale"] is False
        assert evaluate_staleness(aged_record(ttl + 1, klass))["is_stale"] is True


def test_slow_facts_survive_where_volatile_ones_do_not() -> None:
    assert evaluate_staleness(aged_record(100, "VOLATILE"))["is_stale"] is True
    assert evaluate_staleness(aged_record(100, "SLOW"))["is_stale"] is False


def test_unreadable_timestamp_is_treated_as_stale() -> None:
    """Fail safe: an unknown age is never assumed to be fresh."""
    result = evaluate_staleness(
        {"retrieved_at": "not a date", "staleness_class": "SLOW"}
    )
    assert result["is_stale"] is True
    assert result["notice"]
