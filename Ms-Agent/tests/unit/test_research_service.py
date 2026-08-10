"""Evidence grading — offline, driven by stubbed grounding metadata."""

from __future__ import annotations

from types import SimpleNamespace

from app.services.research_service import (
    build_fact,
    classify_source,
    harvest_grounding,
    normalize_domain,
    verify_claim,
)

TORONTO_SEGMENT = (
    "The MSc in Applied Computing at the University of Toronto has an "
    "application deadline of December 1 and requires IELTS 7.0."
)


def grounding_event(pairs: list[tuple[str, str]]) -> SimpleNamespace:
    chunks = [
        SimpleNamespace(web=SimpleNamespace(domain=None, title=d, uri=f"https://x/{i}"))
        for i, (d, _) in enumerate(pairs)
    ]
    supports = [
        SimpleNamespace(segment=SimpleNamespace(text=seg), grounding_chunk_indices=[i])
        for i, (_, seg) in enumerate(pairs)
    ]
    return SimpleNamespace(
        grounding_metadata=SimpleNamespace(
            grounding_chunks=chunks, grounding_supports=supports
        )
    )


def session_with(pairs: list[tuple[str, str]]) -> SimpleNamespace:
    return SimpleNamespace(events=[grounding_event(pairs)])


def test_harvest_collects_domains_and_their_segments() -> None:
    harvest = harvest_grounding(session_with([("utoronto.ca", TORONTO_SEGMENT)]))
    assert len(harvest) == 1
    assert harvest[0]["domain"] == "utoronto.ca"
    assert TORONTO_SEGMENT in harvest[0]["segments"]


def test_harvest_of_nothing_is_empty_not_an_error() -> None:
    assert harvest_grounding(SimpleNamespace(events=[])) == []
    assert harvest_grounding(None) == []


def test_domain_normalization() -> None:
    assert normalize_domain("https://www.UToronto.ca/grad") == "utoronto.ca"


def test_a_value_in_attributed_text_is_verified() -> None:
    harvest = harvest_grounding(session_with([("utoronto.ca", TORONTO_SEGMENT)]))
    assert verify_claim("December 1", "utoronto.ca", harvest) == "verified"


def test_a_value_missing_from_attributed_text_is_partial() -> None:
    harvest = harvest_grounding(session_with([("utoronto.ca", TORONTO_SEGMENT)]))
    assert verify_claim("January 15", "utoronto.ca", harvest) == "partially_verified"


def test_an_unretrieved_domain_is_unverified() -> None:
    harvest = harvest_grounding(session_with([("utoronto.ca", TORONTO_SEGMENT)]))
    assert verify_claim("December 1", "mcgill.ca", harvest) == "unverified"


def test_source_classification_prefers_official() -> None:
    assert classify_source("utoronto.ca", "utoronto.ca") == "official"
    assert classify_source("grad.utoronto.ca", "utoronto.ca") == "official"
    assert classify_source("mit.edu") == "official"
    assert classify_source("canada.gov") == "government"
    assert classify_source("topuniversities.com") == "aggregator"
    assert classify_source("someblog.io") == "other"


def test_build_fact_wires_status_and_evidence_together() -> None:
    harvest = harvest_grounding(session_with([("utoronto.ca", TORONTO_SEGMENT)]))
    fact = build_fact(
        "December 1", "utoronto.ca", harvest, university_website="utoronto.ca"
    )
    assert fact.status == "verified"
    assert fact.evidence.source_domain == "utoronto.ca"
    assert fact.evidence.source_type == "official"
    assert fact.evidence.retrieved_at
    assert fact.evidence.url.startswith("https://")
