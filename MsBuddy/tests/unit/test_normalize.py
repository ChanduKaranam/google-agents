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

"""Stage ① normalization, fixture-first.

The strings marked REAL below were retrieved by C2 during live runs and are
the reason each parser is shaped the way it is:

* ``$15,605.``  ``$15,590.``        gatech.edu, live harvest
* ``EUR 17.310`` ``EUR 22.290``     tudelft.nl, Phase 2 audit run
* ``22,290``                        mastersportal.com, Phase 2 audit run
* ``CHF 1460 per semester``         ethz.ch, Phase 2 fixtures
* ``2025/2026``                     tudelft.nl, Phase 2 audit run
* ``If provided, GRE scores will be considered.``   gatech.edu, live harvest
* ``A minimum overall score of 7.5 is required...`` gatech.edu, live harvest
* ``15 December 2026``              Phase 2 fixtures
* ``24 Months`` ``15 January (23:59 CEST)``  Phase 3 architecture note

The dot-vs-comma cases are the point of the exercise: ``$15,605.`` and
``EUR 17.310`` use opposite conventions and both mean five figures.
"""

from __future__ import annotations

import pytest

from app.normalize import (
    AMBIGUOUS,
    MISSING,
    OK,
    UNSUPPORTED,
    extract_provenance,
    normalize_boolean,
    normalize_deadline,
    normalize_duration,
    normalize_money,
    normalize_program,
    normalize_test_requirement,
    parse_amount,
    parse_basis,
    resolve_currency,
)

# --- Amount parsing --------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("15605", 15605.0),
        ("$15,605.", 15605.0),  # REAL gatech.edu
        ("$15,590.", 15590.0),  # REAL gatech.edu
        ("EUR 17.310", 17310.0),  # REAL tudelft.nl — dot is thousands
        ("EUR 22.290", 22290.0),  # REAL tudelft.nl
        ("22,290", 22290.0),  # REAL mastersportal.com
        ("1460", 1460.0),  # REAL ethz.ch
        ("1'460", 1460.0),  # Swiss apostrophe grouping
        ("1 460", 1460.0),
        ("1.234.567", 1234567.0),
        ("1460.50", 1460.5),  # two digits after -> decimal
        ("1.460,50", 1460.5),  # both separators, comma last -> decimal
        ("1,460.50", 1460.5),  # both separators, dot last -> decimal
        ("1.5", 1.5),
        ("0", 0.0),
    ],
)
def test_amounts_that_parse(text: str, expected: float) -> None:
    result = parse_amount(text)
    assert result["status"] == OK, result
    assert result["amount"] == expected


def test_the_two_conventions_reach_the_same_number() -> None:
    """The whole reason the separator rule exists."""
    assert parse_amount("22.290")["amount"] == parse_amount("22,290")["amount"]


def test_two_amounts_in_one_value_is_ambiguous() -> None:
    """REAL: the TU Delft page quotes a BSc and an MSc fee in one sentence."""
    result = parse_amount("17.310 and 22.290")
    assert result["status"] == AMBIGUOUS
    assert "multiple_amounts" in result["reason"]


def test_four_digit_group_after_a_separator_is_refused() -> None:
    result = parse_amount("22.2905")
    assert result["status"] == AMBIGUOUS
    assert "separator_reading_unclear" in result["reason"]


def test_malformed_amounts() -> None:
    assert parse_amount("tuition is free")["status"] == UNSUPPORTED
    assert parse_amount("")["status"] == MISSING
    assert parse_amount("   ")["status"] == MISSING


# --- Currency --------------------------------------------------------------


def test_currency_codes_and_symbols_resolve() -> None:
    assert resolve_currency("EUR")["currency"] == "EUR"
    assert resolve_currency("chf")["currency"] == "CHF"
    assert resolve_currency("", "EUR 22.290")["currency"] == "EUR"
    assert resolve_currency("", "€ 22.290")["currency"] == "EUR"
    assert resolve_currency("Euro")["currency"] == "EUR"


def test_dollar_sign_alone_is_refused() -> None:
    """REAL: gatech.edu publishes '$15,605.' with no ISO code anywhere."""
    result = resolve_currency("", "$15,605.")
    assert result["status"] == AMBIGUOUS
    assert "USD, CAD, AUD" in result["reason"]


def test_declared_currency_beats_the_symbol_in_the_amount() -> None:
    assert resolve_currency("USD", "$15,605.")["currency"] == "USD"


def test_unstated_currency_is_missing_not_unsupported() -> None:
    """A bare number means 'not stated', which is a different failure."""
    result = resolve_currency("", "15605")
    assert result["status"] == MISSING
    assert result["reason"] == "currency_not_stated"


def test_declared_garbage_currency_is_named_as_such() -> None:
    assert resolve_currency("galleons")["status"] == UNSUPPORTED


# --- Basis -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "basis"),
    [
        ("per year", "year"),
        ("per academic year", "year"),
        ("annually", "year"),
        ("per annum", "year"),
        ("per semester", "semester"),  # REAL ethz.ch
        ("per term", "term"),
        ("whole programme", "program"),
        ("total tuition for the full program", "program"),
        ("per ECTS credit", "credit"),
    ],
)
def test_basis_phrases(text: str, basis: str) -> None:
    assert parse_basis(text) == {"status": OK, "basis": basis}


def test_unstated_basis_is_missing() -> None:
    assert parse_basis("")["status"] == MISSING


# --- Money end to end ------------------------------------------------------


def test_per_year_fee_normalizes_and_annualizes() -> None:
    result = normalize_money("EUR 22.290", "EUR", "per year", duration_months=24)
    assert result["status"] == OK
    assert result["value"] == 22290.0
    assert result["unit"] == "EUR"
    assert result["basis"] == "year"
    assert result["annual_amount"] == 22290.0
    assert result["total_program_amount"] == 44580.0


def test_whole_program_fee_annualizes_against_a_known_duration() -> None:
    result = normalize_money("40000", "USD", "whole programme", duration_months=18)
    assert result["annual_amount"] == pytest.approx(26666.67)
    assert result["total_program_amount"] == 40000.0


def test_per_semester_fee_is_never_annualized() -> None:
    """REAL ethz.ch. Semesters per year is not published, so multiplying by
    two would be an invented number."""
    result = normalize_money("1460", "CHF", "per semester", duration_months=24)
    assert result["status"] == OK
    assert result["value"] == 1460.0
    assert result["annual_amount"] is None
    assert "varies by institution" in result["annualization_reason"]


def test_missing_basis_makes_the_fee_non_comparable() -> None:
    """A price without a basis is not a cost."""
    result = normalize_money("22290", "EUR", "")
    assert result["status"] == MISSING
    assert result["reason"] == "basis_not_stated"
    assert result["value"] is None


def test_missing_currency_makes_the_fee_non_comparable() -> None:
    result = normalize_money("22290", "", "per year")
    assert result["status"] == MISSING
    assert result["value"] is None


def test_program_fee_without_duration_reports_why_it_cannot_annualize() -> None:
    result = normalize_money("40000", "USD", "whole programme")
    assert result["status"] == OK
    assert result["annual_amount"] is None
    assert result["annualization_reason"] == "annualization_needs_a_normalized_duration"


def test_money_never_invents_a_value_on_failure() -> None:
    for bad in ("", "free", "17.310 and 22.290"):
        assert normalize_money(bad, "EUR", "per year")["value"] is None


# --- Duration --------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "months"),
    [
        ("2 years", 24.0),
        ("24 Months", 24.0),  # REAL, and case-insensitive
        ("18 months", 18.0),
        ("1.5 years", 18.0),
        ("12 mo", 12.0),
        ("2 yrs", 24.0),
        ("2 years (120 ECTS)", 24.0),  # unit it cannot use, one it can
    ],
)
def test_durations_that_parse(text: str, months: float) -> None:
    result = normalize_duration(text)
    assert result["status"] == OK, result
    assert result["value"] == months
    assert result["unit"] == "months"


@pytest.mark.parametrize("text", ["1.5 - 2 years", "18-24 months", "2 to 3 years"])
def test_a_range_is_ambiguous_not_a_midpoint(text: str) -> None:
    result = normalize_duration(text)
    assert result["status"] == AMBIGUOUS
    assert "range" in result["reason"]


def test_semesters_are_refused_with_a_reason() -> None:
    result = normalize_duration("4 semesters")
    assert result["status"] == UNSUPPORTED
    assert "semester length varies" in result["reason"]


def test_credits_are_not_a_duration() -> None:
    result = normalize_duration("120 EC")
    assert result["status"] == UNSUPPORTED
    assert "workload, not elapsed time" in result["reason"]


def test_word_numbers_are_refused_rather_than_guessed() -> None:
    assert normalize_duration("two years")["status"] == UNSUPPORTED


def test_unrecognised_language_is_refused() -> None:
    assert normalize_duration("2 Jahre")["status"] == UNSUPPORTED


def test_contradictory_durations_are_ambiguous() -> None:
    result = normalize_duration("2 years or 30 months")
    assert result["status"] == AMBIGUOUS


def test_missing_duration() -> None:
    assert normalize_duration("")["status"] == MISSING


def test_zero_duration_is_refused() -> None:
    assert normalize_duration("0 months")["status"] == UNSUPPORTED


# --- Deadline --------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "iso"),
    [
        ("15 December 2026", "2026-12-15"),  # REAL fixture
        ("December 15, 2026", "2026-12-15"),
        ("15th December 2026", "2026-12-15"),
        ("15 Dec 2026", "2026-12-15"),
        ("2026-12-15", "2026-12-15"),
    ],
)
def test_deadlines_that_parse_with_a_published_year(text: str, iso: str) -> None:
    result = normalize_deadline(text)
    assert result["status"] == OK, result
    assert result["value"] == iso
    assert result["year_source"] == "published"


def test_deadline_without_a_year_uses_the_students_intake() -> None:
    """REAL: '15 January (23:59 CEST)' — the time is noise, the year absent."""
    result = normalize_deadline("15 January (23:59 CEST)", intake_year=2027)
    assert result["status"] == OK
    assert result["value"] == "2027-01-15"
    assert result["year_source"] == "student_intake_year"
    assert "did not publish a year" in result["year_caveat"]


def test_deadline_without_a_year_or_an_intake_is_ambiguous() -> None:
    """Never assumed into a cycle — being a year out is a real harm."""
    result = normalize_deadline("15 January (23:59 CEST)")
    assert result["status"] == AMBIGUOUS
    assert "intake_unknown" in result["reason"]
    assert result["value"] is None


@pytest.mark.parametrize("text", ["15/12/2026", "15.12.2026", "12-15-2026"])
def test_numeric_dates_are_refused_as_ambiguous(text: str) -> None:
    result = normalize_deadline(text, intake_year=2027)
    assert result["status"] == AMBIGUOUS
    assert "ambiguous_numeric_date" in result["reason"]


def test_rolling_admission_is_not_a_date() -> None:
    result = normalize_deadline("Rolling admissions", intake_year=2027)
    assert result["status"] == UNSUPPORTED
    assert "rolling_admission" in result["reason"]


def test_malformed_deadline_is_refused() -> None:
    result = normalize_deadline("sometime in the spring", intake_year=2027)
    assert result["status"] == UNSUPPORTED
    assert result["value"] is None


def test_unsupported_deadline_format_with_a_year_is_named() -> None:
    result = normalize_deadline("Round 1 closes in late 2026", intake_year=2027)
    assert result["status"] == UNSUPPORTED
    assert "unrecognised_date_format" in result["reason"]


def test_missing_deadline() -> None:
    assert normalize_deadline("", intake_year=2027)["status"] == MISSING


# --- Boolean ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("Yes", True),
        ("Yes, STEM designated", True),
        ("STEM-designated", True),
        ("Eligible for OPT", True),
        ("No", False),
        ("Not STEM designated", False),
        ("This program is not designated as STEM", False),
        ("non-STEM", False),
    ],
)
def test_booleans_that_parse(text: str, value: bool) -> None:
    result = normalize_boolean(text)
    assert result["status"] == OK, result
    assert result["value"] is value


def test_negation_is_read_before_affirmation() -> None:
    """'not STEM designated' contains 'STEM designated'."""
    assert normalize_boolean("Not STEM designated")["value"] is False


def test_an_unrelated_negation_does_not_flip_the_answer() -> None:
    """A blanket 'no' check would read this as a denial."""
    assert normalize_boolean("Yes - no separate application is needed")["value"] is True


def test_unstated_designation_is_not_a_denial() -> None:
    result = normalize_boolean("STEM designation not published")
    assert result["status"] == UNSUPPORTED
    assert "not the same as saying it is absent" in result["reason"]


def test_missing_boolean() -> None:
    assert normalize_boolean("")["status"] == MISSING


# --- Test requirements -----------------------------------------------------


def test_gre_optional_is_recognised() -> None:
    """REAL gatech.edu: 'If provided, GRE scores will be considered.'"""
    result = normalize_test_requirement("If provided, GRE scores will be considered.")
    assert result["status"] == OK
    assert result["level"] == "optional"
    assert result["value"] == 1.0


def test_gre_not_required_scores_the_lowest_burden() -> None:
    result = normalize_test_requirement("The GRE is not required for this program.")
    assert result["level"] == "not_required"
    assert result["value"] == 0.0


def test_gre_required_scores_the_highest_burden() -> None:
    result = normalize_test_requirement("GRE General Test is required.")
    assert result["level"] == "required"
    assert result["value"] == 2.0


def test_an_english_test_requirement_is_not_read_as_a_gre_rule() -> None:
    """REAL gatech.edu — this is IELTS and says nothing about the GRE."""
    result = normalize_test_requirement(
        "A minimum overall score of 7.5 is required, with minimum section "
        "scores as follows: Reading 6.5, Listening 6.5, Speaking 6.5, Writing 5.5."
    )
    assert result["status"] == UNSUPPORTED
    assert "no_gre_or_gmat_statement" in result["reason"]


def test_gre_mentioned_without_a_clear_rule_is_refused() -> None:
    result = normalize_test_requirement("See the GRE section of the admissions page.")
    assert result["status"] == UNSUPPORTED


def test_missing_test_requirement() -> None:
    assert normalize_test_requirement("")["status"] == MISSING


# --- Publisher string and provenance preservation --------------------------

PUBLISHER_STRINGS = [
    (normalize_duration, "24 Months"),
    (normalize_duration, "4 semesters"),
    (normalize_duration, "1.5 - 2 years"),
    (normalize_deadline, "15 December 2026"),
    (normalize_deadline, "Rolling admissions"),
    (normalize_boolean, "Yes, STEM designated"),
    (normalize_test_requirement, "If provided, GRE scores will be considered."),
]


@pytest.mark.parametrize(("fn", "text"), PUBLISHER_STRINGS)
def test_the_publisher_string_survives_success_and_failure(fn, text: str) -> None:
    """Normalization must never be where a source's own words are lost."""
    assert fn(text)["published_value"] == text


def test_money_preserves_the_publisher_string_on_refusal() -> None:
    result = normalize_money("EUR 17.310 and 22.290", "EUR", "per year")
    assert result["status"] == AMBIGUOUS
    assert result["published_value"] == "EUR 17.310 and 22.290"


RENDERED_FIELD = {
    "value": "24 Months",
    "tier": "VERIFIED",
    "source_domain": "tudelft.nl",
    "source_is_official": True,
    "source_url": "https://r/0",
    "url_is_grounding_redirect": True,
    "retrieved_at": "2026-07-30T10:00:00+00:00",
    "staleness_class": "CYCLICAL",
    "is_stale": False,
    "staleness_notice": None,
    "supporting_quote": "The programme takes 24 Months.",
    "source_count": 2,
    "all_source_domains": ["mastersportal.com", "tudelft.nl"],
    "conflicts": [{"value": "18 months"}],
    "corroborations": [{"value": "24 Months"}],
}


def test_provenance_is_lifted_whole() -> None:
    prov = extract_provenance(RENDERED_FIELD)
    assert prov is not None
    assert prov["tier"] == "VERIFIED"
    assert prov["source_domain"] == "tudelft.nl"
    assert prov["source_is_official"] is True
    assert prov["retrieved_at"] == "2026-07-30T10:00:00+00:00"
    assert prov["staleness_class"] == "CYCLICAL"
    assert prov["is_stale"] is False
    assert prov["supporting_quote"] == "The programme takes 24 Months."
    assert prov["source_count"] == 2
    assert prov["has_conflict"] is True
    assert prov["conflicting_values"] == ["18 months"]
    assert prov["corroboration_count"] == 1


def test_provenance_travels_through_normalization() -> None:
    result = normalize_duration(
        "24 Months", provenance=extract_provenance(RENDERED_FIELD)
    )
    assert result["status"] == OK
    assert result["provenance"]["source_domain"] == "tudelft.nl"
    assert result["provenance"]["retrieved_at"] == "2026-07-30T10:00:00+00:00"


def test_provenance_survives_a_refusal_too() -> None:
    """A value that could not be normalized still has a source worth citing."""
    result = normalize_duration(
        "4 semesters", provenance=extract_provenance(RENDERED_FIELD)
    )
    assert result["status"] == UNSUPPORTED
    assert result["provenance"]["source_domain"] == "tudelft.nl"


def test_a_normalized_value_is_labelled_an_inference() -> None:
    assert normalize_duration("24 Months")["tier"] == "INFERENCE"
    assert normalize_duration("24 Months")["rule_id"] == "norm:duration:v1"


def test_a_refusal_asserts_nothing() -> None:
    assert normalize_duration("4 semesters")["tier"] == "UNKNOWN"


# --- Whole-program normalization -------------------------------------------


def rendered_program(**fields) -> dict:
    return {
        "program_id": "p",
        "university": "TU Delft",
        "program": "MSc DSAIT",
        "fields": {
            name: {"value": value, "tier": "VERIFIED", "source_domain": "tudelft.nl"}
            for name, value in fields.items()
        },
        "unknown_fields": [],
        "stale_fields": [],
    }


def test_normalize_program_uses_duration_to_annualize_a_program_fee() -> None:
    normalized = normalize_program(
        rendered_program(
            duration="2 years",
            tuition_amount="40000",
            tuition_currency="EUR",
            tuition_basis="whole programme",
        )
    )
    cost = normalized["dimensions"]["cost"]
    assert cost["status"] == OK
    assert cost["annual_amount"] == 20000.0


def test_normalize_program_reports_every_registry_dimension() -> None:
    normalized = normalize_program(rendered_program())
    assert set(normalized["dimensions"]) == {"cost", "duration", "stem", "test_burden"}
    for entry in normalized["dimensions"].values():
        assert entry["status"] == MISSING
        assert entry["value"] is None


def test_deadline_is_normalized_but_kept_out_of_the_dimensions() -> None:
    normalized = normalize_program(
        rendered_program(application_deadline="15 December 2026")
    )
    assert "application_deadline" not in normalized["dimensions"]
    assert normalized["display_only"]["application_deadline"]["value"] == "2026-12-15"


def test_normalize_program_carries_the_academic_year_through() -> None:
    """REAL '2025/2026' — kept so two fees from different years are visible."""
    normalized = normalize_program(rendered_program(tuition_academic_year="2025/2026"))
    assert normalized["tuition_academic_year"] == "2025/2026"
