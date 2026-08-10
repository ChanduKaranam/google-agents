"""Phase 3 — financial calculations: cost, budget, currency, loan, ROI.

Trust rules pinned here: every line item is typed by provenance
(researched / user_provided / estimate); a currency conversion without a
sourced rate is refused; EMI follows the standard formula with a zero-
interest branch; ROI is labeled an assumption-bound estimate; missing
never becomes zero; and nothing anywhere is an admission probability.
"""

from __future__ import annotations

import pytest

from app.calc.finance import (
    budget_fit,
    convert_currency,
    loan_emi,
    simple_payback,
    total_cost,
)

# --- Total cost (§13-14) -----------------------------------------------------


def line(label: str, amount: float, provenance: str = "user_provided") -> dict:
    return {"label": label, "amount": amount, "provenance": provenance}


def test_annual_and_multi_year_cost() -> None:
    result = total_cost(
        [line("tuition", 35000, "researched"), line("living", 18000, "estimate")],
        years=2,
        currency="CAD",
    )
    assert result["annual_total"] == 53000
    assert result["result"] == 106000
    assert result["unit"] == "CAD"
    assert any("billing" in a.casefold() for a in result["assumptions"])


def test_line_items_keep_their_provenance() -> None:
    result = total_cost([line("tuition", 35000, "researched")], 1, "CAD")
    assert result["inputs"]["items"][0]["provenance"] == "researched"


def test_unknown_provenance_is_refused() -> None:
    result = total_cost([line("tuition", 35000, "vibes")], 1, "CAD")
    assert result["status"] == "invalid"


def test_negative_amounts_are_refused() -> None:
    assert total_cost([line("tuition", -5)], 1, "CAD")["status"] == "invalid"
    assert total_cost([line("t", 1)], 0, "CAD")["status"] == "invalid"


# --- Budget fit (§16) --------------------------------------------------------


def test_surplus_and_deficit_are_signed_and_labeled() -> None:
    surplus = budget_fit(4500000, 3800000, "INR")
    assert surplus["verdict"] == "within_budget"
    assert surplus["result"] == 700000
    deficit = budget_fit(3000000, 4200000, "INR")
    assert deficit["verdict"] == "shortfall"
    assert deficit["result"] == 1200000
    assert "admission" not in str(deficit).casefold()


# --- Currency (§15) ----------------------------------------------------------


def test_conversion_requires_a_sourced_rate() -> None:
    result = convert_currency(4000000, "INR", "USD", rate=None, rate_source="")
    assert result["status"] == "invalid"
    assert "rate" in result["message"].casefold()


def test_conversion_preserves_rate_source_and_timestamp() -> None:
    result = convert_currency(
        4000000,
        "INR",
        "USD",
        rate=0.0120,
        rate_source="user-provided rate, 2026-08-10",
    )
    assert result["result"] == 48000.0
    assert result["inputs"]["rate"] == 0.0120
    assert result["inputs"]["rate_source"]
    assert result["status"] == "estimate"
    assert any("rate" in w.casefold() for w in result["warnings"])


# --- Loan EMI (§17) ----------------------------------------------------------


def test_the_standard_emi_formula() -> None:
    result = loan_emi(principal=3000000, annual_rate_percent=9.0, years=7)
    assert result["status"] == "exact"
    assert result["result"] == 48267.23  # P·r·(1+r)^n / ((1+r)^n − 1)
    # Totals come from FULL-precision EMI (§23), not the rounded display
    # value — rounding first would drift by paise across 84 payments.
    assert result["total_repayment"] == 4054447.72
    assert result["total_interest"] == 1054447.72


def test_zero_interest_divides_evenly() -> None:
    result = loan_emi(1200000, 0.0, 10)
    assert result["result"] == 10000.0
    assert result["total_interest"] == 0.0


def test_invalid_loan_inputs_are_refused() -> None:
    assert loan_emi(-1, 9, 7)["status"] == "invalid"
    assert loan_emi(100, -2, 7)["status"] == "invalid"
    assert loan_emi(100, 9, 0)["status"] == "invalid"


# --- ROI (§19) ---------------------------------------------------------------


def test_simple_payback_is_assumption_bound() -> None:
    result = simple_payback(total_cost_amount=70000, annual_income_gain=25000)
    assert result["result"] == 2.8
    assert result["unit"] == "years"
    assert result["status"] == "estimate"
    assert result["assumptions"]  # must name what it assumed
    rendered = str(result).casefold()
    assert "will recover" not in rendered
    assert "guarantee" not in rendered


def test_payback_without_income_is_unknown_not_zero() -> None:
    result = simple_payback(70000, None)
    assert result["status"] == "invalid"
    assert "income" in result["message"].casefold()


def test_nonpositive_income_is_refused() -> None:
    assert simple_payback(70000, 0)["status"] == "invalid"
    assert simple_payback(70000, -5)["status"] == "invalid"


# --- Safety (§21, §25) -------------------------------------------------------


@pytest.mark.parametrize(
    "result_factory",
    [
        lambda: total_cost([line("t", 100, "estimate")], 1, "CAD"),
        lambda: budget_fit(100, 50, "CAD"),
        lambda: loan_emi(100, 5, 1),
        lambda: simple_payback(100, 50),
    ],
)
def test_no_calculation_speaks_of_admission_probability(result_factory) -> None:
    rendered = str(result_factory()).casefold()
    assert "admission" not in rendered
    assert "probability" not in rendered
    assert "chance" not in rendered
