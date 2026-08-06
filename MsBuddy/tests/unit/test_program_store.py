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

"""Shortlist state: conflicts, unknowns, staleness rendering."""

from __future__ import annotations

import datetime as dt

from app.config import STATE_SHORTLIST
from app.program_store import (
    apply_claim,
    empty_shortlist,
    make_program_id,
    read_shortlist,
    render_program,
    render_shortlist,
    unknown_fields,
    upsert_program,
    write_shortlist,
)
from app.reference.program_fields import ALL_FIELD_NAMES


def evidence(
    domain: str, tier: str, value: str, days_old: int = 0, klass: str = "VOLATILE"
) -> dict:
    stamp = dt.datetime.now(dt.UTC) - dt.timedelta(days=days_old)
    return {
        "tier": tier,
        "source_domain": domain,
        "source_is_official": tier == "VERIFIED",
        "source_url": f"https://example/{domain}",
        "retrieved_at": stamp.isoformat(timespec="seconds"),
        "staleness_class": klass,
        "supporting_quote": f"quote for {value}",
        "url_is_grounding_redirect": True,
    }


def program() -> dict:
    return upsert_program(empty_shortlist(), "eth-msc-cs", "ETH Zurich", "MSc CS")


def test_program_id_is_a_stable_slug() -> None:
    assert make_program_id("ETH Zürich", "MSc Computer Science").startswith("eth-z")
    assert make_program_id("A", "B") == make_program_id("A", "B")
    assert " " not in make_program_id("ETH Zurich", "MSc CS")


def test_upsert_is_idempotent() -> None:
    shortlist = empty_shortlist()
    first = upsert_program(shortlist, "p", "U", "P")
    second = upsert_program(shortlist, "p", "U", "P")
    assert first is second
    assert len(shortlist["programs"]) == 1


def test_same_value_restated_does_not_create_a_conflict() -> None:
    record = program()
    apply_claim(record, "duration", "2 years", evidence("ethz.ch", "VERIFIED", "2y"))
    outcome = apply_claim(
        record, "duration", "2 years", evidence("ethz.ch", "VERIFIED", "2y")
    )
    assert outcome["conflict_with"] == []
    assert record["fields"]["duration"]["conflicts"] == []


def test_disagreeing_sources_are_both_surfaced() -> None:
    """Spec §7.4.4 — never average away a conflict.

    Updated by the Phase 2 audit. This previously asserted last-write-wins:
    a later REPORTED value displaced an earlier VERIFIED one and the
    university's own figure was demoted to a footnote. Both values are still
    kept, but the official one is now the preferred value.
    """
    record = program()
    apply_claim(
        record,
        "application_deadline",
        "15 December 2026",
        evidence("ethz.ch", "VERIFIED", "dec"),
    )
    outcome = apply_claim(
        record,
        "application_deadline",
        "30 November 2026",
        evidence("shiksha.com", "REPORTED", "nov"),
    )
    assert outcome["value"] == "15 December 2026"
    assert outcome["conflict_with"] == ["30 November 2026"]

    stored = record["fields"]["application_deadline"]
    assert stored["value"] == "15 December 2026"
    assert stored["tier"] == "VERIFIED"
    assert stored["conflicts"][0]["value"] == "30 November 2026"
    assert stored["conflicts"][0]["evidence"]["source_domain"] == "shiksha.com", (
        "the disagreeing third-party value must remain attributable"
    )


def test_conflicts_are_rendered_to_the_caller() -> None:
    record = program()
    apply_claim(record, "duration", "2 years", evidence("ethz.ch", "VERIFIED", "a"))
    apply_claim(
        record, "duration", "18 months", evidence("shiksha.com", "REPORTED", "b")
    )
    rendered = render_program(record)
    assert rendered["fields"]["duration"]["conflicts"]


def test_unknown_fields_cover_the_whole_registry() -> None:
    record = program()
    assert set(unknown_fields(record)) == set(ALL_FIELD_NAMES)
    apply_claim(record, "duration", "2 years", evidence("ethz.ch", "VERIFIED", "x"))
    assert "duration" not in unknown_fields(record)


def test_render_flags_stale_fields_with_a_notice() -> None:
    record = program()
    apply_claim(
        record,
        "application_deadline",
        "15 Dec 2026",
        evidence("ethz.ch", "VERIFIED", "x", days_old=30, klass="VOLATILE"),
    )
    rendered = render_program(record)
    assert rendered["stale_fields"] == ["application_deadline"]
    assert rendered["fields"]["application_deadline"]["staleness_notice"]


def test_render_counts_tiers_separately() -> None:
    record = program()
    apply_claim(record, "duration", "2 years", evidence("ethz.ch", "VERIFIED", "a"))
    apply_claim(
        record, "tuition_amount", "1460", evidence("shiksha.com", "REPORTED", "b")
    )
    rendered = render_program(record)
    assert rendered["verified_count"] == 1
    assert rendered["reported_count"] == 1


def test_state_round_trip_uses_copies() -> None:
    state: dict = {}
    shortlist = read_shortlist(state, STATE_SHORTLIST)
    upsert_program(shortlist, "p", "U", "P")
    assert STATE_SHORTLIST not in state

    write_shortlist(state, STATE_SHORTLIST, shortlist)
    again = read_shortlist(state, STATE_SHORTLIST)
    again["programs"]["p"]["university"] = "MUTATED"
    assert state[STATE_SHORTLIST]["programs"]["p"]["university"] == "U"


def test_read_tolerates_corrupt_state() -> None:
    for junk in ("nonsense", 7, {"unexpected": True}, None):
        assert (
            read_shortlist({STATE_SHORTLIST: junk}, STATE_SHORTLIST)["programs"] == {}
        )


def test_render_shortlist_reports_every_program() -> None:
    shortlist = empty_shortlist()
    upsert_program(shortlist, "a", "U1", "P1")
    upsert_program(shortlist, "b", "U2", "P2")
    rendered = render_shortlist(shortlist)
    assert rendered["program_count"] == 2
    assert {p["program_id"] for p in rendered["programs"]} == {"a", "b"}
