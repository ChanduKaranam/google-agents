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

"""Stage ① — deterministic normalization of published program strings.

C2 stores values exactly as a source published them, because the stored
string is the one the supporting quote actually verifies. That is right for
provenance and useless for comparison: `"24 Months"`, `"$15,605."` and
`"15 January (23:59 CEST)"` cannot be ordered. This module is the bridge.

**It refuses rather than guesses.** Every normalizer returns a status, and
only `ok` produces a comparable value. `ambiguous` and `unsupported` are
first-class outcomes that carry a reason and keep the field out of scoring —
which is the whole point, because the alternative is a plausible number the
student cannot check. This is the same posture as `convert_to_us_4pt`
rejecting an out-of-range GPA instead of coercing it.

Three properties hold for every result:

* the **original publisher string is preserved verbatim** in
  `published_value`, so normalization is never a place a source's own words
  are lost;
* the **provenance travels through** — tier, domain, officialness, retrieval
  time, staleness and conflicts all survive into the normalized record;
* normalization is an **`INFERENCE`** carrying a versioned `rule_id`, exactly
  like a GPA conversion. A derived number is never dressed up as a stated one.

Pure Python: no ADK, no model, no network, no state. Every parser here was
written against strings C2 actually retrieved (see `tests/unit/test_normalize.py`)
rather than formats invented because they seemed plausible.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Any

from app.reference.comparison_dimensions import DIMENSIONS

VERSION = "normalize:v1"

# --- Statuses --------------------------------------------------------------
# `ok` is the only comparable outcome. The other three are all "this does not
# enter scoring", distinguished so the student can be told *why*.
OK = "ok"
AMBIGUOUS = "ambiguous"  # recognised, but has more than one honest reading
UNSUPPORTED = "unsupported"  # not a form this version parses
MISSING = "missing"  # no value was ever stored for the field


def _result(
    field: str,
    kind: str,
    status: str,
    rule_id: str,
    *,
    value: Any = None,
    unit: str | None = None,
    published_value: str | None = None,
    reason: str | None = None,
    provenance: dict[str, Any] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """Assemble a normalized record.

    `published_value` is carried on every result including the failures —
    an unparsed string is still the source's own words and is still worth
    showing to the student.
    """
    return {
        "field": field,
        "kind": kind,
        "status": status,
        "value": value,
        "unit": unit,
        "published_value": published_value,
        "reason": reason,
        "rule_id": rule_id,
        # A normalized value is derived, never stated. Only `ok` results are
        # an inference *about* something; the rest assert nothing at all.
        "tier": "INFERENCE" if status == OK else "UNKNOWN",
        "provenance": provenance,
        **extra,
    }


# --- Money -----------------------------------------------------------------

MONEY_RULE = "norm:money:v1"

# Symbols that map to exactly one currency.
SYMBOL_TO_CURRENCY: dict[str, str] = {
    "€": "EUR",
    "£": "GBP",
    "₹": "INR",
    "₩": "KRW",
    "₪": "ILS",
}

# Symbols shared by several currencies. Guessing one of these is exactly the
# kind of silent error a student cannot catch, so they are refused.
AMBIGUOUS_SYMBOLS: dict[str, str] = {
    "$": "USD, CAD, AUD, SGD, NZD and HKD are all written '$'",
    "¥": "JPY and CNY are both written '¥'",
    "kr": "SEK, NOK, DKK and ISK are all written 'kr'",
}

KNOWN_CURRENCY_CODES: frozenset[str] = frozenset(
    {
        "AED", "AUD", "CAD", "CHF", "CNY", "CZK", "DKK", "EUR", "GBP", "HKD",
        "HUF", "ILS", "INR", "JPY", "KRW", "NOK", "NZD", "PLN", "SEK", "SGD",
        "TWD", "USD", "ZAR",
    }
)  # fmt: skip

# Alternative spellings seen in published text.
CURRENCY_WORDS: dict[str, str] = {
    "EURO": "EUR",
    "EUROS": "EUR",
    "SFR": "CHF",
    "SWISS FRANCS": "CHF",
    "POUNDS": "GBP",
    "GBP STERLING": "GBP",
    "RUPEES": "INR",
    "RS": "INR",
    "US DOLLARS": "USD",
    "USD DOLLARS": "USD",
}

BASIS_YEAR = "year"
BASIS_SEMESTER = "semester"
BASIS_TERM = "term"
BASIS_MONTH = "month"
BASIS_PROGRAM = "program"
BASIS_CREDIT = "credit"

# Ordered: the first pattern to match wins, so more specific phrases come
# first ("per academic year" before "year").
BASIS_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"per\s+credit|per\s+ects|per\s+unit|per\s+ec\b", BASIS_CREDIT),
    (r"whole\s+programme|whole\s+program|entire\s+programme|entire\s+program"
     r"|full\s+programme|full\s+program|total\s+tuition|total\s+fee"
     r"|for\s+the\s+degree|complete\s+programme|complete\s+program", BASIS_PROGRAM),
    (r"per\s+academic\s+year|per\s+year|per\s+annum|p\.?a\.?\b|annually"
     r"|annual|yearly|/\s*year|/\s*yr", BASIS_YEAR),
    (r"per\s+semester|semesterly|/\s*semester", BASIS_SEMESTER),
    (r"per\s+term|per\s+quarter|/\s*term", BASIS_TERM),
    (r"per\s+month|monthly|/\s*month", BASIS_MONTH),
)  # fmt: skip

_AMOUNT_TOKEN = re.compile(r"\d[\d.,\s']*\d|\d")
_TRAILING_JUNK = re.compile(r"[.,;:\s]+$")


def parse_amount(text: str) -> dict[str, Any]:
    """Parse a published money figure into a float.

    Separator handling is the whole difficulty. `"$15,605."` and `"€ 17.310"`
    are both real strings C2 retrieved, and they mean 15605 and 17310 — the
    dot in the second is a European thousands separator, not a decimal point.
    The rule:

    * both `.` and `,` present → the **last** one is the decimal separator;
    * one separator appearing more than once → thousands (`1.234.567`);
    * one separator followed by exactly **3** digits → thousands, because no
      institution publishes a fee to three decimal places;
    * one separator followed by 1-2 digits → decimal (`1460.50`);
    * spaces and apostrophes between digits → thousands (`CHF 1'460`).

    Anything else is refused. Two distinct numbers in one string is
    `ambiguous`, not a coin-flip between them.
    """
    raw = (text or "").strip()
    if not raw:
        return {"status": MISSING, "reason": "no_value"}

    tokens = _AMOUNT_TOKEN.findall(raw)
    tokens = [_TRAILING_JUNK.sub("", t).strip() for t in tokens]
    tokens = [t for t in tokens if t]
    if not tokens:
        return {"status": UNSUPPORTED, "reason": "no_number_found"}
    if len(set(tokens)) > 1:
        return {
            "status": AMBIGUOUS,
            "reason": f"multiple_amounts_in_value: {', '.join(tokens)}",
        }

    token = tokens[0]
    # Spaces and apostrophes are only ever thousands separators.
    token = re.sub(r"[\s']", "", token)

    has_dot, has_comma = "." in token, "," in token
    if has_dot and has_comma:
        decimal_sep = "." if token.rfind(".") > token.rfind(",") else ","
        thousands_sep = "," if decimal_sep == "." else "."
        token = token.replace(thousands_sep, "").replace(decimal_sep, ".")
    elif has_dot or has_comma:
        sep = "." if has_dot else ","
        if token.count(sep) > 1:
            token = token.replace(sep, "")
        else:
            after = len(token.split(sep)[1])
            if after == 3:
                token = token.replace(sep, "")
            elif after in (1, 2):
                token = token.replace(sep, ".")
            else:
                return {
                    "status": AMBIGUOUS,
                    "reason": (
                        f"separator_reading_unclear: '{text}' has {after} digits "
                        f"after '{sep}', which is neither a decimal nor a "
                        "thousands group"
                    ),
                }

    try:
        return {"status": OK, "amount": float(token)}
    except ValueError:
        return {"status": UNSUPPORTED, "reason": f"unparseable_number: '{text}'"}


def resolve_currency(currency_text: str, amount_text: str = "") -> dict[str, Any]:
    """Resolve a currency to an ISO-4217 code, or refuse.

    The declared `tuition_currency` wins; the amount string is only a
    fallback. A bare `$` is refused outright — six currencies use it, and a
    US-dollar assumption would quietly misprice every Canadian, Australian
    and Singaporean program.
    """

    def find(text: str) -> dict[str, Any] | None:
        """Look for a currency in `text`; None if there is nothing to see."""
        upper = text.upper()
        if upper in KNOWN_CURRENCY_CODES:
            return {"status": OK, "currency": upper}
        if upper in CURRENCY_WORDS:
            return {"status": OK, "currency": CURRENCY_WORDS[upper]}
        for symbol, code in SYMBOL_TO_CURRENCY.items():
            if symbol in text:
                return {"status": OK, "currency": code}
        # Sorted so that a string somehow matching two codes always resolves
        # the same way. Determinism is a scoring requirement, not a nicety.
        for code in sorted(KNOWN_CURRENCY_CODES):
            if re.search(rf"\b{code}\b", upper):
                return {"status": OK, "currency": code}
        for word, code in sorted(CURRENCY_WORDS.items()):
            if re.search(rf"\b{re.escape(word)}\b", upper):
                return {"status": OK, "currency": code}
        for symbol, why in AMBIGUOUS_SYMBOLS.items():
            if symbol in text.lower():
                return {
                    "status": AMBIGUOUS,
                    "reason": f"ambiguous_currency_symbol: {why}",
                }
        return None

    declared = (currency_text or "").strip()
    if declared:
        # A declared currency that cannot be read is an error worth naming.
        return find(declared) or {
            "status": UNSUPPORTED,
            "reason": f"unrecognised_currency: '{declared}'",
        }

    # The amount string is only ever searched, never used to reject: a bare
    # "15605" simply means the currency was not stated.
    inferred = (amount_text or "").strip()
    if inferred:
        found = find(inferred)
        if found:
            return found

    return {"status": MISSING, "reason": "currency_not_stated"}


def parse_basis(text: str) -> dict[str, Any]:
    """Resolve what a tuition figure covers.

    Never defaulted. A per-year figure read as whole-program understates the
    cost by the length of the program, so an unstated basis makes the fee
    non-comparable rather than assumed.
    """
    lowered = (text or "").strip().lower()
    if not lowered:
        return {"status": MISSING, "reason": "basis_not_stated"}
    for pattern, basis in BASIS_PATTERNS:
        if re.search(pattern, lowered):
            return {"status": OK, "basis": basis}
    return {"status": UNSUPPORTED, "reason": f"unrecognised_basis: '{text}'"}


def normalize_money(
    amount_text: str,
    currency_text: str = "",
    basis_text: str = "",
    duration_months: float | None = None,
    field: str = "tuition_amount",
    provenance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Normalize a published tuition figure.

    All three of amount, currency and basis must resolve. A number without a
    currency is not a price, and a price without a basis is not a cost.

    Annualization is attempted only where it is arithmetic rather than
    assumption. A per-semester fee is deliberately **not** annualized:
    semesters per year vary by institution and country, and multiplying by
    two would be an invented number wearing a plausible face.
    """
    published = (amount_text or "").strip() or None

    parsed = parse_amount(amount_text)
    if parsed["status"] != OK:
        return _result(
            field, "money", parsed["status"], MONEY_RULE,
            published_value=published, reason=parsed["reason"],
            provenance=provenance,
        )  # fmt: skip

    currency = resolve_currency(currency_text, amount_text)
    if currency["status"] != OK:
        return _result(
            field, "money", currency["status"], MONEY_RULE,
            published_value=published, reason=currency["reason"],
            provenance=provenance,
        )  # fmt: skip

    basis = parse_basis(basis_text)
    if basis["status"] != OK:
        return _result(
            field, "money", basis["status"], MONEY_RULE,
            published_value=published, reason=basis["reason"],
            provenance=provenance,
        )  # fmt: skip

    amount, code, kind = parsed["amount"], currency["currency"], basis["basis"]

    annual: float | None = None
    total: float | None = None
    annual_reason: str | None = None
    years = (duration_months / 12.0) if duration_months else None

    if kind == BASIS_YEAR:
        annual = amount
        if years:
            total = round(amount * years, 2)
        else:
            annual_reason = "program_total_needs_a_normalized_duration"
    elif kind == BASIS_MONTH:
        annual = round(amount * 12, 2)
        if duration_months:
            total = round(amount * duration_months, 2)
    elif kind == BASIS_PROGRAM:
        total = amount
        if years:
            annual = round(amount / years, 2)
        else:
            annual_reason = "annualization_needs_a_normalized_duration"
    else:
        annual_reason = (
            f"cannot annualize a per-{kind} fee: the number of {kind}s per "
            "year varies by institution and was not published"
        )

    return _result(
        field, "money", OK, MONEY_RULE,
        value=amount, unit=code, published_value=published,
        provenance=provenance,
        basis=kind,
        annual_amount=annual,
        total_program_amount=total,
        annualization_reason=annual_reason,
    )  # fmt: skip


# --- Duration --------------------------------------------------------------

DURATION_RULE = "norm:duration:v1"

_DURATION_UNITS: tuple[tuple[str, float | None, str | None], ...] = (
    (r"years?|yrs?\b", 12.0, None),
    (r"months?|mos?\b", 1.0, None),
    (
        r"semesters?",
        None,
        "semester length varies by institution and was not published",
    ),
    (r"terms?|quarters?", None, "term length varies by institution"),
    (r"weeks?", None, "a week-denominated duration needs a term calendar to compare"),
    (
        r"ects|ec\b|credits?|units?",
        None,
        "credits measure workload, not elapsed time",
    ),
)

# Built from code points rather than literals: an en dash and an em dash are
# indistinguishable from a hyphen when read in source.
_RANGE_DASHES = "-" + chr(0x2013) + chr(0x2014)
_RANGE = re.compile(rf"\d+(?:\.\d+)?\s*(?:[{_RANGE_DASHES}]|to|or)\s*\d+")
_QUANTITY = re.compile(r"(\d+(?:[.,]\d+)?)\s*([A-Za-z]+)")


def normalize_duration(
    text: str,
    field: str = "duration",
    provenance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Normalize a published program length to months.

    Handles the forms C2 actually stores — `"2 years"`, `"18 months"`,
    `"24 Months"`. Refuses the rest, each for a stated reason:

    * `"1.5 - 2 years"` is a **range**, and picking an end is picking a fact;
    * `"4 semesters"` needs a semester length nobody published;
    * `"120 EC"` is workload, not time;
    * `"two years"` has no digits, and a word-number table is a parsing
      format invented rather than observed.
    """
    published = (text or "").strip() or None
    if not published:
        return _result(
            field, "duration", MISSING, DURATION_RULE, reason="no_value",
            provenance=provenance,
        )  # fmt: skip

    lowered = published.lower()

    if _RANGE.search(lowered):
        return _result(
            field, "duration", AMBIGUOUS, DURATION_RULE,
            published_value=published, provenance=provenance,
            reason=(
                f"duration_is_a_range: '{published}' gives no single length; "
                "choosing an end of the range would be inventing a fact"
            ),
        )  # fmt: skip

    matches = _QUANTITY.findall(lowered)
    if not matches:
        return _result(
            field, "duration", UNSUPPORTED, DURATION_RULE,
            published_value=published, provenance=provenance,
            reason=f"no_numeric_quantity_with_a_unit: '{published}'",
        )  # fmt: skip

    resolved: list[float] = []
    refusal: str | None = None
    for quantity, unit in matches:
        for pattern, factor, why in _DURATION_UNITS:
            if re.fullmatch(pattern, unit):
                if factor is None:
                    refusal = refusal or f"unsupported_duration_unit: {why}"
                else:
                    resolved.append(float(quantity.replace(",", ".")) * factor)
                break

    if not resolved:
        return _result(
            field, "duration", UNSUPPORTED, DURATION_RULE,
            published_value=published, provenance=provenance,
            reason=refusal or f"no_recognised_time_unit_in: '{published}'",
        )  # fmt: skip

    if len({round(m, 4) for m in resolved}) > 1:
        return _result(
            field, "duration", AMBIGUOUS, DURATION_RULE,
            published_value=published, provenance=provenance,
            reason=(
                "conflicting_durations_in_one_value: "
                f"{', '.join(str(round(m, 1)) for m in resolved)} months"
            ),
        )  # fmt: skip

    months = round(resolved[0], 2)
    if months <= 0:
        return _result(
            field, "duration", UNSUPPORTED, DURATION_RULE,
            published_value=published, provenance=provenance,
            reason=f"non_positive_duration: '{published}'",
        )  # fmt: skip

    return _result(
        field, "duration", OK, DURATION_RULE,
        value=months, unit="months", published_value=published,
        provenance=provenance,
    )  # fmt: skip


# --- Deadline --------------------------------------------------------------

DEADLINE_RULE = "norm:deadline:v1"

_ROLLING = re.compile(
    r"rolling|until\s+filled|no\s+deadline|year[-\s]?round|open\s+all\s+year"
    r"|continuous(?:ly)?\s+admission",
    re.IGNORECASE,
)
_PARENTHETICAL = re.compile(r"\([^)]*\)")
_ORDINAL = re.compile(r"(\d{1,2})(st|nd|rd|th)\b", re.IGNORECASE)
_NUMERIC_DATE = re.compile(r"\b\d{1,2}\s*[./-]\s*\d{1,2}\s*[./-]\s*\d{2,4}\b")
_HAS_YEAR = re.compile(r"\b(19|20)\d{2}\b")
_TIMEZONE = re.compile(
    r"\b\d{1,2}:\d{2}\s*(?:[A-Z]{2,5})?\b|\b(?:CET|CEST|GMT|UTC|EST|EDT|PST|PDT)\b"
)

_WITH_YEAR = ("%d %B %Y", "%d %b %Y", "%B %d %Y", "%b %d %Y", "%Y-%m-%d")
_WITHOUT_YEAR = ("%d %B", "%d %b", "%B %d", "%b %d")


def normalize_deadline(
    text: str,
    intake_year: int | None = None,
    field: str = "application_deadline",
    provenance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Normalize a published deadline to an ISO date.

    `"15 January (23:59 CEST)"` — a real retrieved string — carries no year,
    which is the common case: institutions publish deadlines inside a page
    that already establishes the cycle. Such a value resolves only if the
    student's intake year is known, and stays `ambiguous` otherwise rather
    than being assumed into the wrong admissions cycle.

    Numeric dates like `15/12/2026` are refused outright: day-month order is
    genuinely undecidable between conventions, and a deadline off by months
    is a harm this system will not risk.
    """
    published = (text or "").strip() or None
    if not published:
        return _result(
            field, "date", MISSING, DEADLINE_RULE, reason="no_value",
            provenance=provenance,
        )  # fmt: skip

    if _ROLLING.search(published):
        return _result(
            field, "date", UNSUPPORTED, DEADLINE_RULE,
            published_value=published, provenance=provenance,
            reason="rolling_admission: there is no single date to normalize",
        )  # fmt: skip

    # Checked against the published string, before punctuation is stripped —
    # stripping the separators out first would hide the very ambiguity this
    # guard exists to catch.
    if _NUMERIC_DATE.search(published):
        return _result(
            field, "date", AMBIGUOUS, DEADLINE_RULE,
            published_value=published, provenance=provenance,
            reason=(
                f"ambiguous_numeric_date: '{published}' could be day-month or "
                "month-day; the two readings differ by months"
            ),
        )  # fmt: skip

    cleaned = _PARENTHETICAL.sub(" ", published)
    cleaned = _TIMEZONE.sub(" ", cleaned)
    cleaned = _ORDINAL.sub(r"\1", cleaned)
    cleaned = cleaned.replace(",", " ")
    cleaned = re.sub(r"[^\w\s:-]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    for fmt in _WITH_YEAR:
        try:
            parsed = dt.datetime.strptime(cleaned, fmt)
        except ValueError:
            continue
        return _result(
            field, "date", OK, DEADLINE_RULE,
            value=parsed.date().isoformat(), unit="iso_date",
            published_value=published, provenance=provenance,
            year_source="published",
        )  # fmt: skip

    if _HAS_YEAR.search(cleaned):
        return _result(
            field, "date", UNSUPPORTED, DEADLINE_RULE,
            published_value=published, provenance=provenance,
            reason=f"unrecognised_date_format: '{published}'",
        )  # fmt: skip

    if intake_year is None:
        return _result(
            field, "date", AMBIGUOUS, DEADLINE_RULE,
            published_value=published, provenance=provenance,
            reason=(
                f"year_not_published_and_intake_unknown: '{published}' names no "
                "year, and the student's target intake year is not recorded, "
                "so the admissions cycle cannot be determined"
            ),
        )  # fmt: skip

    for fmt in _WITHOUT_YEAR:
        try:
            parsed = dt.datetime.strptime(f"{cleaned} {intake_year}", f"{fmt} %Y")
        except ValueError:
            continue
        return _result(
            field, "date", OK, DEADLINE_RULE,
            value=parsed.date().isoformat(), unit="iso_date",
            published_value=published, provenance=provenance,
            year_source="student_intake_year",
            year_caveat=(
                f"The source did not publish a year; {intake_year} was taken "
                "from the student's target intake. Confirm against the "
                "official page before relying on it."
            ),
        )  # fmt: skip

    return _result(
        field, "date", UNSUPPORTED, DEADLINE_RULE,
        published_value=published, provenance=provenance,
        reason=f"unrecognised_date_format: '{published}'",
    )  # fmt: skip


# --- Boolean ---------------------------------------------------------------

BOOLEAN_RULE = "norm:boolean:v1"

# "We don't know" is not "no". Checked first so an institution that simply
# has not published a designation never reads as one that denies it.
_INDETERMINATE = re.compile(
    r"not\s+(?:published|stated|specified|listed|available|clear|confirmed)"
    r"|unknown|unclear|unspecified|\bn/?a\b|to\s+be\s+confirmed",
    re.IGNORECASE,
)

# A value that is nothing but a negative word. The field name supplies the
# question, so a stored "No" is an answer to it, not a stray token.
_BARE_NEGATIVE = re.compile(r"^\s*(?:no|none|false|not)\s*[.!]?\s*$", re.IGNORECASE)

# Otherwise a negation only counts when it actually attaches to the
# designation, within a short window. A blanket `\bno\b` would read
# "Yes - no separate application needed" as a denial of STEM status.
_BOOLEAN_FALSE = re.compile(
    r"\b(?:no|not|non|isn'?t|ineligible|without)\b[-\s]*(?:\w+\s+){0,3}?"
    r"(?:stem|designat\w*|eligib\w*|opt)\b",
    re.IGNORECASE,
)
_BOOLEAN_TRUE = re.compile(
    r"\byes\b|stem[-\s]?designated|stem\s+designation|designated\s+stem"
    r"|opt\s+eligible|eligible\s+for\s+opt|\bis\s+stem\b|stem\s+eligible"
    r"|\btrue\b|\bstem\b",
    re.IGNORECASE,
)


def normalize_boolean(
    text: str,
    field: str = "stem_designation",
    provenance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Normalize a published yes/no designation.

    Negation is checked before affirmation, because `"not STEM designated"`
    contains `"STEM designated"` and the wrong order would invert the
    meaning of the one field US students care most about.
    """
    published = (text or "").strip() or None
    if not published:
        return _result(
            field, "boolean", MISSING, BOOLEAN_RULE, reason="no_value",
            provenance=provenance,
        )  # fmt: skip

    if _INDETERMINATE.search(published):
        return _result(
            field, "boolean", UNSUPPORTED, BOOLEAN_RULE,
            published_value=published, provenance=provenance,
            reason=(
                f"designation_not_determinable: '{published}' says the status "
                "is unstated, which is not the same as saying it is absent"
            ),
        )  # fmt: skip

    if _BARE_NEGATIVE.match(published) or _BOOLEAN_FALSE.search(published):
        return _result(
            field, "boolean", OK, BOOLEAN_RULE, value=False, unit="boolean",
            published_value=published, provenance=provenance,
        )  # fmt: skip
    if _BOOLEAN_TRUE.search(published):
        return _result(
            field, "boolean", OK, BOOLEAN_RULE, value=True, unit="boolean",
            published_value=published, provenance=provenance,
        )  # fmt: skip

    return _result(
        field, "boolean", UNSUPPORTED, BOOLEAN_RULE,
        published_value=published, provenance=provenance,
        reason=f"not_a_yes_or_no_statement: '{published}'",
    )  # fmt: skip


# --- Test requirements -----------------------------------------------------

TEST_RULE = "norm:test_requirement:v1"

_MENTIONS_GRE = re.compile(r"\bgre\b|\bgmat\b", re.IGNORECASE)
_NOT_REQUIRED = re.compile(
    r"not\s+required|no\s+longer\s+required|not\s+accepted|waived\s+for\s+all"
    r"|do\s+not\s+require|does\s+not\s+require|no\s+gre|without\s+a?\s*gre",
    re.IGNORECASE,
)
_OPTIONAL = re.compile(
    r"optional|if\s+provided|if\s+submitted|may\s+be\s+submitted|encouraged"
    r"|will\s+be\s+considered|not\s+mandatory|recommended\s+but",
    re.IGNORECASE,
)
_REQUIRED = re.compile(r"\brequired\b|\bmandatory\b|must\s+submit", re.IGNORECASE)

# Burden ordering, low to high. Scoring needs a number; the mapping is here
# and versioned so it is inspectable rather than buried in the scorer.
TEST_BURDEN = {"not_required": 0.0, "optional": 1.0, "required": 2.0}


def normalize_test_requirement(
    text: str,
    field: str = "test_requirements",
    provenance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Normalize a published GRE/GMAT requirement into a burden level.

    The `test_requirements` field mixes admissions tests with English-language
    tests — a real retrieved value is `"A minimum overall score of 7.5 is
    required, with minimum section scores as follows..."`, which is IELTS and
    says nothing about the GRE. A value that never names the GRE or GMAT is
    therefore refused rather than read as a GRE requirement.
    """
    published = (text or "").strip() or None
    if not published:
        return _result(
            field, "test_requirement", MISSING, TEST_RULE, reason="no_value",
            provenance=provenance,
        )  # fmt: skip

    if not _MENTIONS_GRE.search(published):
        return _result(
            field, "test_requirement", UNSUPPORTED, TEST_RULE,
            published_value=published, provenance=provenance,
            reason=(
                "no_gre_or_gmat_statement: this value describes some other "
                "requirement, and reading it as a GRE rule would invent one"
            ),
        )  # fmt: skip

    # Order matters: "not required" and "if provided" both also match the
    # bare word "required" further down the string.
    if _NOT_REQUIRED.search(published):
        level = "not_required"
    elif _OPTIONAL.search(published):
        level = "optional"
    elif _REQUIRED.search(published):
        level = "required"
    else:
        return _result(
            field, "test_requirement", UNSUPPORTED, TEST_RULE,
            published_value=published, provenance=provenance,
            reason=f"gre_mentioned_but_no_clear_rule: '{published}'",
        )  # fmt: skip

    return _result(
        field, "test_requirement", OK, TEST_RULE,
        value=TEST_BURDEN[level], unit="burden_level",
        published_value=published, provenance=provenance,
        level=level,
    )  # fmt: skip


# --- Provenance ------------------------------------------------------------

# Everything a scorer or a citation needs, carried out of the rendered
# ProgramRecord field unchanged. Freshness and conflict information is part
# of this set precisely so it survives into the final answer.
PROVENANCE_KEYS: tuple[str, ...] = (
    "tier",
    "source_domain",
    "source_is_official",
    "source_url",
    "url_is_grounding_redirect",
    "retrieved_at",
    "staleness_class",
    "is_stale",
    "staleness_notice",
    "supporting_quote",
    "source_count",
    "all_source_domains",
)


def extract_provenance(rendered_field: dict[str, Any] | None) -> dict[str, Any] | None:
    """Lift the provenance of a rendered C2 field into a normalized record."""
    if not isinstance(rendered_field, dict):
        return None
    out: dict[str, Any] = {key: rendered_field.get(key) for key in PROVENANCE_KEYS}
    conflicts = rendered_field.get("conflicts") or []
    out["has_conflict"] = bool(conflicts)
    out["conflicting_values"] = [c.get("value") for c in conflicts]
    out["corroboration_count"] = len(rendered_field.get("corroborations") or [])
    return out


def _value_of(rendered: dict[str, Any], field: str) -> str:
    entry = (rendered.get("fields") or {}).get(field) or {}
    return str(entry.get("value") or "")


def _field_of(rendered: dict[str, Any], field: str) -> dict[str, Any] | None:
    return (rendered.get("fields") or {}).get(field)


def normalize_program(
    rendered: dict[str, Any], intake_year: int | None = None
) -> dict[str, Any]:
    """Normalize one rendered ProgramRecord into comparable quantities.

    Input is the output of `program_store.render_program` — no state, no
    session, no tool context. Output carries every registry dimension plus
    the display-only deadline, each with its status and its provenance.

    Duration is normalized first because money normalization needs it: a
    whole-program fee can only be annualized against a known length.
    """
    duration = normalize_duration(
        _value_of(rendered, "duration"),
        provenance=extract_provenance(_field_of(rendered, "duration")),
    )
    months = duration["value"] if duration["status"] == OK else None

    money = normalize_money(
        _value_of(rendered, "tuition_amount"),
        _value_of(rendered, "tuition_currency"),
        _value_of(rendered, "tuition_basis"),
        duration_months=months,
        provenance=extract_provenance(_field_of(rendered, "tuition_amount")),
    )

    dimensions = {
        "cost": money,
        "duration": duration,
        "stem": normalize_boolean(
            _value_of(rendered, "stem_designation"),
            provenance=extract_provenance(_field_of(rendered, "stem_designation")),
        ),
        "test_burden": normalize_test_requirement(
            _value_of(rendered, "test_requirements"),
            provenance=extract_provenance(_field_of(rendered, "test_requirements")),
        ),
    }
    assert set(dimensions) == set(DIMENSIONS), "dimension registry drift"

    return {
        "program_id": rendered.get("program_id"),
        "university": rendered.get("university"),
        "program": rendered.get("program"),
        "dimensions": dimensions,
        "display_only": {
            "application_deadline": normalize_deadline(
                _value_of(rendered, "application_deadline"),
                intake_year=intake_year,
                provenance=extract_provenance(
                    _field_of(rendered, "application_deadline")
                ),
            )
        },
        "tuition_academic_year": _value_of(rendered, "tuition_academic_year") or None,
        "unknown_fields": rendered.get("unknown_fields", []),
        "stale_fields": rendered.get("stale_fields", []),
        "normalizer_version": VERSION,
    }
