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

"""Deterministic profile-fit assessment against the reference dataset.

Same split as `app.scoring` and `app.affinity`: Python decides, the model
narrates. Fit is a **band with named factors**, not a score:

* Bands are `strong / good / moderate / ambitious` — the words the product
  promises, in that order, so "one band weaker" is an index step.
* Every factor states the student's value, the typical value it was compared
  to, and a one-word verdict. Nothing is hidden inside a weight.
* **No percentage exists anywhere in the output**, because "78% fit" is one
  paraphrase away from "78% chance of admission" — a claim nothing in this
  system can support. `not_an_admission_estimate` is set on every result and
  the disclaimer travels with it.

The comparison side comes from `app.reference.universities`, whose values
are typical historical norms, not current requirements — which is why the
band is a planning aid ("reach/target/safe" in the product's words) and the
current figures still come from C2 research.

Pure Python: no ADK, no network, no state. The tool wrapper lives in
`app/tools/fit_tools.py`.
"""

from __future__ import annotations

from typing import Any

from app.reference.gpa_scales import convert_to_us_4pt
from app.reference.universities import TYPICAL_DISCLAIMER

VERSION = "fit:v1"

FIT_BANDS: tuple[str, ...] = ("strong", "good", "moderate", "ambitious")

# GPA distance from the typical value → starting band.
_STRONG_AT = 0.15
_GOOD_AT = -0.10
_MODERATE_AT = -0.30

# An English score this far under the typical one costs a band. A *missing*
# score costs nothing — it is a gap to report, not evidence of weakness.
_ENGLISH_SHORTFALL = 0.5


def _weaken(band: str, steps: int = 1) -> str:
    return FIT_BANDS[min(FIT_BANDS.index(band) + steps, len(FIT_BANDS) - 1)]


def _student_gpa_4pt(profile: dict[str, Any]) -> dict[str, Any]:
    value = profile.get("gpa_value")
    scale = profile.get("gpa_scale")
    if value is None or not scale:
        return {
            "status": "error",
            "reason": "gpa_missing",
            "message": (
                "Fit needs the student's GPA and its scale. Ask for whichever "
                "is missing rather than assuming one."
            ),
        }
    converted = convert_to_us_4pt(float(value), str(scale))
    if converted.get("status") != "success":
        return {
            "status": "error",
            "reason": converted.get("reason", "gpa_unconvertible"),
            "message": converted.get("message", "The GPA could not be converted."),
        }
    return {"status": "success", "us_4pt": float(converted["us_4pt_equivalent"])}


def assess_fit(profile: dict[str, Any], university: dict[str, Any]) -> dict[str, Any]:
    """Assess one student profile against one reference-dataset entry.

    `profile` is a plain `{field_name: value}` mapping. Only `gpa_value`,
    `gpa_scale`, `ielts_overall` and `specialization_interest` are read —
    protected attributes such as citizenship are never touched.
    """
    gpa = _student_gpa_4pt(profile)
    if gpa["status"] != "success":
        return {
            "status": "error",
            "version": VERSION,
            "university": university["name"],
            "reason": gpa["reason"],
            "message": gpa["message"],
        }

    factors: list[dict[str, Any]] = []

    # GPA — the anchor factor, and the one that sets the starting band.
    student_gpa = round(gpa["us_4pt"], 2)
    typical_gpa = float(university["typical_gpa_4pt"])
    delta = student_gpa - typical_gpa
    if delta >= _STRONG_AT:
        band = "strong"
        gpa_verdict = "above_typical"
    elif delta >= _GOOD_AT:
        band = "good"
        gpa_verdict = "near_typical"
    elif delta >= _MODERATE_AT:
        band = "moderate"
        gpa_verdict = "slightly_below_typical"
    else:
        band = "ambitious"
        gpa_verdict = "below_typical"
    factors.append(
        {
            "factor": "gpa",
            "student_value": student_gpa,
            "typical_value": typical_gpa,
            "verdict": gpa_verdict,
            "note": "Student GPA converted to a US 4.0 scale (approximation).",
        }
    )

    # Competitiveness — a highly competitive pool costs a band regardless of
    # the numbers, which is what keeps a 3.8 honest about a school where the
    # typical admit also has a 3.8.
    competitiveness = str(university["competitiveness"])
    if competitiveness == "highly_competitive":
        band = _weaken(band)
    factors.append(
        {
            "factor": "competitiveness",
            "student_value": None,
            "typical_value": competitiveness,
            "verdict": competitiveness,
            "note": "Highly competitive pools weaken the band by one step.",
        }
    )

    # English — only a *known* shortfall costs anything.
    ielts = profile.get("ielts_overall")
    typical_ielts = float(university["typical_ielts"])
    if ielts is None:
        english_verdict = "unknown"
        english_note = "No English test score recorded yet; worth adding."
    elif float(ielts) <= typical_ielts - _ENGLISH_SHORTFALL:
        band = _weaken(band)
        english_verdict = "below_typical"
        english_note = "IELTS is clearly under the typical level here."
    elif float(ielts) >= typical_ielts:
        english_verdict = "meets_typical"
        english_note = "IELTS meets the typical level."
    else:
        english_verdict = "near_typical"
        english_note = "IELTS is close to the typical level."
    factors.append(
        {
            "factor": "english",
            "student_value": None if ielts is None else float(ielts),
            "typical_value": typical_ielts,
            "verdict": english_verdict,
            "note": english_note,
        }
    )

    # Program alignment — informational: the tool already filters by subject,
    # so a mismatch here means the student is exploring, not failing.
    interest = str(profile.get("specialization_interest") or "").casefold().strip()
    programs = [str(p) for p in university["programs"]]
    if not interest:
        alignment = "unknown"
    elif any(interest in p.casefold() or p.casefold() in interest for p in programs):
        alignment = "aligned"
    else:
        alignment = "different_field"
    factors.append(
        {
            "factor": "program_alignment",
            "student_value": profile.get("specialization_interest"),
            "typical_value": programs,
            "verdict": alignment,
            "note": "Whether the stated interest matches a listed program.",
        }
    )

    return {
        "status": "success",
        "version": VERSION,
        "university": university["name"],
        "band": band,
        "factors": factors,
        "not_an_admission_estimate": True,
        "disclaimer": TYPICAL_DISCLAIMER,
    }
