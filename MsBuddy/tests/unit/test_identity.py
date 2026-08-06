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

"""Deterministic alumni identity (C4 Stage A).

Most of these assert a **non**-match. That is the point: a false merge is
one record wearing two people's facts, which is a fabricated human the
student has no way to detect.
"""

from __future__ import annotations

import pytest

from app.identity import (
    describe_identity,
    is_initial_form,
    make_identity_key,
    name_tokens,
    names_are_equivalent,
    normalize_name,
    slug,
)

DELFT = "TU Delft"

# --- Normalization does three things and stops -----------------------------


def test_case_and_whitespace_are_normalized() -> None:
    assert normalize_name("  JOHN   Smith ") == "john smith"


def test_diacritics_are_folded() -> None:
    """Two spellings of one name should not fragment a real person's record."""
    assert normalize_name("José Álvarez") == normalize_name("Jose Alvarez")
    assert normalize_name("Renée Müller") == "renee muller"


def test_punctuation_becomes_a_space() -> None:
    assert normalize_name("Jean-Luc Picard") == "jean luc picard"
    assert normalize_name("O'Brien") == "o brien"


def test_normalization_survives_empty_and_junk_input() -> None:
    assert normalize_name("") == ""
    assert normalize_name("   ") == ""
    assert normalize_name("!!!") == ""


def test_name_tokens_preserve_order() -> None:
    assert name_tokens("Ada Byron Lovelace") == ["ada", "byron", "lovelace"]
    assert name_tokens("") == []


# --- The merges that must never happen -------------------------------------


def test_a_nickname_is_not_the_same_name() -> None:
    """Bob and Robert are two people until a source says otherwise."""
    assert names_are_equivalent("Bob Smith", "Robert Smith") is False
    assert make_identity_key("Bob Smith", DELFT) != make_identity_key(
        "Robert Smith", DELFT
    )


def test_an_initial_is_not_a_first_name() -> None:
    """`J. Smith` is equally consistent with John, Jane and Jamal."""
    assert names_are_equivalent("J. Smith", "John Smith") is False
    assert make_identity_key("J. Smith", DELFT) != make_identity_key(
        "John Smith", DELFT
    )


def test_initial_forms_are_detectable_so_they_can_be_refused() -> None:
    assert is_initial_form("J. Smith") is True
    assert is_initial_form("J Smith") is True
    assert is_initial_form("John Smith") is False
    assert is_initial_form("Madonna") is False


def test_a_similar_name_is_not_the_same_name() -> None:
    """No edit distance, no phonetics."""
    assert names_are_equivalent("Jon Smith", "John Smith") is False
    assert names_are_equivalent("Smith John", "John Smith") is False


def test_the_same_name_at_two_universities_gets_two_keys() -> None:
    """The case this whole module exists for."""
    a = make_identity_key("John Smith", "University A")
    b = make_identity_key("John Smith", "University B")
    assert a is not None and b is not None
    assert a != b


# --- The merges that should happen -----------------------------------------


def test_the_same_person_written_differently_gets_one_key() -> None:
    assert make_identity_key("  josé álvarez ", DELFT) == make_identity_key(
        "Jose Alvarez", DELFT
    )


def test_university_spelling_variance_is_folded() -> None:
    assert make_identity_key("Ada Lovelace", "TU Delft") == make_identity_key(
        "Ada Lovelace", "tu-delft"
    )


def test_equivalence_is_reflexive_and_symmetric() -> None:
    assert names_are_equivalent("Ada Lovelace", "ada  lovelace") is True
    assert names_are_equivalent("ada lovelace", "Ada Lovelace") is True


def test_an_empty_name_is_equivalent_to_nothing() -> None:
    assert names_are_equivalent("", "") is False


# --- No anchor, no identity ------------------------------------------------


def test_a_person_with_no_university_has_no_key() -> None:
    """Storing them keyed on a bare name is how namesakes get merged."""
    assert make_identity_key("John Smith", "") is None
    assert make_identity_key("John Smith", "   ") is None


def test_a_person_with_no_usable_name_has_no_key() -> None:
    assert make_identity_key("", DELFT) is None
    assert make_identity_key("!!!", DELFT) is None
    assert make_identity_key("J", DELFT) is None


def test_a_mononym_still_resolves() -> None:
    """Not everyone has two names; the university remains the anchor."""
    assert make_identity_key("Madonna", DELFT) is not None


# --- Key shape and stability -----------------------------------------------


def test_the_key_is_readable_rather_than_opaque() -> None:
    """A student asking 'why are these two separate?' deserves an answer."""
    assert make_identity_key("Ada Lovelace", DELFT) == "ada-lovelace@tu-delft"


def test_the_key_is_stable_across_repeated_calls() -> None:
    keys = {make_identity_key("Ada Lovelace", DELFT) for _ in range(100)}
    assert len(keys) == 1


def test_the_key_is_bounded() -> None:
    key = make_identity_key("A" * 500, "B" * 500)
    assert key is not None
    assert len(key) <= 160


def test_slug_is_url_safe() -> None:
    assert slug("TU Delft (NL)") == "tu-delft-nl"
    assert slug("") == ""


# --- The explanation, not just the answer ----------------------------------


def test_describe_identity_shows_its_working() -> None:
    described = describe_identity("José Álvarez", DELFT)
    assert described["identity_key"] == "jose-alvarez@tu-delft"
    assert described["normalized_name"] == "jose alvarez"
    assert described["normalized_university"] == "tu-delft"
    assert described["resolvable"] is True
    assert described["reason"] is None
    assert described["ruleset"]


def test_describe_identity_explains_an_unresolvable_person() -> None:
    described = describe_identity("John Smith", "")
    assert described["resolvable"] is False
    assert described["identity_key"] is None
    assert "institution anchor" in str(described["reason"])


def test_describe_identity_flags_an_initial_form() -> None:
    assert describe_identity("J. Smith", DELFT)["is_initial_form"] is True


# --- No confidence score anywhere ------------------------------------------


def test_identity_never_produces_a_numeric_confidence() -> None:
    """A number would hide which evidence was thin; ambiguity stays visible."""
    described = describe_identity("Ada Lovelace", DELFT)
    for value in described.values():
        assert not isinstance(value, float), described


@pytest.mark.parametrize(
    ("name", "university"),
    [
        ("Ada Lovelace", "TU Delft"),
        ("José Álvarez", "ETH Zürich"),
        ("Jean-Luc Picard", "Starfleet Academy"),
    ],
)
def test_keys_round_trip_deterministically(name: str, university: str) -> None:
    first = make_identity_key(name, university)
    assert first == make_identity_key(name, university)
    assert first == describe_identity(name, university)["identity_key"]
