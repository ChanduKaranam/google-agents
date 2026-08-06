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

"""The student profile field registry.

This is an allowlist. A field name absent from `FIELDS` cannot be written,
which is the first of the structural controls behind C1's "zero unstated
fields ever written".

`why_it_matters` is not documentation — it is returned verbatim by
`profile_completeness`, because C1 requires the completeness report to name
"which fields are missing **and why each matters**".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from app.reference.gpa_scales import SCALE_KEYS

Importance = Literal["core", "recommended", "optional"]

# Guards the named C1 failure case: intake term ambiguity ("Fall 25").
MIN_INTAKE_YEAR = 2020
MAX_INTAKE_YEAR = 2100


@dataclass(frozen=True)
class ProfileFieldSpec:
    """Definition of one writable profile field."""

    name: str
    group: str
    importance: Importance
    why_it_matters: str
    kind: Literal["text", "integer", "decimal", "enum", "list", "year"]
    minimum: float | None = None
    maximum: float | None = None
    choices: tuple[str, ...] = ()
    requires: tuple[str, ...] = field(default_factory=tuple)


FIELDS: dict[str, ProfileFieldSpec] = {
    # --- Academics ---------------------------------------------------------
    "undergrad_degree": ProfileFieldSpec(
        name="undergrad_degree",
        group="academics",
        importance="core",
        why_it_matters=(
            "Programs state prerequisite backgrounds; without your degree "
            "there is no way to check whether you meet them."
        ),
        kind="text",
    ),
    "undergrad_institution": ProfileFieldSpec(
        name="undergrad_institution",
        group="academics",
        importance="recommended",
        why_it_matters=(
            "Used only as an affinity anchor when ranking alumni you might "
            "have something in common with. Never sent to a search engine."
        ),
        kind="text",
    ),
    "gpa_value": ProfileFieldSpec(
        name="gpa_value",
        group="academics",
        importance="core",
        why_it_matters=(
            "Academic standing is the most commonly stated admissions "
            "requirement. Must be supplied together with its scale."
        ),
        kind="decimal",
        minimum=0.0,
        maximum=100.0,
        requires=("gpa_scale",),
    ),
    "gpa_scale": ProfileFieldSpec(
        name="gpa_scale",
        group="academics",
        importance="core",
        why_it_matters=(
            "A number like 7.2 means nothing without its scale. Recording the "
            "scale explicitly is what prevents a percentage being read as a "
            "10-point CGPA."
        ),
        kind="enum",
        choices=SCALE_KEYS,
    ),
    "backlogs": ProfileFieldSpec(
        name="backlogs",
        group="academics",
        importance="optional",
        why_it_matters=(
            "Some programs publish an explicit limit on active or historical backlogs."
        ),
        kind="integer",
        minimum=0,
        maximum=100,
    ),
    # --- Tests -------------------------------------------------------------
    "gre_quant": ProfileFieldSpec(
        name="gre_quant",
        group="tests",
        importance="recommended",
        why_it_matters="Quant is the section most often given a stated minimum.",
        kind="integer",
        minimum=130,
        maximum=170,
    ),
    "gre_verbal": ProfileFieldSpec(
        name="gre_verbal",
        group="tests",
        importance="recommended",
        why_it_matters="Recorded separately from Quant so a total is never guessed.",
        kind="integer",
        minimum=130,
        maximum=170,
    ),
    "gre_awa": ProfileFieldSpec(
        name="gre_awa",
        group="tests",
        importance="optional",
        why_it_matters="A few programs state an AWA minimum.",
        kind="decimal",
        minimum=0.0,
        maximum=6.0,
    ),
    "gmat_total": ProfileFieldSpec(
        name="gmat_total",
        group="tests",
        importance="optional",
        why_it_matters="Accepted instead of the GRE by some management programs.",
        kind="integer",
        minimum=200,
        maximum=800,
    ),
    "toefl_total": ProfileFieldSpec(
        name="toefl_total",
        group="tests",
        importance="recommended",
        why_it_matters=(
            "English proficiency minimums are commonly published and are a "
            "hard filter when unmet."
        ),
        kind="integer",
        minimum=0,
        maximum=120,
    ),
    "ielts_overall": ProfileFieldSpec(
        name="ielts_overall",
        group="tests",
        importance="recommended",
        why_it_matters="Alternative English proficiency evidence to TOEFL.",
        kind="decimal",
        minimum=0.0,
        maximum=9.0,
    ),
    "pte_overall": ProfileFieldSpec(
        name="pte_overall",
        group="tests",
        importance="optional",
        why_it_matters="Accepted by a subset of programs in place of TOEFL/IELTS.",
        kind="integer",
        minimum=10,
        maximum=90,
    ),
    "duolingo_overall": ProfileFieldSpec(
        name="duolingo_overall",
        group="tests",
        importance="optional",
        why_it_matters="Accepted by a growing but still partial set of programs.",
        kind="integer",
        minimum=10,
        maximum=160,
    ),
    # --- Experience --------------------------------------------------------
    "work_experience_months": ProfileFieldSpec(
        name="work_experience_months",
        group="experience",
        importance="recommended",
        why_it_matters=(
            "Some programs require or strongly prefer prior experience. "
            "Stored in months so partial years are never rounded away."
        ),
        kind="integer",
        minimum=0,
        maximum=600,
    ),
    "publications_count": ProfileFieldSpec(
        name="publications_count",
        group="experience",
        importance="optional",
        why_it_matters="Relevant mainly for research-oriented and thesis programs.",
        kind="integer",
        minimum=0,
        maximum=200,
    ),
    # --- Targets -----------------------------------------------------------
    "target_intake_term": ProfileFieldSpec(
        name="target_intake_term",
        group="targets",
        importance="core",
        why_it_matters=(
            "Deadlines are per-intake. Without the term, every date produced "
            "would be a guess."
        ),
        kind="enum",
        choices=("fall", "spring", "summer", "winter"),
    ),
    "target_intake_year": ProfileFieldSpec(
        name="target_intake_year",
        group="targets",
        importance="core",
        why_it_matters=(
            "The single most common source of a wrong plan. Must be a "
            "four-digit year so that 'Fall 25' can never be ambiguous."
        ),
        kind="year",
        minimum=MIN_INTAKE_YEAR,
        maximum=MAX_INTAKE_YEAR,
    ),
    "target_countries": ProfileFieldSpec(
        name="target_countries",
        group="targets",
        importance="core",
        why_it_matters=("Scopes program research. Supplied as a comma-separated list."),
        kind="list",
    ),
    "specialization_interest": ProfileFieldSpec(
        name="specialization_interest",
        group="targets",
        importance="core",
        why_it_matters="Determines which programs are worth researching at all.",
        kind="text",
    ),
    # --- Constraints -------------------------------------------------------
    "budget_ceiling": ProfileFieldSpec(
        name="budget_ceiling",
        group="constraints",
        importance="recommended",
        why_it_matters=(
            "Filters the shortlist before effort is spent on programs that "
            "are out of reach. Must be supplied with its currency."
        ),
        kind="decimal",
        minimum=0.0,
        maximum=10_000_000.0,
        requires=("budget_currency",),
    ),
    "budget_currency": ProfileFieldSpec(
        name="budget_currency",
        group="constraints",
        importance="recommended",
        why_it_matters=(
            "A budget figure without a currency cannot be compared against "
            "tuition. Three-letter ISO-4217 code."
        ),
        kind="text",
    ),
    "funding_intent": ProfileFieldSpec(
        name="funding_intent",
        group="constraints",
        importance="optional",
        why_it_matters="Changes which programs and deadlines are worth prioritising.",
        kind="enum",
        choices=("self", "loan", "scholarship", "assistantship", "mixed"),
    ),
    "citizenship": ProfileFieldSpec(
        name="citizenship",
        group="constraints",
        importance="optional",
        why_it_matters=(
            "Affects fee status and work-authorisation routes. Recorded only "
            "if you state it — it is never inferred from anything else."
        ),
        kind="text",
    ),
    "visa_constraints": ProfileFieldSpec(
        name="visa_constraints",
        group="constraints",
        importance="optional",
        why_it_matters="Any known restriction that would rule a country in or out.",
        kind="text",
    ),
}

# Written only by derivation, never by `save_profile_fields`. Keeping these
# out of `FIELDS` is what makes "derived != stated" structural rather than a
# convention the model is asked to respect.
DERIVED_FIELDS: dict[str, str] = {
    "gpa_us_4pt": (
        "US 4.0 equivalent of your GPA, derived from gpa_value and gpa_scale."
    ),
}

CORE_FIELDS: tuple[str, ...] = tuple(
    n for n, s in FIELDS.items() if s.importance == "core"
)


def is_writable(field_name: str) -> bool:
    """True if `field_name` may be written by a student-facing tool."""
    return field_name in FIELDS


def _fail(field_name: str, message: str) -> dict[str, Any]:
    return {"ok": False, "field": field_name, "message": message}


def validate_field(field_name: str, raw_value: str) -> dict[str, Any]:
    """Validate and coerce one raw string value against the registry.

    Returns `{"ok": True, "value": <coerced>}` or `{"ok": False, "message": ...}`.
    Never raises — callers surface the message to the student.
    """
    spec = FIELDS.get(field_name)
    if spec is None:
        if field_name in DERIVED_FIELDS:
            return _fail(
                field_name,
                f"'{field_name}' is a derived field and cannot be set directly. "
                "It is computed from the fields it depends on.",
            )
        return _fail(
            field_name,
            f"'{field_name}' is not a known profile field. "
            f"Known fields: {', '.join(sorted(FIELDS))}.",
        )

    text = str(raw_value).strip()
    if not text:
        return _fail(field_name, f"No value supplied for '{field_name}'.")

    if spec.kind == "text":
        return {"ok": True, "value": text}

    if spec.kind == "enum":
        lowered = text.lower()
        if lowered not in spec.choices:
            return _fail(
                field_name,
                f"'{text}' is not a valid {field_name}. "
                f"Valid values: {', '.join(spec.choices)}.",
            )
        return {"ok": True, "value": lowered}

    if spec.kind == "list":
        items = [part.strip() for part in text.split(",") if part.strip()]
        if not items:
            return _fail(field_name, f"No usable entries in '{field_name}'.")
        return {"ok": True, "value": items}

    if spec.kind == "year":
        try:
            year = int(text)
        except ValueError:
            return _fail(field_name, f"'{text}' is not a whole year.")
        if year < 1000:
            return _fail(
                field_name,
                f"'{text}' is ambiguous — a two-digit year could mean more "
                "than one intake. Ask the student for the full four-digit year.",
            )
        if not MIN_INTAKE_YEAR <= year <= MAX_INTAKE_YEAR:
            return _fail(
                field_name,
                f"{year} is outside the supported intake range "
                f"({MIN_INTAKE_YEAR}-{MAX_INTAKE_YEAR}).",
            )
        return {"ok": True, "value": year}

    if spec.kind == "integer":
        try:
            number: float = float(text)
        except ValueError:
            return _fail(field_name, f"'{text}' is not a number.")
        if number != int(number):
            return _fail(
                field_name, f"'{text}' must be a whole number for {field_name}."
            )
        coerced = int(number)
        if spec.minimum is not None and coerced < spec.minimum:
            return _fail(
                field_name,
                f"{coerced} is below the valid range for {field_name} "
                f"({int(spec.minimum)}-{int(spec.maximum or 0)}).",
            )
        if spec.maximum is not None and coerced > spec.maximum:
            return _fail(
                field_name,
                f"{coerced} is above the valid range for {field_name} "
                f"({int(spec.minimum or 0)}-{int(spec.maximum)}).",
            )
        return {"ok": True, "value": coerced}

    # decimal
    try:
        value = float(text)
    except ValueError:
        return _fail(field_name, f"'{text}' is not a number.")
    if spec.minimum is not None and value < spec.minimum:
        return _fail(
            field_name,
            f"{value} is below the valid range for {field_name} "
            f"({spec.minimum}-{spec.maximum}).",
        )
    if spec.maximum is not None and value > spec.maximum:
        return _fail(
            field_name,
            f"{value} is above the valid range for {field_name} "
            f"({spec.minimum}-{spec.maximum}).",
        )
    return {"ok": True, "value": value}
