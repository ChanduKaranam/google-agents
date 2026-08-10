"""V2 tool behaviors: provenance, inference channel, authority gate,
deletion, conversion, next steps."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.config.settings import STATE_EVIDENCE, STATE_PROFILE
from app.tools.planning_tools import get_next_steps
from app.tools.profile_tools import (
    clear_profile,
    convert_gpa,
    get_profile,
    update_profile,
)
from app.tools.university_tools import save_research


class StubToolContext:
    def __init__(self) -> None:
        self.state: dict[str, Any] = {}
        self.invocation_id = "test-invocation"
        self.session = SimpleNamespace(events=[])


@pytest.fixture
def context() -> StubToolContext:
    return StubToolContext()


def lendi(source: str = "user_explicit", context: StubToolContext | None = None):
    return update_profile(
        {"profile": {"education": {"cgpa": 8.2, "grading_scale": "10"}}},
        source,
        context,
    )


# --- Provenance -------------------------------------------------------------


def test_every_stored_path_records_its_source(context: StubToolContext) -> None:
    lendi("user_explicit", context)
    update_profile(
        {"profile": {"technical": {"skills": ["Python"]}}}, "resume", context
    )
    provenance = get_profile(context)["provenance"]
    assert provenance["education.cgpa"]["source"] == "user_explicit"
    assert provenance["technical.skills"]["source"] == "resume"


def test_an_invalid_source_is_refused(context: StubToolContext) -> None:
    result = lendi("wikipedia", context)
    assert result["status"] == "error"
    assert result["reason"] == "invalid_source"
    assert STATE_PROFILE not in context.state


def test_inferences_stay_out_of_the_profile(context: StubToolContext) -> None:
    """A resume inference is a suggestion channel, never a profile fact."""
    update_profile(
        {
            "profile": {},
            "inferred_domains": [
                {
                    "domain": "AI/ML",
                    "confidence": 0.85,
                    "basis": ["3 ML projects", "PyTorch"],
                }
            ],
        },
        "resume",
        context,
    )
    state = get_profile(context)
    assert state["profile"] == {}  # nothing entered the profile itself
    inference = state["unconfirmed_domain_inferences"][0]
    assert inference["domain"] == "AI/ML"
    assert inference["status"] == "needs_confirmation"
    assert inference["basis"]


def test_confirming_an_inference_makes_it_a_fact_with_provenance(
    context: StubToolContext,
) -> None:
    update_profile(
        {
            "profile": {},
            "inferred_domains": [
                {"domain": "AI/ML", "confidence": 0.85, "basis": ["projects"]}
            ],
        },
        "resume",
        context,
    )
    update_profile(
        {"profile": {"target": {"specialization": "AI/ML"}}},
        "user_confirmed",
        context,
    )
    state = get_profile(context)
    assert state["profile"]["target"]["specialization"] == "AI/ML"
    assert state["provenance"]["target.specialization"]["source"] == "user_confirmed"


# --- Deletion and conversion ------------------------------------------------


def test_clear_profile_actually_erases(context: StubToolContext) -> None:
    lendi("user_explicit", context)
    result = clear_profile(True, context)
    assert result["status"] == "success"
    state = get_profile(context)
    assert state["is_empty"] is True
    assert state["provenance"] == {}


def test_clear_without_confirmation_refuses(context: StubToolContext) -> None:
    lendi("user_explicit", context)
    assert clear_profile(False, context)["status"] == "error"
    assert get_profile(context)["is_empty"] is False


def test_convert_gpa_uses_the_engine_not_the_model(context: StubToolContext) -> None:
    lendi("user_explicit", context)
    result = convert_gpa(context)
    assert result["status"] == "success"
    assert result["us_4pt_equivalent"] == 3.28
    assert "approximation" in result["caveat"].lower()


def test_convert_gpa_without_a_scale_asks(context: StubToolContext) -> None:
    update_profile({"profile": {"education": {"cgpa": 8.2}}}, "user_explicit", context)
    assert convert_gpa(context)["reason"] == "gpa_or_scale_missing"


# --- The authority gate -----------------------------------------------------


def stub_evidence(context: StubToolContext, domain: str, segment: str) -> None:
    context.state[STATE_EVIDENCE] = [
        {
            "domain": domain,
            "uris": [f"https://x/{domain}"],
            "titles": [domain],
            "segments": [segment],
        }
    ]


def test_a_community_source_cannot_establish_a_deadline(
    context: StubToolContext,
) -> None:
    """V1's worst live finding: a deadline 'reported by youtube.com'."""
    stub_evidence(context, "youtube.com", "The deadline is December 1, 2026.")
    result = save_research(
        "University of Toronto",
        "MSc CS",
        "Canada",
        "",
        [
            {
                "field": "application_deadline",
                "value": "December 1, 2026",
                "source_domain": "youtube.com",
            }
        ],
        context,
    )
    refusal = result["refused_claims"][0]
    assert refusal["reason"] == "source_lacks_authority"
    assert result["graded_claims"] == []


def test_a_community_source_may_supply_career_signals(
    context: StubToolContext,
) -> None:
    stub_evidence(
        context,
        "linkedin.com",
        "Graduates report roles such as ML Engineer and Data Scientist.",
    )
    result = save_research(
        "University of Toronto",
        "MSc CS",
        "Canada",
        "",
        [
            {
                "field": "career_signals",
                "value": "Graduates report roles such as ML Engineer and Data Scientist",
                "source_domain": "linkedin.com",
            }
        ],
        context,
    )
    assert result["graded_claims"][0]["field"] == "career_signals"
    assert result["graded_claims"][0]["source_type"] == "community"


def test_an_aggregator_can_report_but_never_verify(context: StubToolContext) -> None:
    stub_evidence(context, "topuniversities.com", "Tuition is CAD 61,000 per year.")
    result = save_research(
        "University of Toronto",
        "MSc CS",
        "Canada",
        "",
        [
            {
                "field": "tuition",
                "value": "CAD 61,000",
                "source_domain": "topuniversities.com",
            }
        ],
        context,
    )
    graded = result["graded_claims"][0]
    assert graded["verification_status"] == "partially_verified"


# --- Next steps -------------------------------------------------------------


def test_next_steps_are_derived_and_bounded(context: StubToolContext) -> None:
    result = get_next_steps(context)
    assert result["status"] == "success"
    assert 1 <= len(result["next_steps"]) <= 5
    joined = " ".join(result["next_steps"]).lower()
    assert "profile" in joined  # empty profile → complete it first
    assert "ielts" in joined or "english" in joined


def test_next_steps_move_on_once_the_profile_is_ready(
    context: StubToolContext,
) -> None:
    update_profile(
        {
            "profile": {
                "education": {"major": "CSE", "cgpa": 8.2, "grading_scale": "10"},
                "test_scores": {"ielts": 7.5},
                "target": {"country": "Canada", "specialization": "AI/ML"},
            }
        },
        "user_explicit",
        context,
    )
    joined = " ".join(get_next_steps(context)["next_steps"]).lower()
    assert "shortlist" in joined or "research" in joined
    assert "book an english test" not in joined
