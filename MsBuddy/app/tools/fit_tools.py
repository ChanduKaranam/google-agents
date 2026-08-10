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

"""`match_universities` — discovery over the curated reference dataset.

Joins the stored profile to `app.reference.universities` through the
deterministic assessment in `app.fit`. Answers "which well-known
universities fit my profile, roughly" — the shortlist a student explores
*before* research, not instead of it. Every result carries the typical-data
disclaimer, and anything current still goes through `build_program_query` →
research → `save_program_record`.

Reads state, never writes it. Only the fit-relevant profile fields are
extracted; protected attributes stay in the profile.
"""

from __future__ import annotations

from google.adk.tools import ToolContext

from app.config import STATE_PROFILE
from app.fit import FIT_BANDS, assess_fit
from app.profile_store import read_profile
from app.reference.universities import TYPICAL_DISCLAIMER, UNIVERSITIES

# The only profile fields fit may see. An allowlist rather than "everything
# but citizenship", so a future profile field is excluded until someone
# decides otherwise.
_FIT_FIELDS = ("gpa_value", "gpa_scale", "ielts_overall", "specialization_interest")


def match_universities(country: str, program: str, tool_context: ToolContext) -> dict:
    """Match the student's stored profile against the reference universities.

    Compares the profile's GPA, English score and subject interest with each
    university's typical historical norms, and returns a fit band per
    university — strong, good, moderate or ambitious — with the factors
    spelled out. This is a planning aid over reference data: it is not an
    admission estimate, and current requirements still need research.

    Args:
        country: Optional country filter, e.g. `USA`, `Germany`. Empty means
            every country in the dataset.
        program: Optional subject filter, e.g. `Computer Science`,
            `Robotics`. Empty means any program.

    Returns:
        A dict with `matches` ordered strongest band first, each carrying
        `band`, `factors`, and the university's official website, plus the
        typical-data disclaimer.
    """
    fields = read_profile(tool_context.state, STATE_PROFILE).get("fields") or {}
    profile = {
        name: (fields.get(name) or {}).get("value")
        for name in _FIT_FIELDS
        if name in fields
    }

    wanted_country = str(country or "").strip().casefold()
    wanted_program = str(program or "").strip().casefold()

    candidates = [
        u
        for u in UNIVERSITIES
        if (not wanted_country or u["country"].casefold() == wanted_country)
        and (
            not wanted_program
            or any(
                wanted_program in p.casefold() or p.casefold() in wanted_program
                for p in u["programs"]
            )
        )
    ]

    available_countries = sorted({u["country"] for u in UNIVERSITIES})
    if not candidates:
        return {
            "status": "success",
            "matches": [],
            "available_countries": available_countries,
            "note": (
                "The reference dataset has no entry matching that filter. It "
                "covers only ~20 well-known universities — a university not "
                "being listed means nothing about its quality, and program "
                "research works for any university."
            ),
            "disclaimer": TYPICAL_DISCLAIMER,
        }

    matches = []
    for university in candidates:
        assessment = assess_fit(profile, university)
        if assessment["status"] != "success":
            # Every candidate fails the same way (the gap is in the profile),
            # so the first refusal is the answer.
            return {
                "status": "error",
                "reason": assessment["reason"],
                "message": assessment["message"],
            }
        matches.append(
            {
                "university": university["name"],
                "country": university["country"],
                "city": university["city"],
                "programs": university["programs"],
                "band": assessment["band"],
                "factors": assessment["factors"],
                "gre_policy": university["gre_policy"],
                "intakes": university["intakes"],
                "website": university["website"],
            }
        )

    matches.sort(key=lambda m: (FIT_BANDS.index(m["band"]), m["university"]))

    return {
        "status": "success",
        "matches": matches,
        "bands_order": list(FIT_BANDS),
        "available_countries": available_countries,
        "note": (
            "Bands are a planning aid over typical historical data, not an "
            "admission estimate. Research a program to get its current, "
            "sourced requirements and deadline."
        ),
        "disclaimer": TYPICAL_DISCLAIMER,
    }
