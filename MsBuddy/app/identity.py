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

"""Deterministic identity for alumni records (C4, Stage 0 §6).

The `John Smith at University A` versus `John Smith at University B` problem,
solved by refusing to be clever about it.

```
identity_key = slug(normalized_name) @ slug(university)
```

**A name is never an identity.** The university anchor is mandatory, and
without one no key is produced at all — no anchor, no identity, no record.

**Normalization does three things and stops:** case folding, whitespace
collapse, and diacritic folding. Explicitly *not* nickname expansion
(Bob ↔ Robert), initial matching (J. Smith ↔ John Smith), phonetic matching,
or edit distance. Every one of those manufactures false merges, and a false
merge is a fabricated person — one record wearing two people's facts.

**The bias is deliberate and asymmetric:**

> Two records for one person is a cosmetic flaw the student can see and
> resolve. One record fusing two people is a fabricated human they cannot
> detect.

So this module prefers false negatives, always. There is no confidence
score: a number would hide which evidence was thin, and the whole point is
that ambiguity stays visible.

Pure Python — no ADK, no network, no model. Merge *rules* live with storage
in Stage B; this module only decides what a key is and when there isn't one.
"""

from __future__ import annotations

import re
import unicodedata

VERSION = "identity:v1"

_NON_ALPHANUMERIC = re.compile(r"[^a-z0-9]+")
_WHITESPACE = re.compile(r"\s+")

# A key needs something to work with. One character is not a name.
MIN_NAME_LENGTH = 2
MIN_UNIVERSITY_LENGTH = 2
MAX_KEY_LENGTH = 160


def fold_diacritics(text: str) -> str:
    """Strip accents while preserving the letters underneath.

    `José Álvarez` and `Jose Alvarez` are the same name written two ways, and
    treating them as different people would fragment a real person's record
    for no reason. This is the one normalization that removes a *rendering*
    difference rather than a *content* difference, which is why it is safe.
    """
    decomposed = unicodedata.normalize("NFKD", text or "")
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def normalize_name(name: str) -> str:
    """Case, whitespace and diacritics only. Nothing clever.

    Punctuation becomes a space, so `Jean-Luc` and `Jean Luc` agree, and
    `J. Smith` normalizes to `j smith` — which deliberately does **not**
    match `john smith`. That non-match is the feature.
    """
    folded = fold_diacritics(str(name or "")).lower()
    spaced = _NON_ALPHANUMERIC.sub(" ", folded)
    return _WHITESPACE.sub(" ", spaced).strip()


def slug(text: str) -> str:
    """Lower-case, punctuation-free token suitable for a key component."""
    folded = fold_diacritics(str(text or "")).lower()
    return _NON_ALPHANUMERIC.sub("-", folded).strip("-")


def name_tokens(name: str) -> list[str]:
    """The normalized parts of a name, in order."""
    normalized = normalize_name(name)
    return normalized.split(" ") if normalized else []


def is_initial_form(name: str) -> bool:
    """True if any part of `name` is a bare initial, e.g. `J. Smith`.

    Not used to match anything — used to *refuse* to. A record whose name is
    an initial form cannot be merged into a fuller name, because `J. Smith`
    is equally consistent with John, Jane and Jamal.
    """
    tokens = name_tokens(name)
    if len(tokens) < 2:
        return False
    return any(len(token) == 1 for token in tokens[:-1])


def names_are_equivalent(left: str, right: str) -> bool:
    """True only when two names normalize identically.

    Strict equality by design. `Bob Smith` is not `Robert Smith`, and
    `J. Smith` is not `John Smith`, however likely it may seem.
    """
    normalized = normalize_name(left)
    return bool(normalized) and normalized == normalize_name(right)


def make_identity_key(name: str, university: str) -> str | None:
    """Build the composite identity key, or `None` if it cannot be built.

    `None` is a real answer and callers must handle it: a person with no
    institutional anchor is not a person this system can identify, and
    storing them keyed on a bare name would invite exactly the merge this
    design exists to prevent.
    """
    name_slug = slug(normalize_name(name))
    university_slug = slug(university)

    if len(name_slug.replace("-", "")) < MIN_NAME_LENGTH:
        return None
    if len(university_slug.replace("-", "")) < MIN_UNIVERSITY_LENGTH:
        return None

    return f"{name_slug}@{university_slug}"[:MAX_KEY_LENGTH]


def describe_identity(name: str, university: str) -> dict[str, object]:
    """The key plus the reasoning behind it.

    Returned rather than just the key so that a reader — or a test, or a
    student asking why two people were not merged — can see the inputs the
    decision rested on. An opaque identifier would hide exactly that.
    """
    key = make_identity_key(name, university)
    return {
        "identity_key": key,
        "normalized_name": normalize_name(name),
        "normalized_university": slug(university),
        "is_initial_form": is_initial_form(name),
        "resolvable": key is not None,
        "reason": None
        if key is not None
        else "an identity needs both a usable name and an institution anchor",
        "ruleset": VERSION,
    }
