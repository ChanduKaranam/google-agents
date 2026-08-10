"""Financial calculations — typed inputs, visible formulas, labeled outputs.

Rules enforced here rather than hoped for:

* Every cost line item is typed by provenance — researched, user_provided,
  or estimate — and an unknown type is refused (§13).
* A currency conversion without an explicit, sourced rate is refused; the
  rate and its source travel with the result (§15).
* EMI is the standard formula with a zero-interest branch (§17).
* Payback is a simple, assumption-bound estimate that structurally cannot
  promise recovery (§19).
* Missing is never zero; invalid is refused, never repaired (§24-25).
"""

from __future__ import annotations

from typing import Any

PROVENANCES = ("researched", "user_provided", "estimate")


def total_cost(
    items: list[dict[str, Any]], years: float, currency: str
) -> dict[str, Any]:
    """Annual line items × program duration, provenance preserved."""
    if years <= 0:
        return {
            "calculation_type": "total_cost",
            "status": "invalid",
            "message": "Program duration must be positive.",
        }
    cleaned = []
    for item in items:
        label = str(item.get("label", "")).strip()
        provenance = str(item.get("provenance", "")).strip()
        try:
            amount = float(item.get("amount"))
        except (TypeError, ValueError):
            return {
                "calculation_type": "total_cost",
                "status": "invalid",
                "message": f"'{label}' has a non-numeric amount.",
            }
        if amount < 0:
            return {
                "calculation_type": "total_cost",
                "status": "invalid",
                "message": f"'{label}' has a negative amount.",
            }
        if provenance not in PROVENANCES:
            return {
                "calculation_type": "total_cost",
                "status": "invalid",
                "message": (
                    f"'{label}' has provenance '{provenance}'; every amount "
                    f"must be one of {PROVENANCES}."
                ),
            }
        cleaned.append({"label": label, "amount": amount, "provenance": provenance})
    if not cleaned:
        return {
            "calculation_type": "total_cost",
            "status": "invalid",
            "message": "At least one cost line item is required.",
        }
    annual = sum(item["amount"] for item in cleaned)
    has_estimate = any(i["provenance"] != "researched" for i in cleaned)
    return {
        "calculation_type": "total_cost",
        "status": "estimate" if has_estimate else "exact",
        "inputs": {"items": cleaned, "years": years, "currency": currency},
        "method": "sum(annual items) × years",
        "annual_total": round(annual, 2),
        "result": round(annual * years, 2),
        "unit": currency,
        "assumptions": [
            "Assumes annual billing multiplied by duration; verify the "
            "program's actual billing structure (per-term or per-credit "
            "billing changes this).",
            "Amounts are mixed provenance — see each item's type."
            if has_estimate
            else "All amounts researched.",
        ],
        "warnings": [],
    }


def budget_fit(
    budget: float, total_cost_amount: float, currency: str
) -> dict[str, Any]:
    """Budget minus estimated total — financial fit, nothing more."""
    if budget < 0 or total_cost_amount < 0:
        return {
            "calculation_type": "budget_fit",
            "status": "invalid",
            "message": "Budget and cost must be non-negative.",
        }
    difference = budget - total_cost_amount
    return {
        "calculation_type": "budget_fit",
        "status": "estimate",
        "inputs": {
            "budget": budget,
            "total_cost": total_cost_amount,
            "currency": currency,
        },
        "method": "budget − estimated total cost",
        "verdict": "within_budget" if difference >= 0 else "shortfall",
        "result": round(abs(difference), 2),
        "unit": currency,
        "warnings": [
            "A financial-fit figure only; it says nothing about anything except money."
        ],
    }


def convert_currency(
    amount: float,
    from_currency: str,
    to_currency: str,
    rate: float | None,
    rate_source: str,
) -> dict[str, Any]:
    """Convert with an explicit, sourced rate — never a silent one."""
    if rate is None or rate <= 0 or not str(rate_source).strip():
        return {
            "calculation_type": "currency_conversion",
            "status": "invalid",
            "message": (
                "A positive exchange rate with its source and date is "
                "required — no built-in rate exists here, and none is "
                "assumed."
            ),
        }
    if amount < 0:
        return {
            "calculation_type": "currency_conversion",
            "status": "invalid",
            "message": "Amount must be non-negative.",
        }
    return {
        "calculation_type": "currency_conversion",
        "status": "estimate",
        "inputs": {
            "amount": amount,
            "from_currency": from_currency,
            "to_currency": to_currency,
            "rate": rate,
            "rate_source": rate_source,
        },
        "method": "amount × rate",
        "result": round(amount * rate, 2),
        "unit": to_currency,
        "warnings": [
            "Exchange rates move; this is approximate as of the rate's stated date."
        ],
    }


def loan_emi(
    principal: float, annual_rate_percent: float, years: float
) -> dict[str, Any]:
    """Standard EMI: P·r·(1+r)^n / ((1+r)^n − 1), zero-interest branch."""
    if principal <= 0 or annual_rate_percent < 0 or years <= 0:
        return {
            "calculation_type": "loan_emi",
            "status": "invalid",
            "message": (
                "Principal and duration must be positive; the interest "
                "rate cannot be negative."
            ),
        }
    n = round(years * 12)
    if annual_rate_percent == 0:
        emi = principal / n
        method = "zero interest: principal / number of payments"
    else:
        r = annual_rate_percent / 100 / 12
        growth = (1 + r) ** n
        emi = principal * r * growth / (growth - 1)
        method = "EMI = P·r·(1+r)^n / ((1+r)^n − 1), monthly compounding"
    total = emi * n
    return {
        "calculation_type": "loan_emi",
        "status": "exact",
        "inputs": {
            "principal": principal,
            "annual_rate_percent": annual_rate_percent,
            "years": years,
            "payments": n,
        },
        "method": method,
        "result": round(emi, 2),
        "unit": "per month, in the principal's currency",
        "total_repayment": round(total, 2),
        "total_interest": round(total - principal, 2),
        "warnings": [
            "Assumes a fixed rate and monthly compounding; lender terms vary."
        ],
    }


def simple_payback(
    total_cost_amount: float, annual_income_gain: float | None
) -> dict[str, Any]:
    """Cost ÷ annual income gain — an assumption-bound planning estimate."""
    if annual_income_gain is None:
        return {
            "calculation_type": "simple_payback",
            "status": "invalid",
            "message": (
                "An expected annual income gain is required — supplied by "
                "the student or by researched career evidence, never "
                "assumed here."
            ),
        }
    if total_cost_amount <= 0 or annual_income_gain <= 0:
        return {
            "calculation_type": "simple_payback",
            "status": "invalid",
            "message": "Cost and income gain must both be positive.",
        }
    return {
        "calculation_type": "simple_payback",
        "status": "estimate",
        "inputs": {
            "total_cost": total_cost_amount,
            "annual_income_gain": annual_income_gain,
        },
        "method": "total cost / annual income gain",
        "result": round(total_cost_amount / annual_income_gain, 2),
        "unit": "years",
        "assumptions": [
            "Assumes the stated income gain materializes and stays constant.",
            "Ignores taxes, living-cost differences, currency moves and "
            "career variance.",
            "Under these assumptions only — a planning estimate.",
        ],
        "warnings": [],
    }
