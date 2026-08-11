"""Finance analysis — money extraction, freshness, and the cost model.

Deterministic interpretation over stored financial evidence. The rules
that keep it honest:

* Only what the text literally states is extracted — an unstated currency
  stays None (a bare "$" names no country), an unstated amount stays None.
* Ranges survive (§22): low and high are carried separately and no
  midpoint is ever minted.
* The cost model prepares typed inputs for app.calc — the only place that
  may divide a one-time fee across a known duration or annualize a
  monthly figure (×12 is calendar arithmetic, stated as the basis). A
  per-term figure is never annualized: the term count is program evidence
  this code does not have, so it is excluded and named (§12).
"""

from __future__ import annotations

import re
from typing import Any

from app.models.finance import FinanceRecord
from app.models.program import Program, ProgramFact

_CODES = r"CAD|USD|EUR|GBP|INR|AUD"
_SYMBOLS = {"₹": "INR", "€": "EUR", "£": "GBP"}  # a bare "$" is ambiguous by design
_ABBREVIATIONS = {"C$": "CAD", "CA$": "CAD", "US$": "USD", "A$": "AUD"}
_NUM = r"[\d,]+(?:\.\d+)?"
# Sources write the currency on either side ("CAD 44,000" and "44,000 CAD"
# both occur on real fee pages — the second was a live finding).
_MARKER = rf"(?:({_CODES})\b|(CA\$|C\$|US\$|A\$)|[$€£₹])"

_RANGE_BEFORE = re.compile(
    rf"{_MARKER}\s*({_NUM})\s*[–—-]\s*({_NUM})", re.IGNORECASE
)
_RANGE_AFTER = re.compile(
    rf"({_NUM})\s*[–—-]\s*({_NUM})\s*(?:({_CODES})\b|(CA\$|C\$|US\$|A\$))",
    re.IGNORECASE,
)
_SINGLE_BEFORE = re.compile(rf"{_MARKER}\s*({_NUM})", re.IGNORECASE)
_SINGLE_AFTER = re.compile(
    rf"({_NUM})\s*(?:({_CODES})\b|(CA\$|C\$|US\$|A\$))", re.IGNORECASE
)
_INDIAN = re.compile(rf"({_NUM})\s*(lakh|lakhs|lac|crore|crores)", re.IGNORECASE)
_CODE_ANYWHERE = re.compile(rf"\b({_CODES})\b", re.IGNORECASE)
_PERIOD = re.compile(
    r"\bper\s+(term|semester|year|annum|month|week|hour)\b"
    r"|\b(annual|annually|yearly|monthly|weekly|hourly)\b",
    re.IGNORECASE,
)
_YEAR = re.compile(r"\b(20\d{2})\b")

_PERIOD_MAP = {
    "annum": "year",
    "annual": "year",
    "annually": "year",
    "yearly": "year",
    "semester": "term",
    "monthly": "month",
    "weekly": "week",
    "hourly": "hour",
}


def _to_number(raw: str) -> float:
    return float(raw.replace(",", ""))


def _is_year(raw: str) -> bool:
    return bool(re.fullmatch(r"20\d{2}", raw.replace(",", "")))


def _currency_of(
    text: str, code_group: str | None, abbreviation: str | None = None
) -> str | None:
    if code_group:
        return code_group.upper()
    if abbreviation:
        return _ABBREVIATIONS.get(abbreviation.upper())
    for symbol, code in _SYMBOLS.items():
        if symbol in text:
            return code
    match = _CODE_ANYWHERE.search(text)
    return match.group(1).upper() if match else None


def extract_money(text: str) -> dict[str, Any]:
    """Currency, amount(s), period and year — only what the text states."""
    raw = str(text or "")
    result: dict[str, Any] = {
        "currency": None,
        "amount": None,
        "low": None,
        "high": None,
        "period": None,
        "year": None,
        "is_range": False,
    }

    period = _PERIOD.search(raw)
    if period:
        token = (period.group(1) or period.group(2) or "").casefold()
        result["period"] = _PERIOD_MAP.get(token, token)
    years = [int(y) for y in _YEAR.findall(raw)]
    if years:
        result["year"] = max(years)

    indian = _INDIAN.search(raw)
    if indian:
        multiplier = (
            10_000_000 if indian.group(2).casefold().startswith("crore") else 100_000
        )
        amount = _to_number(indian.group(1)) * multiplier
        result.update(
            amount=amount, low=amount, high=amount, currency=_currency_of(raw, None)
        )
        return result

    for ranged in _RANGE_BEFORE.finditer(raw):
        code, abbreviation, raw_low, raw_high = ranged.groups()
        low, high = _to_number(raw_low), _to_number(raw_high)
        if low > high:
            low, high = high, low
        result.update(
            is_range=True,
            low=low,
            high=high,
            currency=_currency_of(raw, code, abbreviation),
        )
        return result
    for ranged in _RANGE_AFTER.finditer(raw):
        raw_low, raw_high, code, abbreviation = ranged.groups()
        if _is_year(raw_low) and _is_year(raw_high):
            continue  # "2025–2026 CAD ..." is a cycle, not a price
        low, high = _to_number(raw_low), _to_number(raw_high)
        if low > high:
            low, high = high, low
        result.update(
            is_range=True,
            low=low,
            high=high,
            currency=_currency_of(raw, code, abbreviation),
        )
        return result

    single = _SINGLE_BEFORE.search(raw)
    if single:
        amount = _to_number(single.group(3))
        result.update(
            amount=amount,
            low=amount,
            high=amount,
            currency=_currency_of(raw, single.group(1), single.group(2)),
        )
        return result
    for single in _SINGLE_AFTER.finditer(raw):
        raw_amount, code, abbreviation = single.groups()
        if _is_year(raw_amount):
            continue  # "for 2025 CAD figures" states a year, not a price
        amount = _to_number(raw_amount)
        result.update(
            amount=amount,
            low=amount,
            high=amount,
            currency=_currency_of(raw, code, abbreviation),
        )
        return result
    return result


def assess_money_freshness(text: str, target_intake: str) -> dict[str, Any]:
    """Is this financial figure plausibly for the student's cycle? (§13)"""
    stated = [int(y) for y in _YEAR.findall(str(text or ""))]
    target = [int(y) for y in _YEAR.findall(str(target_intake or ""))]
    if not stated:
        return {
            "status": "year_unclear",
            "note": (
                "The source states no year for this figure — say which "
                "year the latest verified information is from, never "
                "present it as current."
            ),
        }
    if not target:
        return {
            "status": "year_unclear",
            "note": "No target intake on the profile to compare against.",
        }
    latest, wanted = max(stated), max(target)
    if latest >= wanted - 1:
        return {
            "status": "appears_current",
            "note": f"Stated for {latest}, target intake {wanted}.",
        }
    return {
        "status": "stale",
        "note": (
            f"The latest stated year is {latest}, but the target intake is "
            f"{wanted} — relay it as {latest} information, never as current."
        ),
    }


# component → (program field, finance category, one_time). Program facts
# outrank place-scoped facts for the same component; a city fact outranks
# a country fact.
_COMPONENTS: tuple[tuple[str, str | None, str | None, bool], ...] = (
    ("tuition", "tuition", None, False),
    ("mandatory_fees", "mandatory_fees", None, False),
    ("housing", "housing_cost", "housing", False),
    ("living_cost", "living_cost_estimate", "living_cost", False),
    ("food", None, "food", False),
    ("transport", None, "transport", False),
    ("utilities", None, "utilities", False),
    ("health_insurance", "health_insurance_cost", "health_insurance", False),
    ("application_fee", "application_fee", None, True),
    ("deposit", "deposit", None, True),
    ("travel", None, "travel_cost", True),
)

_DURATION_YEARS = re.compile(r"(\d+(?:\.\d+)?)\s*(year|month)", re.IGNORECASE)


def _parse_years(duration_text: str) -> float | None:
    match = _DURATION_YEARS.search(str(duration_text or ""))
    if not match:
        return None
    value = float(match.group(1))
    return value / 12 if match.group(2).casefold() == "month" else value


def _fact_for(
    component: tuple[str, str | None, str | None, bool],
    program: Program,
    records: list[FinanceRecord],
) -> tuple[ProgramFact, str] | None:
    """The best-scoped stored fact for this component, with its scope label."""
    _, program_field, finance_field, _ = component
    if program_field and program_field in program.facts:
        return program.facts[program_field], "program"
    if finance_field:
        for level, place in (("city", program.city), ("country", program.country)):
            if not place:
                continue
            for record in records:
                if (
                    record.scope_level == level
                    and record.scope_name.strip().casefold() == place.strip().casefold()
                    and finance_field in record.facts
                ):
                    return record.facts[finance_field], f"{level}: {record.scope_name}"
    return None


def build_cost_model(
    program: Program,
    finance_records: list[FinanceRecord],
    target_intake: str,
) -> dict[str, Any]:
    """Assemble the researched cost picture and prepare calc inputs (§21).

    Every component carries provenance, scope and freshness; unknowns are
    named; totals are NOT computed here — `calculation_inputs` feed
    app.calc's total_cost/budget_fit, which own all arithmetic.
    """
    components: list[dict[str, Any]] = []
    unknown: list[str] = []
    items_low: list[dict[str, Any]] = []
    items_high: list[dict[str, Any]] = []
    excluded: list[dict[str, str]] = []
    assumptions: list[str] = []

    duration_fact = program.facts.get("duration")
    years = _parse_years(duration_fact.value) if duration_fact else None
    years_basis = (
        f"duration fact: {duration_fact.value} ({duration_fact.evidence.source_domain})"
        if duration_fact and years
        else "no evidenced duration"
    )

    resolved: list[tuple[str, ProgramFact, str, bool, dict[str, Any]]] = []
    for component in _COMPONENTS:
        name = component[0]
        found = _fact_for(component, program, finance_records)
        if found is None:
            unknown.append(name)
            continue
        fact, scope = found
        money = extract_money(fact.value)
        resolved.append((name, fact, scope, component[3], money))
        cell: dict[str, Any] = {
            "component": name,
            "value": fact.value,
            "status": fact.status,
            "scope": scope,
            "source_domain": fact.evidence.source_domain,
            "source_type": fact.evidence.source_type,
            "url": fact.evidence.url,
            "retrieved_at": fact.evidence.retrieved_at,
            "money": money,
            "freshness": assess_money_freshness(fact.value, target_intake),
        }
        if fact.conflicts:
            cell["conflicts"] = fact.conflicts
        components.append(cell)

    currency = next(
        (m["currency"] for name, _, _, _, m in resolved if name == "tuition"),
        None,
    ) or next((m["currency"] for *_, m in resolved if m["currency"]), None)

    for name, fact, _scope, one_time, money in resolved:
        provenance = (
            "researched"
            if fact.status in ("verified", "partially_verified")
            else "estimate"
        )
        if money["low"] is None:
            excluded.append({"label": name, "reason": "no amount stated to compute with"})
            continue
        if money["currency"] is None:
            excluded.append(
                {"label": name, "reason": "currency unstated — verify before using"}
            )
            continue
        if currency and money["currency"] != currency:
            excluded.append(
                {
                    "label": name,
                    "reason": (
                        f"stated in {money['currency']}, model currency is "
                        f"{currency} — convert first with a sourced rate "
                        "(convert_money)"
                    ),
                }
            )
            continue
        low, high = money["low"], money["high"]
        basis = fact.value
        if one_time:
            if not years:
                excluded.append(
                    {
                        "label": name,
                        "reason": (
                            "a one-time cost, and the program duration is "
                            "not evidenced — cannot spread it across years"
                        ),
                    }
                )
                continue
            low, high = low / years, high / years
            basis = f"one-time {fact.value} spread across {years} years"
        elif money["period"] == "month":
            low, high = low * 12, high * 12
            basis = f"{fact.value} × 12 months"
        elif money["period"] in ("term", "week", "hour"):
            excluded.append(
                {
                    "label": name,
                    "reason": (
                        f"stated per {money['period']} — the {money['period']} "
                        "count per year is not evidenced; research the "
                        "billing structure before annualizing"
                    ),
                }
            )
            continue
        elif money["period"] is None:
            assumptions.append(
                f"'{name}' states no period; treated as annual — verify."
            )
        items_low.append(
            {"label": name, "amount": low, "provenance": provenance, "basis": basis}
        )
        items_high.append(
            {"label": name, "amount": high, "provenance": provenance, "basis": basis}
        )

    if any(m["is_range"] for *_, m in resolved):
        assumptions.append(
            "Ranged evidence kept as low/high scenarios — never averaged."
        )

    return {
        "university": program.university,
        "program": program.name,
        "components": components,
        "unknown_components": unknown,
        "calculation_inputs": {
            "currency": currency,
            "years": years,
            "years_basis": years_basis,
            "items_low": items_low,
            "items_high": items_high,
            "excluded": excluded,
            "assumptions": assumptions,
        },
        "note": (
            "Evidence assembly only — totals come from calculate_total_cost "
            "and affordability from calculate_budget_fit, never from here "
            "and never from the model's head. Unknown components stay "
            "unknown."
        ),
    }
