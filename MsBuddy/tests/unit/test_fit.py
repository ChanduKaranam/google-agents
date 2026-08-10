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

"""Deterministic profile-fit assessment.

Same philosophy as `app.scoring` and `app.affinity`: Python decides, the
model narrates. The output is a *fit band* with named factors — never a
probability, never a promise, and never a number that could be read as an
admission chance. That last rule is load-bearing: "78% match" is one
paraphrase away from "78% chance of admission", so no percentage exists
anywhere in the result.
"""

from __future__ import annotations

import pytest

from app.fit import FIT_BANDS, assess_fit

CMU = {
    "name": "Carnegie Mellon University",
    "country": "USA",
    "city": "Pittsburgh",
    "programs": ["Computer Science", "Software Engineering"],
    "competitiveness": "highly_competitive",
    "typical_gpa_4pt": 3.7,
    "typical_ielts": 7.0,
    "gre_policy": "varies_by_program",
    "intakes": ["fall"],
    "website": "https://www.cmu.edu",
}

ASU = {
    **CMU,
    "name": "Arizona State University",
    "competitiveness": "moderately_competitive",
    "typical_gpa_4pt": 3.0,
    "typical_ielts": 6.5,
}


def profile(**overrides) -> dict:
    base = {
        "gpa_value": 8.1,
        "gpa_scale": "cgpa_10",
        "ielts_overall": 7.0,
        "specialization_interest": "Computer Science",
    }
    base.update(overrides)
    return base


def test_bands_are_the_four_the_product_promises() -> None:
    assert FIT_BANDS == ("strong", "good", "moderate", "ambitious")


def test_a_strong_profile_at_an_accessible_university_is_strong() -> None:
    result = assess_fit(profile(), ASU)
    assert result["status"] == "success"
    assert result["band"] == "strong"


def test_the_same_profile_at_a_highly_competitive_school_is_weaker() -> None:
    """Competitiveness shifts the band down one step — 3.24 against a 3.7
    typical lands 'ambitious', and the tier keeps it honest."""
    result = assess_fit(profile(), CMU)
    assert result["band"] == "ambitious"


def test_assessment_is_deterministic() -> None:
    assert assess_fit(profile(), CMU) == assess_fit(profile(), CMU)


def test_every_factor_is_named_and_transparent() -> None:
    result = assess_fit(profile(), ASU)
    factors = {f["factor"]: f for f in result["factors"]}
    assert "gpa" in factors
    assert "english" in factors
    assert "program_alignment" in factors
    gpa = factors["gpa"]
    assert gpa["student_value"] == pytest.approx(3.24, abs=0.01)
    assert gpa["typical_value"] == 3.0
    assert gpa["verdict"]


def test_no_percentage_and_no_admission_language_anywhere() -> None:
    for university in (CMU, ASU):
        rendered = str(assess_fit(profile(), university)).lower()
        assert "%" not in rendered
        assert "chance" not in rendered
        assert "probability" not in rendered
        assert "admission is" not in rendered


def test_the_result_says_it_is_not_an_admission_estimate() -> None:
    result = assess_fit(profile(), ASU)
    assert result["not_an_admission_estimate"] is True


def test_a_missing_gpa_asks_rather_than_guesses() -> None:
    result = assess_fit(profile(gpa_value=None), CMU)
    assert result["status"] == "error"
    assert result["reason"] == "gpa_missing"


def test_a_missing_english_score_is_reported_not_scored() -> None:
    result = assess_fit(profile(ielts_overall=None), ASU)
    factors = {f["factor"]: f for f in result["factors"]}
    assert factors["english"]["verdict"] == "unknown"
    # A missing score is a gap to mention, never a downgrade.
    assert result["band"] == "strong"


def test_a_weak_english_score_shifts_the_band_down() -> None:
    ok = assess_fit(profile(), ASU)["band"]
    weak = assess_fit(profile(ielts_overall=5.5), ASU)["band"]
    assert FIT_BANDS.index(weak) > FIT_BANDS.index(ok)


def test_program_alignment_is_matched_case_insensitively() -> None:
    result = assess_fit(profile(specialization_interest="computer science"), CMU)
    factors = {f["factor"]: f for f in result["factors"]}
    assert factors["program_alignment"]["verdict"] == "aligned"


def test_citizenship_is_never_read() -> None:
    """A protected attribute must not influence fit, even if present."""
    with_it = assess_fit(profile(citizenship="India"), CMU)
    without = assess_fit(profile(), CMU)
    assert with_it == without
    assert "citizenship" not in str(with_it).lower()
