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

"""The five profile tools, exercised against a stub tool context.

No network and no model: these tools are deterministic by design, which is
exactly why they can be pytest-tested (spec §11.1).
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.config import STATE_PROFILE
from app.schemas import ExtractedField
from app.tools import (
    clear_profile_fields,
    get_profile,
    normalize_gpa,
    profile_completeness,
    save_profile_fields,
)


class StubToolContext:
    """Minimal stand-in exposing only what the profile tools actually use."""

    def __init__(self, student_text: str) -> None:
        self.state: dict[str, Any] = {}
        self.invocation_id = "test-invocation"
        self.user_content = SimpleNamespace(
            role="user", parts=[SimpleNamespace(text=student_text)]
        )
        self.session = SimpleNamespace(events=[])


STUDENT_MESSAGE = (
    "I did my BTech in ECE with 8.1 CGPA out of 10. GRE 168 quant, 159 verbal. "
    "Targeting Fall 2027 in Canada and Germany for Data Science. "
    "My budget is about 45000 CAD."
)


@pytest.fixture
def ctx() -> StubToolContext:
    return StubToolContext(STUDENT_MESSAGE)


def entry(field_name: str, value: str, evidence: str) -> ExtractedField:
    return ExtractedField(field_name=field_name, value=value, evidence_span=evidence)


# --- save_profile_fields ---------------------------------------------------


def test_saves_fields_the_student_actually_stated(ctx: StubToolContext) -> None:
    result = save_profile_fields(
        [
            entry("gre_quant", "168", "GRE 168 quant"),
            entry("target_intake_year", "2027", "Fall 2027"),
        ],
        ctx,
    )
    assert result["status"] == "success"
    assert {e["field"] for e in result["saved"]} == {"gre_quant", "target_intake_year"}
    stored = ctx.state[STATE_PROFILE]["fields"]
    assert stored["gre_quant"]["value"] == 168
    assert stored["gre_quant"]["tier"] == "USER_STATED"


def test_field_the_student_never_mentioned_is_refused(ctx: StubToolContext) -> None:
    """The central C1 guarantee: no unstated field can be written."""
    result = save_profile_fields(
        [entry("toefl_total", "110", "TOEFL 110 overall")], ctx
    )
    assert result["status"] == "error"
    assert result["saved"] == []
    assert result["rejected"][0]["reason"] == "unverified_evidence"
    assert STATE_PROFILE not in ctx.state


def test_paraphrased_evidence_is_refused(ctx: StubToolContext) -> None:
    result = save_profile_fields(
        [entry("gre_quant", "168", "the student scored well on quant")], ctx
    )
    assert result["rejected"][0]["reason"] == "unverified_evidence"


def test_model_cannot_manufacture_its_own_evidence(ctx: StubToolContext) -> None:
    ctx.session = SimpleNamespace(
        events=[
            SimpleNamespace(
                content=SimpleNamespace(
                    role="model",
                    parts=[SimpleNamespace(text="TOEFL 110 overall")],
                )
            )
        ]
    )
    result = save_profile_fields([entry("toefl_total", "110", "TOEFL 110")], ctx)
    assert result["saved"] == []


def test_out_of_range_value_is_refused_with_a_reason(ctx: StubToolContext) -> None:
    result = save_profile_fields([entry("gre_quant", "800", "GRE 168 quant")], ctx)
    assert result["rejected"][0]["reason"] == "invalid_value"
    assert "valid range" in result["rejected"][0]["message"]


def test_unknown_field_is_refused(ctx: StubToolContext) -> None:
    result = save_profile_fields([entry("iq_score", "150", "BTech in ECE")], ctx)
    assert result["rejected"][0]["reason"] == "invalid_value"


def test_partial_status_when_some_entries_fail(ctx: StubToolContext) -> None:
    result = save_profile_fields(
        [
            entry("gre_quant", "168", "GRE 168 quant"),
            entry("toefl_total", "110", "TOEFL 110"),
        ],
        ctx,
    )
    assert result["status"] == "partial"
    assert len(result["saved"]) == 1
    assert len(result["rejected"]) == 1


def test_empty_entry_list_is_an_error(ctx: StubToolContext) -> None:
    result = save_profile_fields([], ctx)
    assert result["status"] == "error"
    assert "known_fields" in result


def test_accepts_plain_dicts_as_well_as_models(ctx: StubToolContext) -> None:
    """ADK may hand tool args through as dicts rather than model instances."""
    result = save_profile_fields(
        [
            {
                "field_name": "gre_verbal",
                "value": "159",
                "evidence_span": "159 verbal",
            }
        ],
        ctx,
    )
    assert result["status"] == "success"


def test_gpa_pair_triggers_derivation(ctx: StubToolContext) -> None:
    result = save_profile_fields(
        [
            entry("gpa_value", "8.1", "8.1 CGPA out of 10"),
            entry("gpa_scale", "cgpa_10", "8.1 CGPA out of 10"),
        ],
        ctx,
    )
    assert result["status"] == "success"
    assert result["derived"][0]["us_4pt_equivalent"] == 3.24
    derived = ctx.state[STATE_PROFILE]["fields"]["gpa_us_4pt"]
    assert derived["tier"] == "INFERENCE"
    assert derived["rule_id"] == "gpa_conv:cgpa_10_to_us_4pt:v1"


def test_percentage_misread_as_cgpa_is_caught(ctx: StubToolContext) -> None:
    """The named C1 failure case, blocked at the tool boundary."""
    context = StubToolContext("I scored 72% in my BTech")
    result = save_profile_fields(
        [
            entry("gpa_value", "72", "72%"),
            entry("gpa_scale", "cgpa_10", "72%"),
        ],
        context,
    )
    assert result["derived"][0]["status"] == "error"
    assert result["derived"][0]["reason"] == "out_of_range"
    assert "gpa_us_4pt" not in context.state[STATE_PROFILE]["fields"]


# --- get_profile / completeness -------------------------------------------


def test_get_profile_on_empty_state(ctx: StubToolContext) -> None:
    result = get_profile(ctx)
    assert result["status"] == "success"
    assert result["is_empty"] is True
    assert result["profile"]["fields"] == {}


def test_get_profile_returns_provenance(ctx: StubToolContext) -> None:
    save_profile_fields([entry("gre_quant", "168", "GRE 168 quant")], ctx)
    field = get_profile(ctx)["profile"]["fields"]["gre_quant"]
    assert field["tier"] == "USER_STATED"
    assert field["evidence_span"] == "GRE 168 quant"
    assert field["recorded_at"]


def test_completeness_lists_missing_core_fields(ctx: StubToolContext) -> None:
    report = profile_completeness(ctx)
    assert report["status"] == "success"
    assert report["core_complete"] is False
    assert "specialization_interest" in report["core_missing"]
    assert all(m["why_it_matters"] for m in report["missing_fields"])


# --- normalize_gpa ---------------------------------------------------------


def test_normalize_gpa_is_pure_and_does_not_touch_state(
    ctx: StubToolContext,
) -> None:
    result = normalize_gpa(8.1, "cgpa_10")
    assert result["us_4pt_equivalent"] == 3.24
    assert result["tier"] == "INFERENCE"
    assert ctx.state == {}


def test_normalize_gpa_reports_supported_scales_on_error() -> None:
    result = normalize_gpa(8.1, "cgpa_9")
    assert result["status"] == "error"
    assert "cgpa_10" in result["supported_scales"]


# --- clear_profile_fields --------------------------------------------------


def test_clear_named_field(ctx: StubToolContext) -> None:
    save_profile_fields([entry("gre_quant", "168", "GRE 168 quant")], ctx)
    result = clear_profile_fields(["gre_quant"], ctx)
    assert result["removed"] == ["gre_quant"]
    assert result["remaining_field_count"] == 0


def test_clear_reports_fields_that_were_not_present(ctx: StubToolContext) -> None:
    save_profile_fields([entry("gre_quant", "168", "GRE 168 quant")], ctx)
    result = clear_profile_fields(["gre_quant", "toefl_total"], ctx)
    assert result["not_found"] == ["toefl_total"]


def test_empty_clear_request_is_refused(ctx: StubToolContext) -> None:
    """An empty list must never be read as 'delete everything'."""
    result = clear_profile_fields([], ctx)
    assert result["status"] == "error"


def test_clear_all_requires_the_explicit_sentinel(ctx: StubToolContext) -> None:
    save_profile_fields(
        [
            entry("gre_quant", "168", "GRE 168 quant"),
            entry("gre_verbal", "159", "159 verbal"),
        ],
        ctx,
    )
    result = clear_profile_fields(["__all__"], ctx)
    assert result["cleared_all"] is True
    assert sorted(result["removed"]) == ["gre_quant", "gre_verbal"]
    assert ctx.state[STATE_PROFILE]["fields"] == {}
