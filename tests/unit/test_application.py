"""Phase 9 — application intelligence: requirements, readiness, tracking.

The rules pinned before implementation:

* **No fabricated requirements.** A document slot nothing researched is
  `unknown` — never "probably required", never a default. The requirement
  interpreter is the exams one (absence is unknown, negations before
  affirmations), reused, not re-implemented.
* **Readiness is derived, not asserted**: profile + tracked documents vs
  researched requirements → ready/missing/unknown/conditional per row,
  with the action named.
* **Deadlines**: a date is parsed only when stated; a past date is
  `passed`; an unparseable one is `unknown` with a verify action. Nothing
  assumes the next cycle from a historical deadline.
* The tracker is deterministic state: closed status sets, invalid
  transitions refused.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from typing import Any

import pytest

from app.application.analysis import (
    application_readiness,
    deadline_urgency,
    extract_lor_details,
    parse_deadline_date,
)
from app.application.tracker import (
    APPLICATION_STATUSES,
    DOCUMENT_STATUSES,
    next_action,
    set_document,
    upsert_application,
)
from app.config.settings import STATE_APPLICATIONS, STATE_EVIDENCE, STATE_PROFILE
from app.models.program import PROGRAM_FIELDS, Program
from app.models.student import StudentProfile
from app.tools.application_tools import (
    check_application_requirements,
    get_application_dashboard,
    track_application,
    update_document_status,
)
from app.tools.university_tools import save_research


class StubToolContext:
    def __init__(self) -> None:
        self.state: dict[str, Any] = {}
        self.invocation_id = "test"
        self.session = SimpleNamespace(events=[])


def stub_evidence(context: StubToolContext, domain: str, segment: str) -> None:
    ledger = context.state.get(STATE_EVIDENCE) or []
    ledger.append(
        {
            "domain": domain,
            "uris": [f"https://{domain}/x"],
            "titles": [domain],
            "segments": [segment],
        }
    )
    context.state[STATE_EVIDENCE] = ledger


def student() -> StudentProfile:
    return StudentProfile.model_validate(
        {
            "education": {"cgpa": 8.2, "grading_scale": "10"},
            "test_scores": {"ielts": 7.0},
            "target": {"country": "Canada", "intake": "Fall 2027"},
        }
    )


def waterloo(facts: dict[str, str]) -> Program:
    return Program.model_validate(
        {
            "university": "University of Waterloo",
            "name": "MMath Computer Science",
            "country": "Canada",
            "facts": {
                field: {
                    "value": value,
                    "status": "verified",
                    "evidence": {
                        "source_domain": "uwaterloo.ca",
                        "source_type": "official",
                        "retrieved_at": "2026-08-11T00:00:00+00:00",
                    },
                }
                for field, value in facts.items()
            },
        }
    )


# --- The application requirement slots (§6) ----------------------------------


def test_the_application_slots_exist_on_programs() -> None:
    for field in (
        "sop_requirement",
        "lor_requirement",
        "transcript_requirement",
        "resume_requirement",
        "portfolio_requirement",
        "prerequisite_requirement",
        "application_portal",
        "additional_documents",
    ):
        assert field in PROGRAM_FIELDS


def test_application_requirements_demand_authoritative_sources() -> None:
    context = StubToolContext()
    stub_evidence(context, "reddit.com", "you need three LORs")
    result = save_research(
        "University of Waterloo",
        "MMath Computer Science",
        "Canada",
        "",
        [
            {
                "field": "lor_requirement",
                "value": "three letters of recommendation",
                "source_domain": "reddit.com",
            }
        ],
        context,
    )
    assert result["refused_claims"][0]["reason"] == "source_lacks_authority"


# --- LOR details (§6) ---------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "count", "kind"),
    [
        ("Three letters of recommendation from academic referees", 3, "academic"),
        ("2 references required", 2, None),
        ("At least two letters, academic or professional", 2, "mixed"),
        ("Letters of recommendation are required", None, None),
    ],
)
def test_lor_details_come_from_the_text_only(
    text: str, count: int | None, kind: str | None
) -> None:
    details = extract_lor_details(text)
    assert details["count"] == count
    assert details["reference_type"] == kind


def test_a_bare_listing_on_a_requirements_page_reads_as_stated() -> None:
    """The slot holds the program's own requirements line, so a listing is
    a positive statement — but negations and 'optional' still win, and an
    absent fact stays unknown (§6: no invention)."""
    from app.application.analysis import interpret_document_requirement

    assert (
        interpret_document_requirement("Three letters of recommendation")["status"]
        == "required"
    )
    assert (
        interpret_document_requirement("A portfolio is not required")["status"]
        == "not_required"
    )
    assert interpret_document_requirement("")["status"] == "unknown"


# --- Deadlines (§9) -----------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("December 15, 2026", date(2026, 12, 15)),
        ("15 December 2026", date(2026, 12, 15)),
        ("Feb 1, 2027", date(2027, 2, 1)),
        ("2026-12-15", date(2026, 12, 15)),
        ("rolling admissions", None),
    ],
)
def test_deadline_dates_parse_only_when_stated(
    text: str, expected: date | None
) -> None:
    assert parse_deadline_date(text) == expected


def test_a_future_deadline_counts_its_days() -> None:
    result = deadline_urgency("December 15, 2026", today=date(2026, 11, 15))
    assert result["days_remaining"] == 30
    assert result["urgency"] == "urgent"


def test_a_passed_deadline_is_passed_never_rolled_forward() -> None:
    result = deadline_urgency("December 15, 2025", today=date(2026, 8, 11))
    assert result["urgency"] == "passed"
    assert "verify" in result["note"].casefold()


def test_an_unparseable_deadline_is_unknown() -> None:
    result = deadline_urgency("rolling admissions", today=date(2026, 8, 11))
    assert result["urgency"] == "unknown"
    assert result["days_remaining"] is None


# --- Readiness (§7) -----------------------------------------------------------


REQUIREMENTS = {
    "sop_requirement": "A statement of purpose is required",
    "lor_requirement": "Three letters of recommendation from academic referees",
    "english_requirement": "IELTS overall 7.0 required",
    "gre_requirement": "GRE is not required",
    "portfolio_requirement": "A portfolio may be submitted",
}


def test_readiness_rows_carry_verdicts_and_actions() -> None:
    rows = application_readiness(
        student(), waterloo(REQUIREMENTS), {"transcripts": "ready"}
    )
    by_doc = {r["requirement"]: r for r in rows["rows"]}
    sop = by_doc["sop_requirement"]
    assert sop["interpretation"]["status"] == "required"
    assert sop["verdict"] == "missing"
    assert "sop" in sop["action"].casefold()
    assert by_doc["gre_requirement"]["verdict"] == "not_needed"
    assert by_doc["portfolio_requirement"]["verdict"] == "optional"


def test_an_available_document_is_ready() -> None:
    rows = application_readiness(
        student(), waterloo(REQUIREMENTS), {"sop": "ready", "lor": "draft"}
    )
    by_doc = {r["requirement"]: r for r in rows["rows"]}
    assert by_doc["sop_requirement"]["verdict"] == "ready"
    assert by_doc["lor_requirement"]["verdict"] == "in_progress"


def test_a_held_score_defers_to_the_exam_check() -> None:
    """No second exam engine: readiness reports the score exists and
    points at check_exam_requirements for the verdict."""
    rows = application_readiness(student(), waterloo(REQUIREMENTS), {})
    english = next(
        r for r in rows["rows"] if r["requirement"] == "english_requirement"
    )
    assert english["verdict"] == "have_score"
    assert "check_exam_requirements" in english["action"]


def test_unresearched_requirements_stay_unknown_never_defaulted() -> None:
    rows = application_readiness(student(), waterloo({}), {})
    assert rows["overall"] == "unknown"
    assert rows["unknown_requirements"]
    rendered = str(rows).casefold()
    assert "probably" not in rendered
    assert "typically" not in rendered


def test_missing_required_documents_block_readiness() -> None:
    rows = application_readiness(student(), waterloo(REQUIREMENTS), {})
    assert rows["overall"] == "not_ready"
    blockers = [r["requirement"] for r in rows["rows"] if r["verdict"] == "missing"]
    assert "sop_requirement" in blockers
    assert "lor_requirement" in blockers


def test_all_required_documents_ready_means_ready() -> None:
    rows = application_readiness(
        student(),
        waterloo(REQUIREMENTS),
        {"sop": "ready", "lor": "submitted", "transcripts": "ready"},
    )
    assert rows["overall"] == "ready"


# --- The tracker (§10) --------------------------------------------------------


def test_application_statuses_are_a_closed_set() -> None:
    store: dict[str, Any] = {}
    upsert_application(store, "University of Waterloo", "MMath CS", "shortlisted")
    with pytest.raises(ValueError):
        upsert_application(store, "University of Waterloo", "MMath CS", "vibing")
    assert "submitted" in APPLICATION_STATUSES


def test_document_statuses_are_a_closed_set() -> None:
    store: dict[str, Any] = {}
    upsert_application(store, "UW", "MMath CS", "preparing")
    set_document(store, "UW", "MMath CS", "sop", "draft")
    with pytest.raises(ValueError):
        set_document(store, "UW", "MMath CS", "sop", "vibed")
    with pytest.raises(ValueError):
        set_document(store, "UW", "MMath CS", "netflix_list", "ready")
    assert "verified" in DOCUMENT_STATUSES


def test_tracking_preserves_documents_across_status_changes() -> None:
    store: dict[str, Any] = {}
    upsert_application(store, "UW", "MMath CS", "preparing")
    set_document(store, "UW", "MMath CS", "sop", "draft")
    upsert_application(store, "UW", "MMath CS", "ready")
    application = next(iter(store.values()))
    assert application["status"] == "ready"
    assert application["documents"]["sop"] == "draft"


def test_next_action_prioritizes_blockers_over_polish() -> None:
    action = next_action(
        {"status": "preparing", "documents": {"transcripts": "ready"}},
        application_readiness(student(), waterloo(REQUIREMENTS), {}),
        deadline_urgency("December 15, 2026", today=date(2026, 8, 11)),
    )
    assert "sop" in action.casefold() or "letters" in action.casefold()


def test_next_action_on_a_passed_deadline_says_verify() -> None:
    action = next_action(
        {"status": "preparing", "documents": {}},
        application_readiness(student(), waterloo(REQUIREMENTS), {}),
        deadline_urgency("December 15, 2025", today=date(2026, 8, 11)),
    )
    assert "verify" in action.casefold() or "passed" in action.casefold()


# --- The tools (§5, §7, §10) --------------------------------------------------


def researched_context() -> StubToolContext:
    context = StubToolContext()
    context.state[STATE_PROFILE] = student().model_dump()
    stub_evidence(
        context,
        "uwaterloo.ca",
        "A statement of purpose is required. Three letters of recommendation "
        "from academic referees. IELTS overall 7.0 required. Applications "
        "are due December 15, 2026.",
    )
    save_research(
        "University of Waterloo",
        "MMath Computer Science",
        "Canada",
        "",
        [
            {
                "field": field,
                "value": value,
                "source_domain": "uwaterloo.ca",
            }
            for field, value in {
                "sop_requirement": "A statement of purpose is required",
                "lor_requirement": "Three letters of recommendation from "
                "academic referees",
                "english_requirement": "IELTS overall 7.0 required",
                "application_deadline": "December 15, 2026",
            }.items()
        ],
        context,
    )
    return context


def test_requirements_come_back_with_provenance_and_unknowns() -> None:
    result = check_application_requirements(researched_context())
    assert result["status"] == "success"
    program = result["programs"][0]
    rows = {r["field"]: r for r in program["requirements"]}
    assert rows["sop_requirement"]["interpretation"]["status"] == "required"
    assert rows["sop_requirement"]["source_domain"] == "uwaterloo.ca"
    assert rows["lor_requirement"]["lor_details"]["count"] == 3
    assert "portfolio_requirement" in program["unknown_requirements"]


def test_no_application_research_is_an_honest_error() -> None:
    context = StubToolContext()
    context.state[STATE_PROFILE] = student().model_dump()
    result = check_application_requirements(context)
    assert result["status"] == "error"
    assert result["reason"] == "no_application_evidence"


def test_the_tracker_tools_write_validated_state() -> None:
    context = researched_context()
    result = track_application(
        "University of Waterloo", "MMath Computer Science", "preparing", context
    )
    assert result["status"] == "success"
    result = update_document_status(
        "University of Waterloo", "MMath Computer Science", "sop", "draft", context
    )
    assert result["status"] == "success"
    bad = track_application(
        "University of Waterloo", "MMath Computer Science", "vibing", context
    )
    assert bad["status"] == "error"
    assert "vibing" not in str(context.state.get(STATE_APPLICATIONS))


def test_the_dashboard_joins_requirements_tracker_and_deadline() -> None:
    context = researched_context()
    track_application(
        "University of Waterloo", "MMath Computer Science", "preparing", context
    )
    update_document_status(
        "University of Waterloo", "MMath Computer Science", "transcripts", "ready",
        context,
    )
    result = get_application_dashboard(context)
    assert result["status"] == "success"
    application = result["applications"][0]
    assert application["readiness"]["overall"] == "not_ready"
    assert application["deadline"]["urgency"] in (
        "urgent",
        "soon",
        "comfortable",
        "passed",
    )
    assert application["next_action"]
    rendered = str(result).casefold()
    assert "admission probability" not in rendered


def test_an_untracked_dashboard_is_honest_not_empty_success() -> None:
    result = get_application_dashboard(StubToolContext())
    assert result["status"] == "error"
    assert result["reason"] == "nothing_tracked"
