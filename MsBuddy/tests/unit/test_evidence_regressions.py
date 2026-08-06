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

"""Regressions for defects found in the Phase 2 architecture audit.

Two real defects, both reproduced against the shipped code before the fix:

* **A genuine quote could carry a fabricated number.** The quote was checked;
  the value was not. The live run stored `tuition_academic_year = "2025/2026"`
  citing a quote that contained no year at all.
* **A corroborating third-party source silently displaced an official one.**
  An aggregator restating a university's own tuition figure downgraded the
  field from VERIFIED to REPORTED and replaced the citation.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.evidence import digit_runs, value_is_supported_by_quote
from app.program_store import (
    apply_claim,
    empty_shortlist,
    render_program,
    upsert_program,
)
from app.schemas import ProgramClaim
from app.tools import save_program_record

OFFICIAL_QUOTE = "Institutional rate, BSc EUR 17.310 MSc EUR 22.290 for the programme."
AGGREGATOR_QUOTE = "International students: EUR 22,290 per year at TU Delft."


def grounding(pairs: list[tuple[str, str]]) -> SimpleNamespace:
    chunks = [
        SimpleNamespace(web=SimpleNamespace(domain=None, title=d, uri=f"https://r/{i}"))
        for i, (d, _) in enumerate(pairs)
    ]
    supports = [
        SimpleNamespace(segment=SimpleNamespace(text=s), grounding_chunk_indices=[i])
        for i, (_, s) in enumerate(pairs)
    ]
    return SimpleNamespace(
        grounding_metadata=SimpleNamespace(
            grounding_chunks=chunks,
            grounding_supports=supports,
            web_search_queries=["tu delft msc tuition"],
        )
    )


class Ctx:
    def __init__(self, events: list[Any]) -> None:
        self.state: dict[str, Any] = {}
        self.invocation_id = "i"
        self.user_content = None
        self.session = SimpleNamespace(events=events)


def claim(field: str, value: str, domain: str, quote: str) -> ProgramClaim:
    return ProgramClaim(
        field_name=field, value=value, source_domain=domain, supporting_quote=quote
    )


@pytest.fixture
def both_sources() -> Ctx:
    return Ctx(
        [
            grounding(
                [
                    ("tudelft.nl", OFFICIAL_QUOTE),
                    ("mastersportal.com", AGGREGATOR_QUOTE),
                ]
            )
        ]
    )


# --- Defect 1: value must be present in its own quote ----------------------


def test_digit_runs_collapse_thousands_separators() -> None:
    assert digit_runs("EUR 22.290") == {"22290"}
    assert digit_runs("EUR 22,290") == {"22290"}
    assert digit_runs("15 January (23:59 CEST)") == {"15", "23", "59"}


def test_textual_values_are_not_digit_checked() -> None:
    """'EUR' and 'per year' are normalisations, not numeric claims."""
    assert value_is_supported_by_quote("EUR", OFFICIAL_QUOTE) is True
    assert value_is_supported_by_quote("per year", OFFICIAL_QUOTE) is True


def test_number_present_in_the_quote_is_supported() -> None:
    assert value_is_supported_by_quote("22290", OFFICIAL_QUOTE) is True
    assert value_is_supported_by_quote("22,290", AGGREGATOR_QUOTE) is True


def test_number_absent_from_the_quote_is_not_supported() -> None:
    assert value_is_supported_by_quote("15000", OFFICIAL_QUOTE) is False


def test_partial_digit_run_cannot_ride_on_a_larger_number() -> None:
    """'290' must not match a quoted '22.290'."""
    assert value_is_supported_by_quote("290", OFFICIAL_QUOTE) is False


def test_the_live_run_academic_year_case_is_now_refused() -> None:
    """The exact claim the live run wrongly stored."""
    assert value_is_supported_by_quote("2025/2026", OFFICIAL_QUOTE) is False


def test_fabricated_number_on_a_real_quote_is_rejected(both_sources: Ctx) -> None:
    result = save_program_record(
        "TU Delft",
        "MSc DSAIT",
        [claim("tuition_amount", "15000", "tudelft.nl", OFFICIAL_QUOTE)],
        both_sources,
    )
    assert result["status"] == "error"
    assert result["saved"] == []
    assert result["rejected"][0]["reason"] == "value_not_in_quote"


def test_unsupported_academic_year_is_rejected_end_to_end(both_sources: Ctx) -> None:
    result = save_program_record(
        "TU Delft",
        "MSc DSAIT",
        [claim("tuition_academic_year", "2025/2026", "tudelft.nl", OFFICIAL_QUOTE)],
        both_sources,
    )
    assert result["rejected"][0]["reason"] == "value_not_in_quote"


def test_supported_number_still_stores(both_sources: Ctx) -> None:
    """The fix must not block legitimate claims."""
    result = save_program_record(
        "TU Delft",
        "MSc DSAIT",
        [claim("tuition_amount", "22290", "tudelft.nl", OFFICIAL_QUOTE)],
        both_sources,
    )
    assert result["status"] == "success"


# --- Defect 2: multiple sources per fact, official preferred ---------------


def test_corroborating_aggregator_does_not_downgrade_an_official_fact(
    both_sources: Ctx,
) -> None:
    save_program_record(
        "TU Delft",
        "MSc DSAIT",
        [claim("tuition_amount", "22290", "tudelft.nl", OFFICIAL_QUOTE)],
        both_sources,
    )
    result = save_program_record(
        "TU Delft",
        "MSc DSAIT",
        [claim("tuition_amount", "22290", "mastersportal.com", AGGREGATOR_QUOTE)],
        both_sources,
    )
    field = result["record"]["fields"]["tuition_amount"]
    assert field["tier"] == "VERIFIED"
    assert field["source_domain"] == "tudelft.nl"


def test_corroboration_is_retained_not_discarded(both_sources: Ctx) -> None:
    """Third-party agreement is evidence, not noise (audit item 9)."""
    save_program_record(
        "TU Delft",
        "MSc DSAIT",
        [claim("tuition_amount", "22290", "tudelft.nl", OFFICIAL_QUOTE)],
        both_sources,
    )
    result = save_program_record(
        "TU Delft",
        "MSc DSAIT",
        [claim("tuition_amount", "22290", "mastersportal.com", AGGREGATOR_QUOTE)],
        both_sources,
    )
    field = result["record"]["fields"]["tuition_amount"]
    assert field["source_count"] == 2
    assert set(field["all_source_domains"]) == {"tudelft.nl", "mastersportal.com"}
    assert field["corroborations"]


def test_official_wins_even_when_the_aggregator_arrives_first(
    both_sources: Ctx,
) -> None:
    save_program_record(
        "TU Delft",
        "MSc DSAIT",
        [claim("tuition_amount", "22290", "mastersportal.com", AGGREGATOR_QUOTE)],
        both_sources,
    )
    result = save_program_record(
        "TU Delft",
        "MSc DSAIT",
        [claim("tuition_amount", "22290", "tudelft.nl", OFFICIAL_QUOTE)],
        both_sources,
    )
    assert result["record"]["fields"]["tuition_amount"]["tier"] == "VERIFIED"


def test_restating_the_same_source_does_not_duplicate(both_sources: Ctx) -> None:
    for _ in range(3):
        result = save_program_record(
            "TU Delft",
            "MSc DSAIT",
            [claim("tuition_amount", "22290", "tudelft.nl", OFFICIAL_QUOTE)],
            both_sources,
        )
    assert result["record"]["fields"]["tuition_amount"]["source_count"] == 1


def make_evidence(domain: str, tier: str, stamp: str) -> dict[str, Any]:
    return {
        "tier": tier,
        "source_domain": domain,
        "source_is_official": tier == "VERIFIED",
        "retrieved_at": stamp,
        "staleness_class": "CYCLICAL",
        "supporting_quote": "q",
    }


def test_conflicting_values_coexist_with_official_preferred() -> None:
    """Audit item 8: no silent overwrite; item 9: official ranks higher."""
    record = upsert_program(empty_shortlist(), "p", "U", "P")
    apply_claim(
        record,
        "application_deadline",
        "30 November",
        make_evidence("shiksha.com", "REPORTED", "2026-07-01T00:00:00+00:00"),
    )
    outcome = apply_claim(
        record,
        "application_deadline",
        "15 December",
        make_evidence("ethz.ch", "VERIFIED", "2026-07-02T00:00:00+00:00"),
    )
    assert outcome["value"] == "15 December"
    assert outcome["conflict_with"] == ["30 November"]

    rendered = render_program(record)["fields"]["application_deadline"]
    assert rendered["tier"] == "VERIFIED"
    assert rendered["conflicts"], "the disagreeing third-party value was dropped"
    assert rendered["source_count"] == 2


def test_a_newer_official_source_supersedes_an_older_official_one() -> None:
    record = upsert_program(empty_shortlist(), "p", "U", "P")
    apply_claim(
        record,
        "application_deadline",
        "1 December",
        make_evidence("ethz.ch", "VERIFIED", "2026-07-01T00:00:00+00:00"),
    )
    outcome = apply_claim(
        record,
        "application_deadline",
        "15 December",
        make_evidence("ethz.ch", "VERIFIED", "2026-07-20T00:00:00+00:00"),
    )
    assert outcome["value"] == "15 December"
    assert outcome["conflict_with"] == ["1 December"]
