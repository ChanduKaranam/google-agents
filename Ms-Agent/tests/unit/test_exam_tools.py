"""`check_exam_requirements` — stored evidence in, personalized matrix out.

The tool reads ONLY what research stored (program facts with evidence) and
what the profile states. Per §26: requirements never leak between programs,
absence surfaces as unknown, and every row carries its evidence and
retrieval time.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.config.settings import STATE_KNOWLEDGE, STATE_PROFILE
from app.models.student import StudentProfile
from app.tools.exam_tools import check_exam_requirements, get_exam_info


class StubToolContext:
    def __init__(self) -> None:
        self.state: dict[str, Any] = {}
        self.invocation_id = "test"
        self.session = SimpleNamespace(events=[])


def program(key: str, university: str, name: str, facts: dict[str, str]):
    return {
        "university": university,
        "name": name,
        "degree_type": "",
        "country": "Canada",
        "city": "",
        "program_url": "",
        "facts": {
            field: {
                "value": value,
                "status": "verified",
                "evidence": {
                    "source_title": "Graduate admissions",
                    "source_domain": f"{key}.ca",
                    "url": f"https://{key}.ca/grad",
                    "source_type": "official",
                    "quote": "",
                    "retrieved_at": "2026-08-10T00:00:00+00:00",
                },
            }
            for field, value in facts.items()
        },
    }


@pytest.fixture
def context() -> StubToolContext:
    ctx = StubToolContext()
    ctx.state[STATE_KNOWLEDGE] = {
        "ubc::msc cs": program(
            "ubc",
            "UBC",
            "MSc Computer Science",
            {
                "english_requirement": "IELTS overall 6.5 with no band below 6.0",
                "gre_requirement": "GRE is not required",
            },
        ),
        "waterloo::mmath cs": program(
            "waterloo",
            "Waterloo",
            "MMath Computer Science",
            {"english_requirement": "IELTS overall 7.0 required"},
        ),
    }
    ctx.state[STATE_PROFILE] = StudentProfile.model_validate(
        {"test_scores": {"ielts": 7.0}}
    ).model_dump()
    return ctx


def rows_by_university(result: dict) -> dict[str, dict]:
    return {row["university"]: row for row in result["programs"]}


def test_the_matrix_covers_every_researched_program(context) -> None:
    result = check_exam_requirements(context)
    assert result["status"] == "success"
    assert set(rows_by_university(result)) == {"UBC", "Waterloo"}


def test_requirements_do_not_leak_between_programs(context) -> None:
    rows = rows_by_university(check_exam_requirements(context))
    assert rows["UBC"]["gre"]["status"] == "not_required"
    # Waterloo's GRE was never researched → unknown, never inherited.
    assert rows["Waterloo"]["gre"]["status"] == "unknown"


def test_student_scores_are_compared_per_program(context) -> None:
    rows = rows_by_university(check_exam_requirements(context))
    # UBC: overall ok but per-section minimum stated, sections unknown.
    assert rows["UBC"]["english"]["student"]["verdict"] == (
        "meets_overall_sections_unknown"
    )
    # Waterloo: 7.0 meets the stated 7.0.
    assert rows["Waterloo"]["english"]["student"]["verdict"] == ("meets_stated_minimum")


def test_every_interpreted_row_carries_evidence_and_freshness(context) -> None:
    rows = rows_by_university(check_exam_requirements(context))
    english = rows["UBC"]["english"]
    assert english["source_domain"] == "ubc.ca"
    assert english["retrieved_at"]
    assert english["verification_status"] == "verified"


def test_gaps_name_actions_not_optional_exams(context) -> None:
    context.state[STATE_PROFILE] = StudentProfile().model_dump()
    result = check_exam_requirements(context)
    gaps = " ".join(result["gaps"]).casefold()
    assert "english" in gaps  # required English, no score → a real gap
    assert "gre" not in gaps  # not_required/unknown GRE is never a gap


def test_no_research_is_an_honest_empty(context) -> None:
    context.state[STATE_KNOWLEDGE] = {}
    result = check_exam_requirements(context)
    assert result["status"] == "error"
    assert result["reason"] == "no_programs_researched"


def test_exam_info_tool_serves_structure(context) -> None:
    result = get_exam_info("ielts", context)
    assert result["status"] == "success"
    assert result["exam"]["validity_years"] == 2
    assert "acceptance" in result["note"].casefold()  # program-specific caveat


def test_exam_info_unknown_exam_is_refused(context) -> None:
    result = get_exam_info("sat", context)
    assert result["status"] == "error"
    assert "ielts" in result["known_exams"]
