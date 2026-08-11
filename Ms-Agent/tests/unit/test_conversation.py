"""Conversational intelligence — precedence, context, no re-asking.

The refactor's contract, pinned before implementation (§2-§10 of the
refactor brief):

* **Precedence is automatic and silent.** This turn beats this session;
  this session beats the resume; the resume beats anything historical;
  inference outranks nothing. The highest-priority value becomes the
  effective value — the student is NEVER asked to reconcile stored data
  with what they just said.
* **`conflicts` is gone.** `update_profile` reports `auto_resolved` (the
  incoming value won; the old value went to history) and `retained` (a
  lower-authority source tried to change a higher-authority value; it
  was kept as history instead). Neither is a question.
* **Corrections are instant** — a new explicit statement is already the
  truth when the tool returns.
* **Context references resolve deterministically**: "the current one",
  "use the new one", "the second option", "I don't have it".
* **Known information is never re-asked**; one high-value question only
  when something material is genuinely missing; none when enough exists.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.config.settings import (
    STATE_PROFILE,
    STATE_PROFILE_META,
    STATE_SESSION_FACTS,
)
from app.models.student import StudentProfile
from app.services.context_service import resolve_reference
from app.services.question_service import choose_next_question
from app.tools.profile_tools import get_interview_state, get_profile, update_profile


class StubToolContext:
    def __init__(self) -> None:
        self.state: dict[str, Any] = {}
        self.invocation_id = "test"
        self.session = SimpleNamespace(events=[])


@pytest.fixture
def context() -> StubToolContext:
    return StubToolContext()


def put(context, source: str, **sections) -> dict:
    return update_profile({"profile": sections}, source, context)


def seed_historical(
    context: StubToolContext, sections: dict, source: str
) -> None:
    """State as a NEW session sees it: profile + meta persisted from a
    previous session (`user:` keys), session facts empty."""
    context.state[STATE_PROFILE] = StudentProfile.model_validate(
        {k: v for k, v in sections.items()}
    ).model_dump()
    context.state[STATE_PROFILE_META] = {
        "fields": {
            f"{section}.{field}": {
                "source": source,
                "status": "extracted",
                "confidence": 1.0,
            }
            for section, fields in sections.items()
            for field in fields
        },
        "inferred_domains": [],
    }


# --- TEST 1 / TEST 10 / TEST 13: historical loses silently -------------------


def test_current_user_beats_historical_resume_without_a_question(
    context: StubToolContext,
) -> None:
    seed_historical(
        context,
        {"education": {"major": "Computer Science and Systems Engineering"}},
        source="resume",
    )
    result = put(context, "user_explicit", education={"major": "CSE"})
    assert result["status"] == "success"
    assert "conflicts" not in result  # the old contract is gone
    assert get_profile(context)["profile"]["education"]["major"] == "CSE"
    resolved = result["auto_resolved"][0]
    assert resolved["field"] == "education.major"
    assert resolved["superseded_source"] == "resume"
    assert result["retained"] == []


def test_old_data_never_causes_a_reconciliation_prompt(
    context: StubToolContext,
) -> None:
    seed_historical(context, {"education": {"cgpa": 8.5}}, source="user_explicit")
    result = put(context, "user_explicit", education={"cgpa": 8.2})
    rendered = str(result).casefold()
    assert "which should i use" not in rendered
    assert "never ask" in str(result["note"]).casefold()


# --- TEST 2: current session beats historical profile ------------------------


def test_current_session_beats_historical_explicit_value(
    context: StubToolContext,
) -> None:
    seed_historical(context, {"education": {"cgpa": 8.5}}, source="user_explicit")
    put(context, "user_explicit", education={"cgpa": 8.2})
    assert get_profile(context)["profile"]["education"]["cgpa"] == 8.2


# --- TEST 3 / TEST 4: contextual reference resolution ------------------------


OPTIONS = [
    {"label": "current conversation", "value": "CSE"},
    {"label": "resume", "value": "Computer Science and Systems Engineering"},
]


@pytest.mark.parametrize(
    "reply", ["the current one", "current", "use the new one", "the latest"]
)
def test_current_references_resolve_to_the_current_value(reply: str) -> None:
    result = resolve_reference(reply, OPTIONS)
    assert result["resolution"] == "selected"
    assert result["value"] == "CSE"
    assert result["basis"]


@pytest.mark.parametrize("reply", ["keep the previous one", "the old one"])
def test_previous_references_resolve_to_the_prior_value(reply: str) -> None:
    result = resolve_reference(reply, OPTIONS)
    assert result["value"] == "Computer Science and Systems Engineering"


def test_ordinals_pick_from_the_list() -> None:
    options = [
        {"label": "1", "value": "Waterloo"},
        {"label": "2", "value": "UBC"},
        {"label": "3", "value": "Toronto"},
    ]
    assert resolve_reference("the second one", options)["value"] == "UBC"
    assert resolve_reference("option 3", options)["value"] == "Toronto"


def test_yes_no_and_declines_are_understood() -> None:
    assert resolve_reference("yes", OPTIONS)["resolution"] == "affirmed"
    assert resolve_reference("no", OPTIONS)["resolution"] == "negated"
    assert resolve_reference("I don't have it", OPTIONS)["resolution"] == "declined"


def test_unresolvable_replies_say_so_instead_of_guessing() -> None:
    result = resolve_reference("banana", OPTIONS)
    assert result["resolution"] == "unresolved"


# --- TEST 5 / TEST 6 / TEST 12: never re-ask what is known -------------------


def test_a_known_cgpa_is_never_asked_again(context: StubToolContext) -> None:
    put(context, "user_explicit", education={"cgpa": 8.2, "grading_scale": "10"})
    question = get_interview_state("", context)["next_question"]
    assert question is None or question["field"] not in (
        "education.cgpa",
        "education.grading_scale",
    )


def test_a_known_country_is_never_asked_again(context: StubToolContext) -> None:
    put(context, "user_explicit", target={"country": "Canada"})
    question = get_interview_state("FIND_AFFORDABLE", context)["next_question"]
    assert question is None or question["field"] != "target.country"


def test_a_stored_profile_serves_when_nothing_new_arrives(
    context: StubToolContext,
) -> None:
    seed_historical(context, {"target": {"country": "Canada"}}, "user_explicit")
    snapshot = get_profile(context)
    assert snapshot["is_empty"] is False
    assert snapshot["profile"]["target"]["country"] == "Canada"


# --- TEST 7 / TEST 8: inference outranks nothing -----------------------------


def test_resume_inference_never_overwrites_explicit_preference(
    context: StubToolContext,
) -> None:
    put(context, "user_explicit", target={"specialization": "AI/ML"})
    update_profile(
        {
            "profile": {},
            "inferred_domains": [
                {
                    "domain": "Computer Vision",
                    "confidence": 0.8,
                    "basis": ["facial recognition project"],
                }
            ],
        },
        "resume",
        context,
    )
    snapshot = get_profile(context)
    assert snapshot["profile"]["target"]["specialization"] == "AI/ML"


def test_a_resume_project_is_a_hypothesis_not_an_interest(
    context: StubToolContext,
) -> None:
    update_profile(
        {
            "profile": {},
            "inferred_domains": [
                {
                    "domain": "AI/ML",
                    "confidence": 0.9,
                    "basis": ["3 ML projects"],
                }
            ],
        },
        "resume",
        context,
    )
    snapshot = get_profile(context)
    assert snapshot["profile"].get("target", {}).get("specialization") is None
    inference = snapshot["unconfirmed_domain_inferences"][0]
    assert inference["status"] == "needs_confirmation"
    assert inference["basis"]


# --- TEST 9: corrections are instant -----------------------------------------


def test_an_explicit_correction_applies_without_confirmation(
    context: StubToolContext,
) -> None:
    put(context, "user_explicit", education={"cgpa": 8.5})
    result = put(context, "user_explicit", education={"cgpa": 8.2})
    assert get_profile(context)["profile"]["education"]["cgpa"] == 8.2
    assert result["retained"] == []
    rendered = str(result).casefold()
    assert "should i update" not in rendered


def test_a_session_resume_cannot_displace_a_session_statement(
    context: StubToolContext,
) -> None:
    """Lower authority arriving later is retained as history, not applied
    and not asked about."""
    put(context, "user_explicit", education={"cgpa": 8.5})
    result = put(context, "resume", education={"cgpa": 8.2})
    assert get_profile(context)["profile"]["education"]["cgpa"] == 8.5
    kept = result["retained"][0]
    assert kept["field"] == "education.cgpa"
    assert kept["kept_source"] == "user_explicit"
    assert kept["incoming_source"] == "resume"


# --- TEST 11: sessions do not leak into each other ---------------------------


def test_session_facts_live_in_session_scope() -> None:
    """No `user:` prefix — ADK keeps the key per session, so a new session
    starts with no current-session claims while `user:` history persists."""
    assert not STATE_SESSION_FACTS.startswith("user:")


def test_a_new_session_sees_history_as_history(context: StubToolContext) -> None:
    seed_historical(context, {"education": {"cgpa": 8.5}}, "user_explicit")
    snapshot = get_profile(context)
    assert snapshot["stated_this_session"] == []
    assert "education.cgpa" in snapshot["historical"]
    put(context, "user_explicit", target={"country": "Canada"})
    snapshot = get_profile(context)
    assert "target.country" in snapshot["stated_this_session"]
    assert "education.cgpa" in snapshot["historical"]


# --- TEST 14 / TEST 15: one question when needed, none when not --------------


def test_insufficient_information_yields_exactly_one_question() -> None:
    question = choose_next_question(StudentProfile(), "")
    assert isinstance(question, dict)
    assert question["field"]


def test_enough_information_yields_no_question() -> None:
    profile = StudentProfile.model_validate(
        {
            "education": {
                "degree": "Bachelor's",
                "major": "CSE",
                "cgpa": 8.2,
                "grading_scale": "10",
            },
            "test_scores": {"ielts": 7.0, "gre": 320},
            "experience": {"work_experience_months": 12},
            "research": {"research_interests": ["CV"]},
            "preferences": {
                "budget": 3000000,
                "thesis_preference": True,
                "coop_preference": True,
            },
            "target": {
                "country": "Canada",
                "intake": "Fall 2027",
                "specialization": "AI/ML",
                "career_goal": "ML Engineer",
            },
        }
    )
    assert choose_next_question(profile, "") is None
