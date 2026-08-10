"""The V1 scenarios, end to end, with the network unplugged.

These drive the same tool sequence the orchestrator's instruction
prescribes — extract → update → research → save → match — against stubbed
grounding, proving the deterministic layer end to end. The live halves
(does the model choose these calls) are in `test_live.py`, gated on a
configured backend.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.config.settings import STATE_EVIDENCE, STATE_KNOWLEDGE, STATE_PROFILE
from app.tools.matching_tools import match_programs
from app.tools.profile_tools import get_missing_fields, get_profile, update_profile
from app.tools.university_tools import get_programs, save_research

TORONTO_SEGMENT = (
    "The MSc in Computer Science at the University of Toronto requires a "
    "minimum GPA of 3.0/4.0, IELTS 7.0, and the application deadline is "
    "December 1, 2026."
)


class StubToolContext:
    def __init__(self) -> None:
        self.state: dict[str, Any] = {}
        self.invocation_id = "test-invocation"
        self.session = SimpleNamespace(events=[])


@pytest.fixture
def context() -> StubToolContext:
    return StubToolContext()


def lendi_update() -> dict:
    """What the profile agent extracts from the Scenario 1 message."""
    return {
        "profile": {
            "education": {
                "major": "CSE",
                "institution": "Lendi",
                "cgpa": 8.2,
            },
            "target": {"degree": "MS", "country": "Canada"},
        },
        "ambiguities": [],
    }


def stub_evidence(context: StubToolContext) -> None:
    """What the research agent's harvest callback would have stored."""
    context.state[STATE_EVIDENCE] = [
        {
            "domain": "utoronto.ca",
            "uris": ["https://vertexaisearch.example/redir1"],
            "titles": ["utoronto.ca"],
            "segments": [TORONTO_SEGMENT],
        }
    ]


TORONTO_CLAIMS = [
    {"field": "gpa_requirement", "value": "3.0/4.0", "source_domain": "utoronto.ca"},
    {
        "field": "english_requirement",
        "value": "IELTS 7.0",
        "source_domain": "utoronto.ca",
    },
    {
        "field": "application_deadline",
        "value": "December 1, 2026",
        "source_domain": "utoronto.ca",
    },
    # A fabricated fee from a never-retrieved domain must grade unverified.
    {"field": "tuition", "value": "CAD 61,000", "source_domain": "made-up.com"},
]


# --- Scenario 1 + 2 + 3: profile lifecycle ----------------------------------


def test_profile_create_update_and_status(context: StubToolContext) -> None:
    created = update_profile(lendi_update(), context)
    assert created["status"] == "success"
    assert "education.cgpa" in created["changed"]

    # Scenario 2 — new facts land, old facts survive.
    update_profile(
        {
            "profile": {
                "education": {"graduation_year": 2026},
                "target": {"intake": "Fall 2027"},
            }
        },
        context,
    )
    status = get_profile(context)
    assert status["profile"]["education"]["cgpa"] == 8.2
    assert status["profile"]["education"]["graduation_year"] == 2026
    assert status["profile"]["target"]["intake"] == "Fall 2027"

    # Scenario 7 — the next question is the single highest-value gap.
    ask = get_missing_fields(context)["ask_next"]
    assert ask["field"] == "education.grading_scale"


def test_an_invalid_update_is_refused_with_the_field_named(
    context: StubToolContext,
) -> None:
    result = update_profile({"profile": {"education": {"cgpa": "eight"}}}, context)
    assert result["status"] == "error"
    assert result["reason"] == "invalid_update"
    assert STATE_PROFILE not in context.state


# --- Scenario 5: research with evidence grading -----------------------------


def test_research_grades_every_claim_and_names_unknowns(
    context: StubToolContext,
) -> None:
    stub_evidence(context)
    result = save_research(
        "University of Toronto",
        "MSc Computer Science",
        "Canada",
        "https://web.cs.toronto.edu",
        TORONTO_CLAIMS,
        context,
    )
    graded = {c["field"]: c["verification_status"] for c in result["graded_claims"]}
    assert graded["gpa_requirement"] == "verified"
    assert graded["english_requirement"] == "verified"
    assert graded["application_deadline"] == "verified"
    assert graded["tuition"] == "unverified"  # fabricated source, caught
    assert "duration" in result["unknown_fields"]


def test_research_from_nothing_retrieved_is_refused(
    context: StubToolContext,
) -> None:
    result = save_research(
        "University of Toronto", "MSc CS", "Canada", "", TORONTO_CLAIMS, context
    )
    assert result["status"] == "error"
    assert result["reason"] == "no_sources_retrieved"
    assert STATE_KNOWLEDGE not in context.state


def test_stored_programs_render_with_sources(context: StubToolContext) -> None:
    stub_evidence(context)
    save_research(
        "University of Toronto",
        "MSc Computer Science",
        "Canada",
        "",
        TORONTO_CLAIMS[:3],
        context,
    )
    programs = get_programs(context)["programs"]
    assert len(programs) == 1
    deadline = programs[0]["facts"]["application_deadline"]
    assert deadline["verification_status"] == "verified"
    assert deadline["source_domain"] == "utoronto.ca"
    assert deadline["retrieved_at"]


# --- Scenario 4: the full pipeline ------------------------------------------


def test_profile_research_match_pipeline(context: StubToolContext) -> None:
    update_profile(lendi_update(), context)
    update_profile(
        {
            "profile": {
                "education": {"grading_scale": "10"},
                "test_scores": {"ielts": 7.5},
            }
        },
        context,
    )
    stub_evidence(context)
    save_research(
        "University of Toronto",
        "MSc Computer Science",
        "Canada",
        "",
        TORONTO_CLAIMS[:3],
        context,
    )

    result = match_programs(context)
    assert result["status"] == "success"
    top = result["results"][0]
    assert top["university"] == "University of Toronto"
    assert 0 <= top["match_score"] <= 100
    assert top["category"]
    assert top["not_an_admission_estimate"] is True
    # The engine explains itself.
    assert top["reasoning"]


def test_matching_refuses_before_the_inputs_exist(context: StubToolContext) -> None:
    assert match_programs(context)["reason"] == "empty_profile"
    update_profile(lendi_update(), context)
    assert match_programs(context)["reason"] == "no_programs_researched"
