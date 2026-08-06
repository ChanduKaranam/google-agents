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

"""GPA conversion — deterministic, so this is pytest territory (spec §11.1)."""

from __future__ import annotations

import pytest

from app.reference.gpa_scales import SCALE_KEYS, SCALES, convert_to_us_4pt


@pytest.mark.parametrize(
    ("value", "scale", "expected"),
    [
        (8.1, "cgpa_10", 3.24),
        (10.0, "cgpa_10", 4.0),
        (0.0, "cgpa_10", 0.0),
        (72.0, "pct_100", 2.88),
        (100.0, "pct_100", 4.0),
        (4.5, "cgpa_5", 3.6),
        (3.7, "cgpa_4", 3.7),
        (3.7, "gpa_4_us", 3.7),
    ],
)
def test_conversion_values(value: float, scale: str, expected: float) -> None:
    result = convert_to_us_4pt(value, scale)
    assert result["status"] == "success"
    assert result["us_4pt_equivalent"] == pytest.approx(expected)


def test_conversion_is_always_inference_with_a_rule_id() -> None:
    """Derived != stated (spec C1): every conversion is attributable."""
    for scale in SCALE_KEYS:
        result = convert_to_us_4pt(SCALES[scale].maximum / 2, scale)
        assert result["tier"] == "INFERENCE"
        assert result["rule_id"].startswith("gpa_conv:")
        assert result["rule_id"].endswith(":v1")
        assert result["caveat"]


def test_unknown_scale_is_rejected_not_guessed() -> None:
    result = convert_to_us_4pt(8.1, "cgpa_9")
    assert result["status"] == "error"
    assert result["reason"] == "unknown_scale"
    assert "cgpa_10" in result["supported_scales"]


@pytest.mark.parametrize(
    ("value", "scale"),
    [
        (72.0, "cgpa_10"),  # the named C1 failure case, caught by range
        (10.5, "cgpa_10"),
        (101.0, "pct_100"),
        (-1.0, "pct_100"),
        (4.5, "cgpa_4"),
    ],
)
def test_out_of_range_values_are_rejected(value: float, scale: str) -> None:
    """A value impossible on its stated scale must never be converted."""
    result = convert_to_us_4pt(value, scale)
    assert result["status"] == "error"
    assert result["reason"] == "out_of_range"


def test_inverse_scale_confusion_is_flagged() -> None:
    """7.2 stated as a percentage is legal but almost certainly a mix-up."""
    result = convert_to_us_4pt(7.2, "pct_100")
    assert result["status"] == "success"
    assert result["warnings"]
    assert "cgpa_10" in result["warnings"][0]


def test_plausible_percentage_is_not_flagged() -> None:
    result = convert_to_us_4pt(72.0, "pct_100")
    assert result["status"] == "success"
    assert result["warnings"] == []
