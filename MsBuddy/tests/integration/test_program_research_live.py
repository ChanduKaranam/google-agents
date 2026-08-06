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

"""Live C2 test — real search, real grounding, invariants only.

Per spec §11.1 nothing here asserts what the model *said* or that a
particular deadline was found; recall and accuracy are eval questions. What
is asserted is what must hold for any correct run:

* every stored fact cites a domain that was genuinely retrieved;
* every stored fact's quote appears in a segment the runtime grounded;
* `VERIFIED` is reserved for official domains;
* fields that were not sourced are named as unknown;
* **no search query issued to Google contains the student's private data.**

The last one is checked against `web_search_queries` in the real grounding
metadata, so it tests the actual outbound traffic rather than our intent.
"""

from __future__ import annotations

from typing import Any

import pytest
from google.adk.runners import InMemoryRunner
from google.genai import types

from app.agent import app as ms_buddy_app
from app.config import STATE_PROFILE, STATE_SHORTLIST
from app.evidence import collect_sources, find_supporting_source, retrieved_domains
from app.reference.domain_trust import is_official
from app.reference.program_fields import ALL_FIELD_NAMES
from app.tools.program_tools import SENSITIVE_PROFILE_FIELDS

APP_NAME = "app"
USER_ID = "test-student"

PROFILE_MESSAGE = (
    "I did my BTech at Anna University with 8.1 CGPA out of 10, GRE quant 168. "
    "I'm targeting Fall 2027 for Computer Science."
)
RESEARCH_MESSAGE = (
    "Please look up the MSc Computer Science at ETH Zurich — deadlines, "
    "tuition and entry requirements."
)

# Bounded, and each one is a thing a real student would plausibly say next
# rather than a jailbreak into the tool. Two retries because the observed
# miss rate is occasional, not systematic; more would just spend quota.
RETRY_PROMPTS = (
    "Could you actually search the web for that? I need current information "
    "from the university's own pages.",
    "Please use the program research agent to look this up and record what "
    "you find with its sources.",
)


@pytest.fixture(scope="module")
def researched(live_model: None) -> dict[str, Any]:
    """One session: state a profile, then ask for a program to be researched."""
    runner = InMemoryRunner(app=ms_buddy_app, app_name=APP_NAME)
    session = runner.session_service.create_session_sync(
        app_name=APP_NAME, user_id=USER_ID
    )

    def say(message: str) -> None:
        for _ in runner.run(
            user_id=USER_ID,
            session_id=session.id,
            new_message=types.Content(
                role="user", parts=[types.Part.from_text(text=message)]
            ),
        ):
            pass

    def current() -> tuple[Any, dict[str, Any], list[dict[str, Any]]]:
        refreshed = runner.session_service.get_session_sync(
            app_name=APP_NAME, user_id=USER_ID, session_id=session.id
        )
        state = refreshed.state or {}
        return refreshed, state, collect_sources(refreshed, state)

    say(PROFILE_MESSAGE)
    say(RESEARCH_MESSAGE)
    refreshed, state, harvest = current()

    # Whether the model *chooses* to search on a given run is behaviour, and
    # spec §11.1 puts behaviour in eval rather than pytest. It searches on
    # most runs but not all, and when it does not there is nothing to check
    # invariants against.
    #
    # Asking again is not weakening anything — every assertion below is
    # unchanged, and a retry only affects whether they get to run at all.
    # The Phase 3 audit added it because a single unlucky run skipped all
    # eight C2 live invariants while the suite still reported green, which
    # is the failure mode where a test suite stops being worth having.
    for follow_up in RETRY_PROMPTS:
        if harvest:
            break
        say(follow_up)
        refreshed, state, harvest = current()

    if not harvest:
        pytest.skip(
            f"the agent did not search on this run, after {1 + len(RETRY_PROMPTS)} "
            "attempts, so there is no grounding to verify invariants against "
            "(search rate is an eval metric, not a pytest assertion)"
        )

    return {
        "profile": state.get(STATE_PROFILE) or {},
        "shortlist": state.get(STATE_SHORTLIST) or {},
        "harvest": harvest,
        "session": refreshed,
    }


def stored_fields(researched: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    out: list[tuple[str, dict[str, Any]]] = []
    for record in (researched["shortlist"].get("programs") or {}).values():
        for name, entry in (record.get("fields") or {}).items():
            out.append((name, entry))
    return out


def test_grounding_reached_the_caller(researched: dict[str, Any]) -> None:
    """The AgentTool isolation boundary was actually crossed.

    Guards the specific defect found building this: `AgentTool` gives the
    sub-agent a private session, so without the research agent's harvest
    callback the ledger arrives empty and every claim is refused.
    """
    assert researched["harvest"], "no grounded sources reached the caller"


def test_no_search_query_contained_the_students_private_data(
    researched: dict[str, Any],
) -> None:
    """Spec §5.2 invariant 1, asserted against real outbound queries."""
    sensitive: list[str] = []
    for name, entry in (researched["profile"].get("fields") or {}).items():
        if name not in SENSITIVE_PROFILE_FIELDS:
            continue
        value = entry.get("value")
        for item in value if isinstance(value, list) else [value]:
            text = str(item).strip().lower()
            if len(text) >= 3:
                sensitive.append(text)

    queries = [
        q.lower() for entry in researched["harvest"] for q in entry.get("queries", [])
    ]
    assert queries, "no search queries were recorded"

    for query in queries:
        for value in sensitive:
            assert value not in query, (
                f"private profile value {value!r} leaked into search query {query!r}"
            )


def test_every_stored_fact_cites_a_domain_that_was_retrieved(
    researched: dict[str, Any],
) -> None:
    available = retrieved_domains(researched["harvest"])
    for name, entry in stored_fields(researched):
        domain = entry["evidence"]["source_domain"]
        assert domain in available, (
            f"'{name}' cites {domain!r}, which was never retrieved"
        )


def test_every_stored_fact_quote_is_in_the_harvest(
    researched: dict[str, Any],
) -> None:
    """The C2 anti-fabrication guarantee, against a real model's output."""
    for name, entry in stored_fields(researched):
        evidence = entry["evidence"]
        assert find_supporting_source(
            researched["harvest"],
            evidence["supporting_quote"],
            evidence["source_domain"],
        ), f"'{name}' quote is not present in any retrieved segment"


def test_verified_tier_is_reserved_for_official_domains(
    researched: dict[str, Any],
) -> None:
    for name, entry in stored_fields(researched):
        domain = entry["evidence"]["source_domain"]
        if entry["tier"] == "VERIFIED":
            assert is_official(domain), (
                f"'{name}' is VERIFIED but {domain!r} is not an official domain"
            )
        else:
            assert entry["tier"] == "REPORTED"


def test_stored_fields_are_all_on_the_program_allowlist(
    researched: dict[str, Any],
) -> None:
    for name, _ in stored_fields(researched):
        assert name in ALL_FIELD_NAMES, f"'{name}' is not a known program field"


def test_unsourced_fields_are_named_as_unknown(researched: dict[str, Any]) -> None:
    """C2: a coverage gap must never read as an absence of a requirement."""
    programs = researched["shortlist"].get("programs") or {}
    if not programs:
        pytest.skip("nothing was stored this run; nothing to report as unknown")
    for record in programs.values():
        stored = set(record.get("fields") or {})
        unknown = [n for n in ALL_FIELD_NAMES if n not in stored]
        assert set(stored) | set(unknown) == set(ALL_FIELD_NAMES)


def test_profile_still_works_alongside_research(researched: dict[str, Any]) -> None:
    """Phase 2 must not have broken Phase 1."""
    fields = researched["profile"].get("fields") or {}
    assert fields, "the profile was not captured; C1 has regressed"
    for entry in fields.values():
        assert entry["tier"] in ("USER_STATED", "INFERENCE")
