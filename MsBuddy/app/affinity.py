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

"""Deterministic alumni affinity (C4, Stage F).

"Is anyone like me?" is answerable without a similarity model, because the
thing being asked is **overlap between evidenced anchors**, and overlap is
countable. Same split as Phase 3: Python decides the order, the model
explains it.

**No composite score.** Architecture §12 is explicit, and the reason is
practical rather than aesthetic: a single number would hide *which* anchor
matched, and the matched anchor is the part a student can act on. "Someone
from your university did this program" is useful. "Affinity 0.72" is not.

**Ties stay tied.** Competition ranking — `1, 1, 3` — exactly as
`app.scoring` does it. Two people with one shared anchor each are equally
relevant, and inventing an order between them would be asserting something
no evidence supports.

**Ranking never filters.** Someone who shares nothing with the student is
still a real alumnus of the program they are evaluating, and dropping them
would make the result look more relevant than it is.

**No anchor may rest on an inference** (§12). The alumni side must be
`VERIFIED` or `REPORTED` — a value that was itself derived cannot then
support a second derivation. Affinity is the *only* legitimate `INFERENCE`
in C4 (§8), and it stays confined to this module's output: nothing here is
ever written back onto a person's record.

Pure Python — no ADK, no network, no model, no state. The same AST
import-graph test as Phase 3 holds it that way.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from app.reference.source_authority import (
    PRIOR_DEGREE,
    PRIOR_INSTITUTION,
    PROGRAM,
)

VERSION = "affinity:v1"

# An anchor may only rest on a claim some source actually stated.
EVIDENCED_TIERS: frozenset[str] = frozenset({"VERIFIED", "REPORTED"})

_NON_ALPHANUMERIC = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class AnchorSpec:
    """One thing a student and an alumnus can demonstrably have in common."""

    key: str
    profile_field: str
    alumni_field: str
    label: str


# Three anchors, not four. Architecture §12 also lists "same target country",
# which needs the university's country — a fact no alumni record holds and no
# source is asked for. An anchor that can never match is worse than a missing
# one, because it reads as coverage. Listed as a post-demo item instead.
#
# `citizenship` is deliberately absent and a test pins it: it is a protected
# attribute, and matching on it would be a discriminatory filter wearing an
# affinity label.
ANCHORS: tuple[AnchorSpec, ...] = (
    AnchorSpec(
        key="undergrad_institution",
        profile_field="undergrad_institution",
        alumni_field=PRIOR_INSTITUTION,
        label="same undergraduate institution",
    ),
    AnchorSpec(
        key="undergrad_field",
        profile_field="undergrad_degree",
        alumni_field=PRIOR_DEGREE,
        label="same undergraduate field",
    ),
    AnchorSpec(
        key="specialization",
        profile_field="specialization_interest",
        alumni_field=PROGRAM,
        label="same specialization",
    ),
)

ANCHOR_KEYS: tuple[str, ...] = tuple(a.key for a in ANCHORS)


def _normalize(text: str) -> str:
    """Case, whitespace, punctuation and diacritics folded away.

    Same three transformations `app.identity.normalize_name` applies, and for
    the same reason — they remove differences in *rendering*, never in
    content. Written out here rather than imported because that function is
    about names and this one is about institutions and programs; sharing it
    would tie two unrelated rules together.
    """
    decomposed = unicodedata.normalize("NFKD", str(text or ""))
    folded = "".join(ch for ch in decomposed if not unicodedata.combining(ch)).lower()
    return " ".join(_NON_ALPHANUMERIC.sub(" ", folded).split())


def _is_contiguous_sublist(needle: list[str], haystack: list[str]) -> bool:
    if not needle or len(needle) > len(haystack):
        return False
    return any(
        haystack[i : i + len(needle)] == needle
        for i in range(len(haystack) - len(needle) + 1)
    )


def values_match(student_value: str, alumni_value: str) -> bool:
    """True if two anchor values describe the same thing.

    Equality after normalization, or one being a whole-token run inside the
    other. The second case is what makes the specialization anchor work at
    all: a student's `Computer Science` has to meet a program published as
    `MSc Computer Science`, and exact equality would miss every real match.

    Token-run containment rather than substring containment, so `art` cannot
    match `smart systems`. It is still the loosest rule here, which is
    acceptable because an affinity match is a *ranking* signal shown with its
    rationale — never a stored fact about the person.
    """
    student = _normalize(student_value).split()
    alumni = _normalize(alumni_value).split()
    if not student or not alumni:
        return False
    if student == alumni:
        return True
    return _is_contiguous_sublist(student, alumni) or _is_contiguous_sublist(
        alumni, student
    )


def anchor_values_from_profile(profile: dict[str, Any]) -> dict[str, str]:
    """The student's side of each anchor, and nothing else about them.

    Reads only the fields an anchor names. That narrowness is the privacy
    control: this function is the whole interface between the student's
    profile and the alumni path, so nothing else can leak into it.
    """
    fields = profile.get("fields") or {}
    values: dict[str, str] = {}
    for anchor in ANCHORS:
        entry = fields.get(anchor.profile_field)
        if not isinstance(entry, dict):
            continue
        text = str(entry.get("value") or "").strip()
        if text:
            values[anchor.key] = text
    return values


def matched_anchors(
    student_values: dict[str, str], person: dict[str, Any]
) -> list[dict[str, Any]]:
    """Every anchor this person demonstrably shares with the student.

    `person` is a record in the shape `alumni_store.render_person` produces.
    Each match carries both values and a rationale string, because the
    rationale is what the student is actually told.
    """
    fields = person.get("fields") or {}
    matches: list[dict[str, Any]] = []

    for anchor in ANCHORS:
        student_value = student_values.get(anchor.key)
        if not student_value:
            continue

        entry = fields.get(anchor.alumni_field)
        if not isinstance(entry, dict):
            continue
        if str(entry.get("tier")) not in EVIDENCED_TIERS:
            continue

        alumni_value = str(entry.get("value") or "")
        if not values_match(student_value, alumni_value):
            continue

        matches.append(
            {
                "anchor": anchor.key,
                "label": anchor.label,
                "student_value": student_value,
                "alumni_value": alumni_value,
                "tier": entry.get("tier"),
                "source_domain": (entry.get("source_domain")),
                "rationale": (
                    f"{anchor.label} ({alumni_value})"
                    if _normalize(student_value) == _normalize(alumni_value)
                    else f"{anchor.label} — you: {student_value}; them: {alumni_value}"
                ),
            }
        )

    return matches


def rank_people(
    people: list[dict[str, Any]], student_values: dict[str, str]
) -> list[dict[str, Any]]:
    """Order rendered alumni by how many anchors they share with the student.

    Returns copies with `matched_anchors`, `match_count` and `rank` added.
    The inputs are not mutated — the ranking is a view over the store, never
    an edit to it.

    Order within a tie is by `record_id`, which is derived from the identity
    key and therefore stable. That is a *presentation* order for a group the
    ranking itself declares equal, not a tiebreak: every member of the group
    carries the same `rank`.
    """
    ranked = []
    for original in people:
        person = dict(original)
        matches = matched_anchors(student_values, original)
        person["matched_anchors"] = matches
        person["match_count"] = len(matches)
        ranked.append(person)

    ranked.sort(key=lambda p: (-p["match_count"], str(p.get("record_id") or "")))

    for index, person in enumerate(ranked):
        if index and person["match_count"] == ranked[index - 1]["match_count"]:
            person["rank"] = ranked[index - 1]["rank"]  # competition ranking: 1, 1, 3
        else:
            person["rank"] = index + 1

    return ranked


def describe_anchors() -> list[dict[str, str]]:
    """The anchor catalogue, for a caller that needs to explain the ranking."""
    return [
        {
            "anchor": a.key,
            "label": a.label,
            "student_field": a.profile_field,
            "alumni_field": a.alumni_field,
        }
        for a in ANCHORS
    ]
