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

"""The alumni field registry and the privacy boundary (C4, Stage 0 §7).

Same shape as `program_fields`: a field absent from `ALUMNI_FIELDS` cannot be
written, and missing fields are returned as `UNKNOWN` by name rather than
omitted, so a coverage gap never reads as an absence.

Two things are different here, and both come from the subject being a person
rather than an institution.

**Everything ages.** Every alumni claim carries the `PERSON` staleness class
(180 days, already defined in `evidence.STALENESS_TTL_DAYS`). A degree does
not change, but the page asserting it may be revised or withdrawn, and a
role certainly changes. Uniform `PERSON` is the conservative choice: it
over-prompts re-verification rather than under-prompting it.

**Most things about a person are none of our business.** `PROHIBITED_FIELDS`
is not a list of things we forgot to implement — it is a list of things that
must never be stored even when a public page publishes them. The test for
inclusion in `ALUMNI_FIELDS` is narrow: *does this help an applicant
evaluate a program?* A home address does not. Neither does a photograph.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass

from app.reference.source_authority import (
    DEGREE,
    EMPLOYER,
    GRADUATION_YEAR,
    PRIOR_DEGREE,
    PRIOR_INSTITUTION,
    PROGRAM,
    ROLE,
    UNIVERSITY_AFFILIATION,
)

VERSION = "alumni_fields:v1"

# Every alumni claim ages, whatever it is about. See the module docstring.
ALUMNI_STALENESS_CLASS = "PERSON"


@dataclass(frozen=True)
class AlumniFieldSpec:
    """One claim that may be made about an alumnus."""

    name: str
    description: str
    # Why an MS applicant is entitled to this, in one line. A field that
    # cannot answer this question does not belong in the registry.
    decision_value: str


ALUMNI_FIELDS: dict[str, AlumniFieldSpec] = {
    UNIVERSITY_AFFILIATION: AlumniFieldSpec(
        name=UNIVERSITY_AFFILIATION,
        description="That this person attended the institution in question.",
        decision_value="Without it there is no reason to show this person at all.",
    ),
    PROGRAM: AlumniFieldSpec(
        name=PROGRAM,
        description="The program as published, e.g. 'MSc Computer Science'.",
        decision_value="The student is choosing between programs, not universities.",
    ),
    DEGREE: AlumniFieldSpec(
        name=DEGREE,
        description="The awarded degree as published.",
        decision_value="Distinguishes an MSc from an exchange or a PhD.",
    ),
    GRADUATION_YEAR: AlumniFieldSpec(
        name=GRADUATION_YEAR,
        description="Four-digit year of graduation, exactly as stated.",
        decision_value="Tells the student how current this path is.",
    ),
    EMPLOYER: AlumniFieldSpec(
        name=EMPLOYER,
        description="Employer named by the source, at the time it was published.",
        decision_value="The outcome question the student is actually asking.",
    ),
    ROLE: AlumniFieldSpec(
        name=ROLE,
        description="Job title or role as published.",
        decision_value="An employer without a role says little about the work.",
    ),
    PRIOR_INSTITUTION: AlumniFieldSpec(
        name=PRIOR_INSTITUTION,
        description="Institution attended before this program.",
        decision_value="An affinity anchor: 'someone from my university did this'.",
    ),
    PRIOR_DEGREE: AlumniFieldSpec(
        name=PRIOR_DEGREE,
        description="Prior degree or field of study.",
        decision_value="An affinity anchor: 'someone with my background did this'.",
    ),
}

ALL_FIELD_NAMES: tuple[str, ...] = tuple(ALUMNI_FIELDS)

# Anchors used to rank alumni by relevance to the student. Computed locally,
# never sent to a search engine.
AFFINITY_FIELDS: frozenset[str] = frozenset({PRIOR_INSTITUTION, PRIOR_DEGREE, PROGRAM})

# --- The privacy boundary --------------------------------------------------

# Never stored, never displayed, never inferred — even when a public page
# publishes them. A source publishing something does not make it ours to
# keep. `citizenship`-style attributes appear here because matching on them
# would be both a privacy violation and a discriminatory filter.
PROHIBITED_FIELDS: frozenset[str] = frozenset(
    {
        "email",
        "email_address",
        "personal_email",
        "contact",
        "phone",
        "phone_number",
        "mobile",
        "telephone",
        "whatsapp",
        "address",
        "home_address",
        "street_address",
        "postal_code",
        "location",
        "city",
        "country_of_residence",
        "residence",
        "gender",
        "pronouns",
        "sex",
        "nationality",
        "citizenship",
        "ethnicity",
        "race",
        "religion",
        "date_of_birth",
        "dob",
        "age",
        "marital_status",
        "family",
        "health",
        "disability",
        "salary",
        "compensation",
        "pay",
        "photo",
        "photograph",
        "image",
        "avatar",
        "twitter",
        "instagram",
        "facebook",
        "handle",
        "social",
        "linkedin",
        "linkedin_url",
    }
)

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")

# Candidate digit runs, then a length test. A bare pattern of "7+ digits with
# separators" also matches a year range like "2021-2023", so the digit count
# does the real work: a phone number carries 9+ digits, or 8+ behind a
# country-code `+`. A graduation-year range has 8 and no `+`.
_PHONE_CANDIDATE = re.compile(r"[+(]?\d[\d\s().-]{5,}\d")
MIN_PHONE_DIGITS = 9
MIN_INTERNATIONAL_PHONE_DIGITS = 8


def is_prohibited_field(field_name: str) -> bool:
    """True if this field must never be stored, whatever the source says."""
    return str(field_name or "").strip().lower() in PROHIBITED_FIELDS


def contains_contact_details(text: str) -> bool:
    """True if `text` looks like it carries an email address or phone number.

    Used to drop a claim whose *value* smuggles contact details in, rather
    than only checking the field name. C5 handles outreach with its own
    consent story; Phase 4 stores none of this.
    """
    candidate = str(text or "")
    if _EMAIL.search(candidate):
        return True

    for run in _PHONE_CANDIDATE.findall(candidate):
        if _is_only_years(run):
            continue
        digits = sum(1 for ch in run if ch.isdigit())
        if digits >= MIN_PHONE_DIGITS:
            return True
        if run.lstrip().startswith("+") and digits >= MIN_INTERNATIONAL_PHONE_DIGITS:
            return True
    return False


def _is_only_years(run: str) -> bool:
    """True if every digit group in `run` is a plausible four-digit year.

    `2019 2020 2021` carries twelve digits and would otherwise read as a
    phone number. A run made only of years is a list of years — no phone
    number is written as a sequence of 4-digit groups in the 1900-2100 band.
    """
    groups = [g for g in re.split(r"\D+", run) if g]
    if not groups:
        return False
    return all(len(g) == 4 and 1900 <= int(g) <= 2100 for g in groups)


# --- Registry helpers ------------------------------------------------------


def is_writable(field_name: str) -> bool:
    """True if `field_name` may be stored on an alumni record."""
    return field_name in ALUMNI_FIELDS and not is_prohibited_field(field_name)


def staleness_class_for(field_name: str) -> str:
    """Staleness class for an alumni claim. Uniformly `PERSON` — see above."""
    return ALUMNI_STALENESS_CLASS


# --- Value validation ------------------------------------------------------

_FOUR_DIGIT_YEAR = re.compile(r"^\s*(\d{4})\s*$")

# A graduation year outside this window is a parsing error or a fabrication,
# not a fact. The upper bound allows for a currently-enrolled student whose
# expected year is published.
EARLIEST_GRADUATION_YEAR = 1900
GRADUATION_YEAR_LOOKAHEAD = 10

MAX_VALUE_LENGTH = 200


def validate_alumni_value(field_name: str, value: str) -> dict[str, object]:
    """Deterministically check one proposed claim value.

    Returns `{"status": "ok", "value": ...}` or a refusal naming the reason.
    This runs before any evidence check: a value that is not even well
    formed cannot be admitted however good its citation looks.
    """
    if not is_writable(field_name):
        return {
            "status": "error",
            "reason": "unknown_field",
            "message": (
                f"'{field_name}' is not an alumni field. Known fields: "
                f"{', '.join(ALL_FIELD_NAMES)}."
            ),
        }

    text = str(value or "").strip()
    if not text:
        return {
            "status": "error",
            "reason": "empty_value",
            "message": f"No value supplied for '{field_name}'.",
        }

    if len(text) > MAX_VALUE_LENGTH:
        return {
            "status": "error",
            "reason": "value_too_long",
            "message": (
                f"'{field_name}' is {len(text)} characters. A claim this long "
                "is prose, not a field value."
            ),
        }

    if contains_contact_details(text):
        return {
            "status": "error",
            "reason": "contact_details_in_value",
            "message": (
                "This value contains what looks like contact information. "
                "MS Buddy does not store contact details for anyone."
            ),
        }

    if field_name == GRADUATION_YEAR:
        return _validate_year(text)

    return {"status": "ok", "value": text}


def _validate_year(text: str) -> dict[str, object]:
    match = _FOUR_DIGIT_YEAR.match(text)
    if not match:
        return {
            "status": "error",
            "reason": "not_a_four_digit_year",
            "message": (
                f"'{text}' is not a four-digit year. A two-digit year is "
                "ambiguous and a range is not a graduation year."
            ),
        }

    year = int(match.group(1))
    latest = dt.datetime.now(dt.UTC).year + GRADUATION_YEAR_LOOKAHEAD
    if not EARLIEST_GRADUATION_YEAR <= year <= latest:
        return {
            "status": "error",
            "reason": "year_out_of_range",
            "message": (
                f"{year} is outside the plausible range "
                f"{EARLIEST_GRADUATION_YEAR}-{latest}."
            ),
        }
    return {"status": "ok", "value": str(year)}
