"""Phase 5 — placement & career intelligence: scope, kinds, fit, analysis.

The rules pinned before implementation:

* **Scope is never upgraded.** A faculty-level employment figure stays
  faculty-level; a Canadian labour benchmark stays a market benchmark;
  text stating no scope is `scope_unclear` — never program-specific.
* **Individuals are not statistics.** Three alumni examples can never
  become "66% placement"; aggregates come only from sources that state
  aggregates.
* **Salary carries its attributes** (currency, period, year) only when the
  text states them, and a benchmark is labeled a benchmark.
* Career fit is deterministic token alignment against the student's
  stated skills/interests, with a named basis — no hiring probabilities.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.config.settings import STATE_EVIDENCE, STATE_PROFILE
from app.models.student import StudentProfile
from app.placement.analysis import (
    analyze_career_fit,
    classify_scope,
    extract_salary_attributes,
)
from app.tools.placement_tools import analyze_career_outcomes
from app.tools.university_tools import save_research


class StubToolContext:
    def __init__(self) -> None:
        self.state: dict[str, Any] = {}
        self.invocation_id = "test"
        self.session = SimpleNamespace(events=[])


# --- Scope classification (§13) ----------------------------------------------


@pytest.mark.parametrize(
    ("text", "scope"),
    [
        (
            "92% of MSc Computer Science graduates employed within 6 months",
            "program_specific",
        ),
        ("Faculty of Engineering graduates report 90% employment", "faculty_level"),
        ("University-wide, 88% of graduates found employment", "university_level"),
        ("Median software engineer salary in Canada is CAD 95,000", "market_benchmark"),
        ("92% employment", "scope_unclear"),
    ],
)
def test_scope_is_classified_from_stated_text_only(text: str, scope: str) -> None:
    result = classify_scope(text)
    assert result["scope"] == scope
    if scope != "scope_unclear":
        assert result["basis"]


def test_unclear_scope_is_never_program_specific() -> None:
    result = classify_scope("Employment rate: 95%")
    assert result["scope"] == "scope_unclear"
    assert "verify" in result["note"].casefold()


# --- Salary attributes (§19) -------------------------------------------------


def test_salary_attributes_come_from_the_text() -> None:
    result = extract_salary_attributes(
        "Median salary CAD 95,000 per year for software engineers in "
        "Toronto (2025 labour market data)"
    )
    assert result["currency"] == "CAD"
    assert result["amount"] == 95000
    assert result["period"] == "year"
    assert result["year"] == 2025


def test_missing_salary_attributes_stay_missing() -> None:
    result = extract_salary_attributes("Graduates earn competitive salaries")
    assert result["amount"] is None
    assert result["currency"] is None
    assert result["year"] is None


# --- Career fit (§16) --------------------------------------------------------


ROLES_EVIDENCE = (
    "Graduates commonly move into Machine Learning Engineer, Data "
    "Scientist, Software Engineer and Research Engineer roles."
)


def student() -> StudentProfile:
    return StudentProfile.model_validate(
        {
            "technical": {"skills": ["Python", "TensorFlow", "Deep Learning"]},
            "research": {"research_interests": ["Computer Vision"]},
            "target": {"specialization": "AI/ML", "career_goal": "ML Engineer"},
        }
    )


def test_career_fit_names_aligned_roles_with_basis() -> None:
    result = analyze_career_fit(student(), ROLES_EVIDENCE)
    aligned = {r["role"] for r in result["aligned"]}
    assert "Machine Learning Engineer" in aligned or "ML Engineer" in str(aligned)
    top = result["aligned"][0]
    assert top["basis"]
    rendered = str(result).casefold()
    assert "probability" not in rendered
    assert "%" not in rendered


def test_no_roles_evidence_means_no_fit_claims() -> None:
    result = analyze_career_fit(student(), "")
    assert result["aligned"] == []
    assert "no role evidence" in result["note"].casefold()


# --- The analysis tool (§15, §26) --------------------------------------------


def stub_evidence(context: StubToolContext, domain: str, segment: str) -> None:
    context.state[STATE_EVIDENCE] = [
        {
            "domain": domain,
            "uris": [f"https://x/{domain}"],
            "titles": [domain],
            "segments": [segment],
        }
    ]


@pytest.fixture
def researched_context() -> StubToolContext:
    context = StubToolContext()
    context.state[STATE_PROFILE] = student().model_dump()
    stub_evidence(
        context,
        "uwaterloo.ca",
        "Faculty of Engineering graduates report 90% employment within six "
        "months. Graduates commonly move into Machine Learning Engineer and "
        "Software Engineer roles at companies including Shopify and Google. "
        "Most graduates work in Toronto and Waterloo.",
    )
    save_research(
        "University of Waterloo",
        "MMath Computer Science",
        "Canada",
        "",
        [
            {
                "field": "employment_outcomes",
                "value": "Faculty of Engineering graduates report 90% employment "
                "within six months",
                "source_domain": "uwaterloo.ca",
            },
            {
                "field": "career_signals",
                "value": "Graduates commonly move into Machine Learning Engineer "
                "and Software Engineer roles at companies including "
                "Shopify and Google",
                "source_domain": "uwaterloo.ca",
            },
            {
                "field": "career_locations",
                "value": "Most graduates work in Toronto and Waterloo",
                "source_domain": "uwaterloo.ca",
            },
        ],
        context,
    )
    return context


def test_analysis_preserves_scope_and_sources(researched_context) -> None:
    result = analyze_career_outcomes(researched_context)
    assert result["status"] == "success"
    waterloo = result["universities"][0]
    outcomes = waterloo["employment_outcomes"]
    assert outcomes["scope"]["scope"] == "faculty_level"  # never upgraded
    assert outcomes["source_domain"] == "uwaterloo.ca"
    assert outcomes["retrieved_at"]


def test_analysis_aligns_roles_with_the_profile(researched_context) -> None:
    result = analyze_career_outcomes(researched_context)
    fit = result["universities"][0]["career_fit"]
    assert fit["aligned"]


def test_missing_career_evidence_stays_unknown(researched_context) -> None:
    waterloo = analyze_career_outcomes(researched_context)["universities"][0]
    assert waterloo["salary_evidence"]["status"] == "unknown"


def test_no_career_research_is_an_honest_error() -> None:
    context = StubToolContext()
    context.state[STATE_PROFILE] = student().model_dump()
    result = analyze_career_outcomes(context)
    assert result["status"] == "error"
    assert result["reason"] == "no_career_evidence"


def test_individual_examples_note_points_at_the_alumni_system(
    researched_context,
) -> None:
    """Aggregates here; individuals via the alumni gate. The tool says so."""
    result = analyze_career_outcomes(researched_context)
    assert "alumni" in result["note"].casefold()
    rendered = str(result).casefold()
    assert "placement probability" not in rendered
