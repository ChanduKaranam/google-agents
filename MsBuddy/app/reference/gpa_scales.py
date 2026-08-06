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

"""Versioned GPA scale definitions and conversions to a US 4.0 equivalent.

**These are linear approximations, not credential evaluations.** A real
WES/ECE evaluation uses band tables and institution-specific rules and will
disagree with these numbers. Every conversion therefore carries a versioned
`rule_id` and is stored at tier `INFERENCE`, never `USER_STATED` — spec C1:
"Derived != stated, always."

Changing a formula requires a new `:vN` rule id, so an already-stored
derivation always remains attributable to the rule that produced it.
"""

from __future__ import annotations

from dataclasses import dataclass

US_4PT_MAX = 4.0


@dataclass(frozen=True)
class GpaScale:
    """One grading scale MS Buddy can accept and convert."""

    key: str
    label: str
    minimum: float
    maximum: float
    rule_id: str
    # Values at or below this are implausible for the scale and usually mean
    # the student (or the model) picked the wrong scale. Guards the named C1
    # failure case "a 72% becomes a 7.2/10".
    implausible_at_or_below: float | None
    implausible_hint: str | None

    def to_us_4pt(self, value: float) -> float:
        """Linear conversion of `value` on this scale to a US 4.0 equivalent."""
        return round(value / self.maximum * US_4PT_MAX, 2)


SCALES: dict[str, GpaScale] = {
    "pct_100": GpaScale(
        key="pct_100",
        label="Percentage (0-100)",
        minimum=0.0,
        maximum=100.0,
        rule_id="gpa_conv:pct_100_to_us_4pt:v1",
        implausible_at_or_below=10.0,
        implausible_hint=(
            "A percentage of 10 or below is unusual. If this is a CGPA on a "
            "10-point scale, the scale should be 'cgpa_10'."
        ),
    ),
    "cgpa_10": GpaScale(
        key="cgpa_10",
        label="CGPA out of 10",
        minimum=0.0,
        maximum=10.0,
        rule_id="gpa_conv:cgpa_10_to_us_4pt:v1",
        implausible_at_or_below=None,
        implausible_hint=None,
    ),
    "cgpa_5": GpaScale(
        key="cgpa_5",
        label="CGPA out of 5",
        minimum=0.0,
        maximum=5.0,
        rule_id="gpa_conv:cgpa_5_to_us_4pt:v1",
        implausible_at_or_below=None,
        implausible_hint=None,
    ),
    "cgpa_4": GpaScale(
        key="cgpa_4",
        label="CGPA out of 4",
        minimum=0.0,
        maximum=4.0,
        rule_id="gpa_conv:cgpa_4_identity:v1",
        implausible_at_or_below=None,
        implausible_hint=None,
    ),
    "gpa_4_us": GpaScale(
        key="gpa_4_us",
        label="US GPA out of 4.0",
        minimum=0.0,
        maximum=4.0,
        rule_id="gpa_conv:us_4pt_identity:v1",
        implausible_at_or_below=None,
        implausible_hint=None,
    ),
}

SCALE_KEYS: tuple[str, ...] = tuple(SCALES)

CONVERSION_CAVEAT = (
    "Linear approximation only. This is not a WES/ECE credential evaluation "
    "and universities may compute a different equivalent."
)


def convert_to_us_4pt(value: float, scale_key: str) -> dict:
    """Convert `value` on `scale_key` to a US 4.0 equivalent.

    Returns a result dict rather than raising, so callers (including tools)
    can surface a precise reason to the student.
    """
    scale = SCALES.get(scale_key)
    if scale is None:
        return {
            "status": "error",
            "reason": "unknown_scale",
            "message": (
                f"Unknown GPA scale '{scale_key}'. "
                f"Supported scales: {', '.join(SCALE_KEYS)}."
            ),
            "supported_scales": list(SCALE_KEYS),
        }

    if not scale.minimum <= value <= scale.maximum:
        return {
            "status": "error",
            "reason": "out_of_range",
            "message": (
                f"{value} is outside the valid range for "
                f"{scale.label} ({scale.minimum}-{scale.maximum}). "
                "Confirm the value and the scale with the student before retrying."
            ),
            "scale": scale.key,
            "valid_range": [scale.minimum, scale.maximum],
        }

    warnings: list[str] = []
    if (
        scale.implausible_at_or_below is not None
        and value <= scale.implausible_at_or_below
    ):
        warnings.append(scale.implausible_hint or "")

    return {
        "status": "success",
        "input_value": value,
        "input_scale": scale.key,
        "input_scale_label": scale.label,
        "us_4pt_equivalent": scale.to_us_4pt(value),
        "rule_id": scale.rule_id,
        "tier": "INFERENCE",
        "caveat": CONVERSION_CAVEAT,
        "warnings": warnings,
    }
