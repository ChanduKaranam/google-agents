"""Phase 4 — university domain: resolution, freshness, faculty, comparison.

The rules pinned before implementation:

* Aliases resolve to official names; unknown stays unknown; an ambiguous
  alias is a question, never a guess.
* A deadline whose cycle predates the student's target intake is flagged
  stale — historical deadlines are never silently current.
* Faculty matching is token overlap over *stated* interests with a named
  basis; nothing unsupported is matched.
* Comparison renders only stored facts: missing stays unknown, facts never
  leak between programs, and no universal score is produced.
* Overwriting a program fact with a different value from a different
  source records the prior value as a conflict, never erases it.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.config.settings import STATE_EVIDENCE, STATE_KNOWLEDGE, STATE_PROFILE
from app.models.student import StudentProfile
from app.tools.university_analysis_tools import compare_programs, find_faculty_matches
from app.tools.university_tools import save_research
from app.university.analysis import assess_deadline_freshness, match_faculty
from app.university.resolution import resolve_university


class StubToolContext:
    def __init__(self) -> None:
        self.state: dict[str, Any] = {}
        self.invocation_id = "test"
        self.session = SimpleNamespace(events=[])


# --- University resolution (§9) ----------------------------------------------


def test_common_aliases_resolve_to_official_names() -> None:
    assert resolve_university("UBC")["official_name"] == (
        "University of British Columbia"
    )
    assert resolve_university("uoft")["official_name"] == "University of Toronto"
    assert resolve_university("Waterloo")["official_name"] == ("University of Waterloo")


def test_official_names_resolve_to_themselves() -> None:
    result = resolve_university("University of British Columbia")
    assert result["status"] == "resolved"
    assert result["official_name"] == "University of British Columbia"


def test_unknown_universities_stay_unknown() -> None:
    result = resolve_university("Hogwarts Institute")
    assert result["status"] == "unknown"
    assert "official_name" not in result


def test_ambiguous_aliases_ask_rather_than_guess() -> None:
    result = resolve_university("columbia")
    assert result["status"] == "ambiguous"
    assert len(result["candidates"]) >= 2


# --- Deadline freshness (§17) ------------------------------------------------


def test_a_deadline_for_the_target_cycle_is_current() -> None:
    result = assess_deadline_freshness(
        "December 1, 2026 for Fall 2027 admission", target_intake="Fall 2027"
    )
    assert result["status"] == "appears_current"


def test_a_previous_cycle_deadline_is_stale() -> None:
    result = assess_deadline_freshness(
        "Applications closed December 1, 2024 for Fall 2025",
        target_intake="Fall 2027",
    )
    assert result["status"] == "stale"
    assert "2025" in result["note"] or "2024" in result["note"]


def test_a_deadline_without_a_year_is_unclear_not_current() -> None:
    result = assess_deadline_freshness("December 1", target_intake="Fall 2027")
    assert result["status"] == "cycle_unclear"


# --- Faculty matching (§19, §36) ---------------------------------------------


FACULTY_FACT = (
    "Prof. A. Sharma: computer vision, medical imaging. "
    "Prof. B. Chen: natural language processing, LLMs. "
    "Prof. C. Rossi: quantum algorithms."
)


def test_faculty_match_names_the_overlap() -> None:
    result = match_faculty(["Computer Vision", "Deep Learning"], FACULTY_FACT)
    assert result["matched"]
    top = result["matched"][0]
    assert "vision" in " ".join(top["overlap"]).casefold()
    assert top["basis"]


def test_no_overlap_means_no_match_not_an_invented_one() -> None:
    result = match_faculty(["Databases"], FACULTY_FACT)
    assert result["matched"] == []
    assert "no overlap" in result["note"].casefold()


def test_empty_interests_refuse_to_match() -> None:
    result = match_faculty([], FACULTY_FACT)
    assert result["status"] == "no_interests"


# --- Conflict recording on program facts (§31) -------------------------------


def stub_evidence(context: StubToolContext, domain: str, segment: str) -> None:
    context.state[STATE_EVIDENCE] = [
        {
            "domain": domain,
            "uris": [f"https://x/{domain}"],
            "titles": [domain],
            "segments": [segment],
        }
    ]


def test_a_differing_value_from_another_source_is_a_recorded_conflict() -> None:
    context = StubToolContext()
    stub_evidence(context, "ubc.ca", "The application deadline is December 1.")
    save_research(
        "UBC",
        "MSc CS",
        "Canada",
        "",
        [
            {
                "field": "application_deadline",
                "value": "December 1",
                "source_domain": "ubc.ca",
            }
        ],
        context,
    )
    stub_evidence(context, "grad.ubc.ca", "The deadline is December 15.")
    save_research(
        "UBC",
        "MSc CS",
        "Canada",
        "",
        [
            {
                "field": "application_deadline",
                "value": "December 15",
                "source_domain": "grad.ubc.ca",
            }
        ],
        context,
    )
    knowledge = context.state[STATE_KNOWLEDGE]
    fact = next(iter(knowledge.values()))["facts"]["application_deadline"]
    assert fact["value"] == "December 15"
    assert fact["conflicts"][0]["value"] == "December 1"
    assert fact["conflicts"][0]["source_domain"] == "ubc.ca"


# --- Comparison (§24-26) -----------------------------------------------------


@pytest.fixture
def compared_context() -> StubToolContext:
    context = StubToolContext()
    stub_evidence(
        context,
        "ubc.ca",
        "Tuition is CAD 9500 per year. The MSc is thesis-based. "
        "IELTS overall 6.5 required.",
    )
    save_research(
        "University of British Columbia",
        "MSc Computer Science",
        "Canada",
        "",
        [
            {"field": "tuition", "value": "CAD 9500", "source_domain": "ubc.ca"},
            {"field": "structure", "value": "thesis-based", "source_domain": "ubc.ca"},
            {
                "field": "english_requirement",
                "value": "IELTS overall 6.5 required",
                "source_domain": "ubc.ca",
            },
        ],
        context,
    )
    stub_evidence(
        context,
        "uwaterloo.ca",
        "The MMath program deadline is December 1, 2026.",
    )
    save_research(
        "University of Waterloo",
        "MMath Computer Science",
        "Canada",
        "",
        [
            {
                "field": "application_deadline",
                "value": "December 1, 2026",
                "source_domain": "uwaterloo.ca",
            }
        ],
        context,
    )
    return context


def test_the_matrix_keeps_unknowns_unknown(compared_context) -> None:
    result = compare_programs(compared_context)
    assert result["status"] == "success"
    by_uni = {row["university"]: row for row in result["matrix"]}
    ubc = by_uni["University of British Columbia"]
    waterloo = by_uni["University of Waterloo"]
    assert ubc["dimensions"]["tuition"]["value"] == "CAD 9500"
    assert waterloo["dimensions"]["tuition"]["status"] == "unknown"
    # No leakage: Waterloo never inherits UBC's structure.
    assert waterloo["dimensions"]["structure"]["status"] == "unknown"


def test_every_known_dimension_carries_its_source(compared_context) -> None:
    result = compare_programs(compared_context)
    ubc = next(
        r
        for r in result["matrix"]
        if r["university"].startswith("University of British")
    )
    tuition = ubc["dimensions"]["tuition"]
    assert tuition["source_domain"] == "ubc.ca"
    assert tuition["retrieved_at"]


def test_comparison_produces_no_universal_score(compared_context) -> None:
    rendered = str(compare_programs(compared_context)).casefold()
    assert "overall score" not in rendered
    assert "ranking" not in rendered


def test_comparison_with_nothing_stored_is_honest() -> None:
    result = compare_programs(StubToolContext())
    assert result["status"] == "error"
    assert result["reason"] == "no_programs_researched"


# --- Faculty tool over stored facts ------------------------------------------


def test_find_faculty_matches_uses_stored_facts_and_profile() -> None:
    context = StubToolContext()
    stub_evidence(context, "ubc.ca", f"Faculty research: {FACULTY_FACT}")
    save_research(
        "University of British Columbia",
        "MSc Computer Science",
        "Canada",
        "",
        [
            {
                "field": "faculty_research",
                "value": FACULTY_FACT,
                "source_domain": "ubc.ca",
            }
        ],
        context,
    )
    context.state[STATE_PROFILE] = StudentProfile.model_validate(
        {"research": {"research_interests": ["Computer Vision"]}}
    ).model_dump()
    result = find_faculty_matches(context)
    assert result["status"] == "success"
    match = result["universities"][0]
    assert match["matched"]
    assert match["source_domain"] == "ubc.ca"


def test_faculty_matching_without_stored_faculty_is_honest() -> None:
    context = StubToolContext()
    context.state[STATE_PROFILE] = StudentProfile.model_validate(
        {"research": {"research_interests": ["Computer Vision"]}}
    ).model_dump()
    result = find_faculty_matches(context)
    assert result["status"] == "error"
    assert result["reason"] == "no_faculty_researched"
