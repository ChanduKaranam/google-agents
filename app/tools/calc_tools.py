"""Calculation tools — thin, validated wrappers over app.calc services.

Small tools over one calculate_everything (§29). Each returns the full
CalculationResult shape — inputs, method, result, warnings — so the root
can explain the arithmetic it did not perform.
"""

from __future__ import annotations

from google.adk.tools import ToolContext

from app.calc.academic import convert_academic_score
from app.calc.finance import (
    budget_fit,
    convert_currency,
    loan_emi,
    simple_payback,
    total_cost,
)
from app.exams.conversions import compare_english_scores
from app.tools.profile_tools import _read_profile


def convert_score(
    value: float,
    from_scale: str,
    to_scale: str,
    methodology: str,
    tool_context: ToolContext,
) -> dict:
    """Convert an academic score between explicit grading scales.

    Args:
        value: The score, e.g. `8.2`.
        from_scale: Its scale maximum, e.g. `10`, `4`, `100`.
        to_scale: The target scale maximum.
        methodology: A researched institutional methodology sentence if one
            exists (e.g. "multiply CGPA by 9.5"); empty for none. Without
            one the result is a clearly-labeled linear estimate — present
            it as such, never as an official equivalence.

    Returns:
        The conversion with method, status and warnings.
    """
    return convert_academic_score(value, from_scale, to_scale, methodology)


def compare_english_tests(
    from_exam: str, score: float, to_exam: str, tool_context: ToolContext
) -> dict:
    """Compare an English test score across tests via the linking table.

    Args:
        from_exam: e.g. `ielts`.
        score: The score on that test.
        to_exam: e.g. `toefl`.

    Returns:
        A commonly-used-comparison range with its caveats — never an
        official equivalence, and unmapped scores stay unknown.
    """
    return compare_english_scores(from_exam, score, to_exam)


def calculate_total_cost(
    items: list[dict], years: float, currency: str, tool_context: ToolContext
) -> dict:
    """Total program cost from typed annual line items.

    Args:
        items: One dict per cost: `{"label": "tuition", "amount": 35000,
            "provenance": "researched"|"user_provided"|"estimate"}`.
            Researched amounts must come from stored program facts;
            everything else is user_provided or estimate — never untyped.
        years: Program duration in years.
        currency: The currency every amount is in.

    Returns:
        Annual and total figures with assumptions (billing structure).
    """
    return total_cost(items, years, currency)


def calculate_budget_fit(
    total_cost_amount: float, currency: str, tool_context: ToolContext
) -> dict:
    """Compare the student's stored budget against an estimated total cost.

    Args:
        total_cost_amount: The estimated total (from calculate_total_cost).
        currency: The currency of that total.

    Returns:
        Surplus or shortfall — or a refusal when the budget's currency
        differs (convert first, with a sourced rate) or no budget is
        stored.
    """
    profile = _read_profile(tool_context.state)
    budget = profile.preferences.budget
    budget_currency = (profile.preferences.budget_currency or "").strip().upper()
    if budget is None:
        return {
            "status": "invalid",
            "message": "No budget on the profile — ask the student for it.",
        }
    if budget_currency and budget_currency != currency.strip().upper():
        return {
            "status": "invalid",
            "message": (
                f"The budget is in {budget_currency} and the cost in "
                f"{currency}. Convert one first with convert_money and a "
                "sourced rate — never compare across currencies."
            ),
        }
    return budget_fit(budget, total_cost_amount, currency)


def convert_money(
    amount: float,
    from_currency: str,
    to_currency: str,
    rate: float,
    rate_source: str,
    tool_context: ToolContext,
) -> dict:
    """Convert an amount between currencies with an explicit, sourced rate.

    Args:
        amount: The amount to convert.
        from_currency: e.g. `INR`.
        to_currency: e.g. `USD`.
        rate: The exchange rate (target per source unit). There is no
            built-in rate: it must come from the student or research, with
            its source.
        rate_source: Where the rate came from, with its date.

    Returns:
        The converted amount carrying the rate, source and caveats.
    """
    return convert_currency(amount, from_currency, to_currency, rate, rate_source)


def calculate_loan_emi(
    principal: float,
    annual_rate_percent: float,
    years: float,
    tool_context: ToolContext,
) -> dict:
    """Education-loan EMI, total repayment and total interest.

    Args:
        principal: Loan amount.
        annual_rate_percent: Annual interest rate, e.g. `9` for 9%.
        years: Loan tenure in years.

    Returns:
        Monthly EMI (standard formula, monthly compounding), totals, and
        the assumptions.
    """
    return loan_emi(principal, annual_rate_percent, years)


def calculate_payback(
    total_cost_amount: float,
    annual_income_gain: float,
    tool_context: ToolContext,
) -> dict:
    """Simple payback period under stated assumptions.

    Args:
        total_cost_amount: Total education cost.
        annual_income_gain: Expected annual income gain — from the student
            or researched career evidence, never assumed.

    Returns:
        A years figure that is an assumption-bound planning estimate; the
        assumptions travel with it and must be relayed.
    """
    return simple_payback(total_cost_amount, annual_income_gain)
