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

"""Field registry validation — the allowlist and coercion layer."""

from __future__ import annotations

import pytest

from app.reference.profile_fields import (
    CORE_FIELDS,
    DERIVED_FIELDS,
    FIELDS,
    is_writable,
    validate_field,
)


def test_every_field_explains_why_it_matters() -> None:
    """C1 requires the completeness report to say why each field matters."""
    for name, spec in FIELDS.items():
        assert spec.why_it_matters.strip(), f"{name} has no rationale"
        assert spec.why_it_matters.endswith("."), f"{name} rationale not a sentence"


def test_core_fields_are_the_ones_program_research_needs() -> None:
    assert set(CORE_FIELDS) == {
        "undergrad_degree",
        "gpa_value",
        "gpa_scale",
        "target_intake_term",
        "target_intake_year",
        "target_countries",
        "specialization_interest",
    }


def test_unknown_field_is_rejected() -> None:
    result = validate_field("favourite_colour", "blue")
    assert result["ok"] is False
    assert "not a known profile field" in result["message"]
    assert is_writable("favourite_colour") is False


def test_derived_fields_cannot_be_written_directly() -> None:
    """Keeping derived names out of FIELDS is what makes this structural."""
    for name in DERIVED_FIELDS:
        assert is_writable(name) is False
        result = validate_field(name, "3.5")
        assert result["ok"] is False
        assert "derived field" in result["message"]


# --- Year: the "Fall 25" ambiguity failure case ----------------------------


def test_two_digit_year_is_rejected_as_ambiguous() -> None:
    result = validate_field("target_intake_year", "25")
    assert result["ok"] is False
    assert "ambiguous" in result["message"]


def test_four_digit_year_is_accepted_as_int() -> None:
    result = validate_field("target_intake_year", "2027")
    assert result == {"ok": True, "value": 2027}


def test_year_outside_supported_range_is_rejected() -> None:
    assert validate_field("target_intake_year", "1999")["ok"] is False
    assert validate_field("target_intake_year", "2200")["ok"] is False


# --- Enums -----------------------------------------------------------------


def test_enum_is_case_insensitive_but_closed() -> None:
    assert validate_field("target_intake_term", "Fall") == {
        "ok": True,
        "value": "fall",
    }
    bad = validate_field("target_intake_term", "monsoon")
    assert bad["ok"] is False
    assert "Valid values" in bad["message"]


def test_gpa_scale_choices_come_from_the_scale_table() -> None:
    assert validate_field("gpa_scale", "cgpa_10")["ok"] is True
    assert validate_field("gpa_scale", "cgpa_9")["ok"] is False


# --- Numbers ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("field_name", "raw", "expected"),
    [
        ("gre_quant", "168", 168),
        ("work_experience_months", "36", 36),
        ("ielts_overall", "7.5", 7.5),
        ("gpa_value", "8.1", 8.1),
    ],
)
def test_numeric_coercion(field_name: str, raw: str, expected: float) -> None:
    assert validate_field(field_name, raw) == {"ok": True, "value": expected}


@pytest.mark.parametrize(
    ("field_name", "raw"),
    [
        ("gre_quant", "129"),
        ("gre_quant", "171"),
        ("gre_awa", "6.5"),
        ("toefl_total", "121"),
        ("gmat_total", "199"),
        ("gre_quant", "not a score"),
    ],
)
def test_numbers_outside_their_range_are_rejected(field_name: str, raw: str) -> None:
    assert validate_field(field_name, raw)["ok"] is False


def test_integer_field_rejects_fractional_value() -> None:
    result = validate_field("gre_quant", "165.5")
    assert result["ok"] is False
    assert "whole number" in result["message"]


# --- Lists and text --------------------------------------------------------


def test_list_field_splits_on_commas() -> None:
    result = validate_field("target_countries", "Canada, Germany , Netherlands")
    assert result == {"ok": True, "value": ["Canada", "Germany", "Netherlands"]}


def test_blank_values_are_rejected() -> None:
    assert validate_field("undergrad_degree", "   ")["ok"] is False
    assert validate_field("target_countries", " , , ")["ok"] is False


def test_gpa_value_declares_its_scale_dependency() -> None:
    """A number without its scale is the C1 failure case; the registry knows."""
    assert FIELDS["gpa_value"].requires == ("gpa_scale",)
    assert FIELDS["budget_ceiling"].requires == ("budget_currency",)
