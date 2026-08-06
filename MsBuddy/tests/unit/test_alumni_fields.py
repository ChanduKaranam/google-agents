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

"""The alumni field registry and the privacy boundary (C4 Stage A)."""

from __future__ import annotations

import datetime as dt

import pytest

from app.config import MAX_ALUMNI_RESULTS, MIN_PATTERN_N
from app.evidence import STALENESS_TTL_DAYS
from app.reference.alumni_fields import (
    ALL_FIELD_NAMES,
    ALUMNI_FIELDS,
    ALUMNI_STALENESS_CLASS,
    MAX_VALUE_LENGTH,
    PROHIBITED_FIELDS,
    contains_contact_details,
    is_prohibited_field,
    is_writable,
    staleness_class_for,
    validate_alumni_value,
)

# --- The registry ----------------------------------------------------------


def test_the_registry_is_an_allowlist() -> None:
    assert is_writable("employer") is True
    assert is_writable("favourite_colour") is False
    assert is_writable("") is False


def test_every_field_justifies_its_own_existence() -> None:
    """The test for inclusion is 'does this help evaluate a program'."""
    for spec in ALUMNI_FIELDS.values():
        assert spec.description
        assert spec.decision_value, f"{spec.name} has no stated decision value"


def test_every_alumni_claim_ages() -> None:
    for name in ALL_FIELD_NAMES:
        assert staleness_class_for(name) == "PERSON"


def test_the_person_ttl_is_the_one_the_evidence_layer_already_defines() -> None:
    assert STALENESS_TTL_DAYS[ALUMNI_STALENESS_CLASS] == 180


def test_the_agreed_caps_are_wired() -> None:
    assert MAX_ALUMNI_RESULTS == 10
    assert MIN_PATTERN_N == 5


# --- The privacy boundary --------------------------------------------------


@pytest.mark.parametrize(
    "field",
    [
        "email", "phone", "address", "home_address", "location",
        "gender", "pronouns", "nationality", "citizenship", "ethnicity",
        "religion", "date_of_birth", "age", "marital_status",
        "health", "salary", "photo", "twitter", "linkedin",
    ],
)  # fmt: skip
def test_prohibited_fields_are_refused(field: str) -> None:
    assert is_prohibited_field(field) is True
    assert is_writable(field) is False


def test_prohibition_is_case_insensitive() -> None:
    assert is_prohibited_field("EMAIL") is True
    assert is_prohibited_field("  Phone  ") is True


def test_no_prohibited_field_is_also_a_registry_field() -> None:
    """The two lists must not contradict each other."""
    assert PROHIBITED_FIELDS.isdisjoint(set(ALL_FIELD_NAMES))


def test_a_prohibited_field_is_refused_even_with_a_perfect_value() -> None:
    """A source publishing something does not make it ours to keep."""
    result = validate_alumni_value("email", "ada@example.com")
    assert result["status"] == "error"
    assert result["reason"] == "unknown_field"


# --- Contact details smuggled into a permitted field -----------------------


@pytest.mark.parametrize(
    "value",
    [
        "ada@example.com",
        "Contact: ada.lovelace@tudelft.nl",
        "+31 6 1234 5678",
        "call 020 123 4567",
    ],
)
def test_contact_details_are_detected_in_values(value: str) -> None:
    assert contains_contact_details(value) is True


@pytest.mark.parametrize(
    "value",
    ["Senior Data Scientist", "MSc Computer Science", "2021", "Booking.com"],
)
def test_ordinary_values_are_not_flagged_as_contact_details(value: str) -> None:
    assert contains_contact_details(value) is False


def test_a_role_carrying_an_email_is_refused() -> None:
    """Checking the field name alone would let this through."""
    result = validate_alumni_value("role", "Data Scientist — ada@example.com")
    assert result["status"] == "error"
    assert result["reason"] == "contact_details_in_value"


# --- Value validation ------------------------------------------------------


def test_a_well_formed_value_passes() -> None:
    result = validate_alumni_value("employer", "  Booking.com  ")
    assert result == {"status": "ok", "value": "Booking.com"}


def test_an_empty_value_is_refused() -> None:
    assert validate_alumni_value("employer", "")["reason"] == "empty_value"
    assert validate_alumni_value("employer", "   ")["reason"] == "empty_value"


def test_a_prose_length_value_is_refused() -> None:
    result = validate_alumni_value("role", "x" * (MAX_VALUE_LENGTH + 1))
    assert result["reason"] == "value_too_long"


# --- Graduation year: the field most likely to be invented -----------------


def test_a_four_digit_year_is_accepted() -> None:
    assert validate_alumni_value("graduation_year", "2021") == {
        "status": "ok",
        "value": "2021",
    }


@pytest.mark.parametrize("value", ["21", "'21", "2021-2023", "spring 2021", "MMXXI"])
def test_anything_that_is_not_a_four_digit_year_is_refused(value: str) -> None:
    result = validate_alumni_value("graduation_year", value)
    assert result["status"] == "error"
    assert result["reason"] == "not_a_four_digit_year"


def test_an_implausible_year_is_refused() -> None:
    assert validate_alumni_value("graduation_year", "1650")["reason"] == (
        "year_out_of_range"
    )
    far_future = str(dt.datetime.now(dt.UTC).year + 50)
    assert validate_alumni_value("graduation_year", far_future)["reason"] == (
        "year_out_of_range"
    )


def test_an_expected_graduation_year_is_allowed() -> None:
    """A currently-enrolled student's published expected year is legitimate."""
    next_year = str(dt.datetime.now(dt.UTC).year + 2)
    assert validate_alumni_value("graduation_year", next_year)["status"] == "ok"


def test_validation_is_deterministic() -> None:
    for _ in range(50):
        assert validate_alumni_value("graduation_year", "2021")["value"] == "2021"


def test_every_refusal_names_a_reason() -> None:
    for field, value in (
        ("nope", "x"),
        ("employer", ""),
        ("graduation_year", "21"),
        ("role", "a@b.com"),
    ):
        result = validate_alumni_value(field, value)
        assert result["status"] == "error"
        assert result["reason"]
        assert result["message"]


# --- Contact detection must not swallow ordinary numbers -------------------


@pytest.mark.parametrize(
    "value",
    ["2021-2023", "2019 2020 2021", "MSc 2021", "120 ECTS", "GPA 3.85"],
)
def test_ordinary_number_patterns_are_not_read_as_phone_numbers(value: str) -> None:
    """Caught in Stage A: a '7+ digits with separators' rule also matches a
    year range, which would have refused `2021-2023` for the wrong reason and
    hidden the real one."""
    assert contains_contact_details(value) is False


@pytest.mark.parametrize("value", ["+31 6 1234 5678", "(020) 123-4567", "555 123 4567"])
def test_real_phone_shapes_are_still_caught(value: str) -> None:
    assert contains_contact_details(value) is True


def test_a_year_range_is_refused_as_a_year_not_as_contact_details() -> None:
    result = validate_alumni_value("graduation_year", "2021-2023")
    assert result["reason"] == "not_a_four_digit_year"
