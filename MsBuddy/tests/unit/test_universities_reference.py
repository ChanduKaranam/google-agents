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

"""The curated university reference dataset.

Reference data in the same spirit as `gpa_scales.py`: a starting point for
discovery and comparison, never a source of current facts. The dataset's
contract is enforced here — most importantly the things it must NOT contain,
because a stored deadline or fee would rot into a confidently wrong answer.
Anything current still goes through C2's research-and-verify path.
"""

from __future__ import annotations

import re

from app.reference.universities import (
    COMPETITIVENESS_LEVELS,
    TYPICAL_DISCLAIMER,
    UNIVERSITIES,
)

REQUIRED_FIELDS = {
    "name",
    "country",
    "city",
    "programs",
    "competitiveness",
    "typical_gpa_4pt",
    "typical_ielts",
    "gre_policy",
    "intakes",
    "website",
}


def test_the_dataset_holds_roughly_twenty_universities() -> None:
    assert 18 <= len(UNIVERSITIES) <= 25


def test_every_entry_carries_every_field() -> None:
    for u in UNIVERSITIES:
        missing = REQUIRED_FIELDS - set(u)
        assert not missing, f"{u.get('name')} is missing {sorted(missing)}"


def test_names_are_unique() -> None:
    names = [u["name"] for u in UNIVERSITIES]
    assert len(names) == len(set(names))


def test_the_prompt_required_countries_are_covered() -> None:
    countries = {u["country"] for u in UNIVERSITIES}
    for wanted in ("USA", "Canada", "UK", "Germany", "Australia"):
        assert wanted in countries, f"no university for {wanted}"


def test_typical_values_are_sane() -> None:
    for u in UNIVERSITIES:
        assert 2.5 <= u["typical_gpa_4pt"] <= 4.0, u["name"]
        assert 5.5 <= u["typical_ielts"] <= 9.0, u["name"]
        assert u["competitiveness"] in COMPETITIVENESS_LEVELS, u["name"]
        assert u["programs"], u["name"]
        assert u["intakes"], u["name"]


def test_websites_are_https_and_official_looking() -> None:
    for u in UNIVERSITIES:
        assert u["website"].startswith("https://"), u["name"]
        assert "wikipedia" not in u["website"], u["name"]


def test_no_entry_stores_a_deadline_date_or_fee() -> None:
    """Dates and money rot. They are researched, never curated."""
    date_like = re.compile(
        r"\b(20\d\d|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\b",
        re.IGNORECASE,
    )
    money_like = re.compile(r"[$€£]|\b(usd|eur|gbp|tuition)\b", re.IGNORECASE)
    for u in UNIVERSITIES:
        rendered = str(sorted(u.items()))
        assert "deadline" not in rendered.lower(), u["name"]
        assert not money_like.search(rendered), u["name"]
        # Intake words like "fall" are fine; month names and years are not.
        assert not date_like.search(rendered), u["name"]


def test_no_entry_names_a_person() -> None:
    """Alumni stay behind the C4 verification gate. A curated alumni list
    would be exactly the unverified real-people claim the gate exists to
    prevent, so the dataset must not carry one."""
    for u in UNIVERSITIES:
        assert "alumni" not in str(sorted(u)).lower(), u["name"]


def test_the_disclaimer_says_typical_and_names_the_research_path() -> None:
    flat = " ".join(TYPICAL_DISCLAIMER.split()).lower()
    assert "typical" in flat
    assert "research" in flat
    assert "not" in flat  # ... not current/official
