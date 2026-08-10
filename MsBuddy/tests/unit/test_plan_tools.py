# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Application documents and progress — deterministic, state-backed, offline.

The checklist is a fixed registry (the documents every MS application needs),
the statuses live in session state under a `user:` key, and the "what next"
suggestion is a priority ladder over state that already exists — profile
completeness, researched programs, document statuses. Nothing here searches,
nothing here writes to the profile, and deadlines are surfaced **only** from
what C2 research verified and stored; this module never invents one.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.config import STATE_DOCUMENTS, STATE_PROFILE, STATE_SHORTLIST
from app.tools.plan_tools import (
    STANDARD_DOCUMENTS,
    get_application_plan,
    set_document_status,
)


class StubToolContext:
    def __init__(self) -> None:
        self.state: dict[str, Any] = {}
        self.invocation_id = "test-invocation"
        self.session = SimpleNamespace(events=[])


@pytest.fixture
def context() -> StubToolContext:
    return StubToolContext()


def core_complete_profile() -> dict[str, Any]:
    """A profile with every core field present."""
    fields = {
        "undergrad_degree": "BTech in Computer Engineering",
        "undergrad_institution": "Anna University",
        "gpa_value": 8.1,
        "gpa_scale": "cgpa_10",
        "target_intake_term": "fall",
        "target_intake_year": 2027,
        "target_countries": "USA",
        "specialization_interest": "Computer Science",
    }
    return {"fields": {k: {"value": v} for k, v in fields.items()}}


def shortlist_with_deadline() -> dict[str, Any]:
    return {
        "programs": {
            "tu-delft::msc-cs": {
                "program_id": "tu-delft::msc-cs",
                "university": "TU Delft",
                "program": "MSc Computer Science",
                "fields": {
                    "application_deadline": {
                        "value": "15 January 2027",
                        "tier": "VERIFIED",
                    },
                    "tuition_amount": {"value": "22290", "tier": "VERIFIED"},
                },
            }
        }
    }


# --- The checklist ----------------------------------------------------------


def test_every_standard_document_starts_pending(context: StubToolContext) -> None:
    plan = get_application_plan(context)
    assert plan["status"] == "success"
    assert len(plan["documents"]) == len(STANDARD_DOCUMENTS)
    assert all(d["state"] == "pending" for d in plan["documents"])


def test_marking_a_document_done_sticks(context: StubToolContext) -> None:
    result = set_document_status("sop", "done", context)
    assert result["status"] == "success"
    plan = get_application_plan(context)
    by_key = {d["document"]: d["state"] for d in plan["documents"]}
    assert by_key["sop"] == "done"
    assert plan["done_count"] == 1


def test_marking_done_twice_is_idempotent(context: StubToolContext) -> None:
    set_document_status("sop", "done", context)
    set_document_status("sop", "done", context)
    assert get_application_plan(context)["done_count"] == 1


def test_a_document_can_go_back_to_pending(context: StubToolContext) -> None:
    set_document_status("sop", "done", context)
    set_document_status("sop", "pending", context)
    assert get_application_plan(context)["done_count"] == 0


def test_an_unknown_document_is_refused_with_the_valid_list(
    context: StubToolContext,
) -> None:
    result = set_document_status("blood_sample", "done", context)
    assert result["status"] == "error"
    assert result["reason"] == "unknown_document"
    assert "sop" in result["valid_documents"]
    assert STATE_DOCUMENTS not in context.state


def test_an_unknown_status_is_refused(context: StubToolContext) -> None:
    result = set_document_status("sop", "maybe", context)
    assert result["status"] == "error"
    assert result["reason"] == "unknown_status"


# --- Progress and next step -------------------------------------------------


def test_with_nothing_recorded_the_next_step_is_the_profile(
    context: StubToolContext,
) -> None:
    plan = get_application_plan(context)
    assert plan["profile"]["core_complete"] is False
    assert "profile" in plan["next_step"].lower()


def test_with_a_complete_profile_the_next_step_is_research(
    context: StubToolContext,
) -> None:
    context.state[STATE_PROFILE] = core_complete_profile()
    plan = get_application_plan(context)
    assert plan["profile"]["core_complete"] is True
    assert "research" in plan["next_step"].lower()


def test_with_research_done_the_next_step_is_documents(
    context: StubToolContext,
) -> None:
    context.state[STATE_PROFILE] = core_complete_profile()
    context.state[STATE_SHORTLIST] = shortlist_with_deadline()
    plan = get_application_plan(context)
    assert "document" in plan["next_step"].lower()


# --- Deadlines come from research, never from here --------------------------


def test_deadlines_surface_only_what_research_stored(
    context: StubToolContext,
) -> None:
    context.state[STATE_SHORTLIST] = shortlist_with_deadline()
    plan = get_application_plan(context)
    assert plan["deadlines"] == [
        {
            "university": "TU Delft",
            "program": "MSc Computer Science",
            "field": "application_deadline",
            "value": "15 January 2027",
            "tier": "VERIFIED",
        }
    ]


def test_no_research_means_no_deadlines_and_says_so(
    context: StubToolContext,
) -> None:
    plan = get_application_plan(context)
    assert plan["deadlines"] == []
    assert plan["deadline_note"]


# --- Boundaries -------------------------------------------------------------


def test_the_plan_never_writes_to_the_profile(context: StubToolContext) -> None:
    context.state[STATE_PROFILE] = core_complete_profile()
    before = str(context.state[STATE_PROFILE])
    get_application_plan(context)
    set_document_status("resume", "done", context)
    assert str(context.state[STATE_PROFILE]) == before
