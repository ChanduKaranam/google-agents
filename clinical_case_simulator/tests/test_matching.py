"""Gating tests for request matching.

A wrong match hands the student a fabricated result, which is the exact
failure mode this project is built to avoid.
"""

import pytest

from clinical_simulator.cases import get_case
from clinical_simulator.cases.matching import best_finding, match_all


@pytest.fixture
def case():
    return get_case("IM-001")


@pytest.mark.parametrize(
    "query,expected_id",
    [
        ("sputum for AFB", "afb"),
        ("GeneXpert", "afb"),
        ("sputum culture", "sputum"),
        ("sputum gram stain and culture", "sputum"),
        ("chest x-ray", "cxr"),
        ("CXR", "cxr"),
        ("complete blood count", "cbc"),
        ("CBC", "cbc"),
        ("renal function and electrolytes", "rft"),
        ("CT chest", "ctchest"),
    ],
)
def test_investigation_requests_resolve_correctly(case, query, expected_id):
    findings, _ = match_all(query, case.investigations)
    assert findings and findings[0].id == expected_id, query


def test_a_compound_request_returns_every_test(case):
    findings, _ = match_all("CBC, CRP and blood culture", case.investigations)
    assert {f.id for f in findings} == {"cbc", "crp", "bloodculture"}


def test_a_compound_examination_returns_both_manoeuvres(case):
    findings, _ = match_all("auscultate the chest and percuss it", case.examination)
    assert {f.id for f in findings} == {"auscultation", "percussion"}


def test_an_undefined_test_is_refused_not_invented(case):
    findings, _ = match_all("bronchoscopy", case.investigations)
    assert findings == []


def test_an_ambiguous_request_asks_rather_than_guesses(case):
    finding, suggestions = best_finding("culture", case.investigations)
    assert finding is None
    assert suggestions


def test_matching_is_case_and_punctuation_insensitive(case):
    for variant in ("ECG", "e.c.g", "  ecg  "):
        findings, _ = match_all(variant, get_case("IM-002").investigations)
        assert findings and findings[0].id == "ecg", variant
