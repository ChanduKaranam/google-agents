"""Model contracts: what the schemas accept, refuse, and report."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models import (
    Evidence,
    MatchWeights,
    Program,
    ProgramFact,
    StudentProfile,
)


def fact(value: str = "x") -> ProgramFact:
    return ProgramFact(value=value, evidence=Evidence(source_domain="utoronto.ca"))


def test_an_empty_profile_knows_nothing() -> None:
    assert StudentProfile().known() == {}


def test_known_reports_only_provided_fields() -> None:
    profile = StudentProfile.model_validate(
        {"education": {"major": "CSE", "cgpa": 8.2}, "target": {"country": "Canada"}}
    )
    known = profile.known()
    assert known == {
        "education": {"major": "CSE", "cgpa": 8.2},
        "target": {"country": "Canada"},
    }


def test_a_typoed_field_is_an_error_not_lost_data() -> None:
    with pytest.raises(ValidationError):
        StudentProfile.model_validate({"education": {"cpga": 8.2}})


def test_out_of_range_scores_are_refused() -> None:
    with pytest.raises(ValidationError):
        StudentProfile.model_validate({"test_scores": {"ielts": 11}})


def test_match_weights_must_sum_to_one() -> None:
    with pytest.raises(ValidationError):
        MatchWeights(academic_fit=0.9)  # rest default → sum > 1


def test_program_rejects_unknown_fact_slots() -> None:
    with pytest.raises(ValidationError):
        Program(university="U", name="MSc CS", facts={"world_ranking": fact()})


def test_program_names_its_unknown_fields() -> None:
    program = Program(
        university="U", name="MSc CS", facts={"application_deadline": fact("Dec 1")}
    )
    unknown = program.unknown_fields()
    assert "application_deadline" not in unknown
    assert "tuition" in unknown


def test_a_fact_cannot_exist_without_evidence() -> None:
    with pytest.raises(ValidationError):
        ProgramFact(value="Dec 1")  # type: ignore[call-arg]
