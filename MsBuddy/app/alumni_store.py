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

"""Deterministic alumni storage (C4, Stage B).

Mirrors `program_store`: pure Python over plain dicts, read-copy-write
against ADK state, no LLM and no network. The claim shape — every source
retained, conflicts kept, preferred value chosen by rank — is C2's, because
the Phase 2 audit already proved that shape works and that discarding a
weaker source loses real information.

Three things differ, and each exists because the subject is a person.

**The tier is derived here, never supplied.** C2's `apply_claim` accepts
`evidence["tier"]` from its caller. This module refuses to: the tier comes
from `authority_for(source_class, field)` and nothing else. A caller —
including one relaying a model's proposal — cannot assert that a claim is
`VERIFIED`. That is the difference between a storage layer and a filing
cabinet.

**A person must be originated.** Only a source class with standing may bring
someone into existence (Stage 0 §5). A search snippet may corroborate a
person who already exists; it cannot mint one.

**Ambiguity splits rather than merges.** When a second record shares an
identity key but contradicts it on a discriminating field, the two are kept
apart and cross-linked as possible namesakes. Two records for one person is
a cosmetic flaw the student can see; one record fusing two people is a
fabricated human they cannot detect.

Nothing in this module reasons. Every decision is a table lookup or a string
comparison, which is what makes "the LLM is never the authority for whether
an alumnus exists" checkable rather than promised.
"""

from __future__ import annotations

import copy
from typing import Any

from app.config import MIN_PATTERN_N, PROFILE_SCHEMA_VERSION
from app.evidence import evaluate_staleness, now_utc
from app.identity import make_identity_key, normalize_name
from app.reference.alumni_fields import (
    ALL_FIELD_NAMES,
    is_prohibited_field,
    is_writable,
    staleness_class_for,
    validate_alumni_value,
)
from app.reference.source_authority import (
    EMPLOYER,
    GRADUATION_YEAR,
    PROGRAM,
    REFUSE,
    UNIVERSITY_AFFILIATION,
    VERIFY,
    authority_for,
    can_corroborate,
    can_originate,
)

VERSION = "alumni_store:v1"

# Fields on which a disagreement means "probably not the same person" rather
# than "one of these sources is out of date". Someone's employer changes;
# the year they graduated and the program they took do not.
DISCRIMINATING_FIELDS: tuple[str, ...] = (GRADUATION_YEAR, PROGRAM)

# Same ordering as C2: standing first, then recency. A weaker source never
# displaces a stronger one, and never disappears either.
_TIER_RANK = {"VERIFIED": 2, "REPORTED": 1}

URL_NOT_ATTEMPTED = "not_attempted"
URL_RESOLVED = "resolved"
URL_UNRESOLVED = "url_unresolved"


def now_iso() -> str:
    """Current UTC time as an ISO-8601 string."""
    return now_utc().isoformat(timespec="seconds")


# --- State -----------------------------------------------------------------


def empty_alumni_store() -> dict[str, Any]:
    """A fresh, empty alumni store.

    Empty is a valid, successful state — a program with no publicly
    discoverable alumni is a real answer, not an error.
    """
    stamp = now_iso()
    return {
        "schema_version": PROFILE_SCHEMA_VERSION,
        "created_at": stamp,
        "updated_at": stamp,
        "people": {},
    }


def read_alumni_store(state: Any, key: str) -> dict[str, Any]:
    """Return a mutable deep copy of the stored alumni directory."""
    stored = state.get(key)
    if not isinstance(stored, dict) or "people" not in stored:
        return empty_alumni_store()
    return copy.deepcopy(stored)


def write_alumni_store(state: Any, key: str, store: dict[str, Any]) -> None:
    """Persist `store`, stamping `updated_at`."""
    store["updated_at"] = now_iso()
    state[key] = store


# --- Evidence --------------------------------------------------------------


def make_alumni_evidence(
    source_domain: str,
    source_class: str,
    supporting_quote: str,
    field_name: str,
    source_url: str | None = None,
    resolved_url: str | None = None,
    url_resolution_status: str = URL_NOT_ATTEMPTED,
    retrieved_at: str | None = None,
) -> dict[str, Any]:
    """Build the provenance record carried with one alumni claim.

    `source_url` is the grounding redirect; `resolved_url` is the publisher
    URL if Stage C managed to resolve it. Both are kept, and the status says
    which is which, so a reader is never misled about what they are
    clicking.
    """
    return {
        "source_domain": source_domain,
        "source_class": source_class,
        "source_url": source_url,
        "resolved_url": resolved_url,
        "url_resolution_status": url_resolution_status,
        "supporting_quote": supporting_quote,
        "retrieved_at": retrieved_at or now_iso(),
        "staleness_class": staleness_class_for(field_name),
        "authority": authority_for(source_class, field_name),
        "ruleset": VERSION,
    }


def tier_for(source_class: str, field_name: str) -> str | None:
    """The tier this source may claim for this field, or `None` if it may not.

    Derived, never accepted from a caller. This single function is why a
    model cannot talk its way into a `VERIFIED` fact about a person.
    """
    verdict = authority_for(source_class, field_name)
    if verdict == VERIFY:
        return "VERIFIED"
    if verdict == REFUSE:
        return None
    return "REPORTED"


def _rank(entry: dict[str, Any]) -> tuple[int, str]:
    """Sort key: tier first, then recency."""
    return (
        _TIER_RANK.get(str(entry.get("tier")), 0),
        str(entry.get("evidence", {}).get("retrieved_at") or ""),
    )


# --- Records ---------------------------------------------------------------


def _new_record(
    record_id: str,
    identity_key: str,
    name: str,
    university: str,
    originated_by: str,
) -> dict[str, Any]:
    return {
        "record_id": record_id,
        "identity_key": identity_key,
        "name_as_published": name.strip(),
        "university": university.strip(),
        "first_seen_at": now_iso(),
        "originated_by": originated_by,
        "fields": {},
        "possible_namesakes": [],
    }


def records_for(store: dict[str, Any], identity_key: str) -> list[dict[str, Any]]:
    """Every record sharing an identity key, in stable order."""
    people = store.get("people") or {}
    return [
        people[rid]
        for rid in sorted(people)
        if people[rid].get("identity_key") == identity_key
    ]


def _discriminators(claims: list[dict[str, Any]]) -> dict[str, str]:
    """The incoming values for fields that distinguish one person from another."""
    found: dict[str, str] = {}
    for claim in claims:
        name = str(claim.get("field_name") or "")
        if name in DISCRIMINATING_FIELDS and name not in found:
            found[name] = str(claim.get("value") or "").strip().casefold()
    return found


def is_compatible(record: dict[str, Any], discriminators: dict[str, str]) -> bool:
    """True if `discriminators` do not contradict what `record` already holds.

    Absence never contradicts: a record with no stored graduation year is
    compatible with any year. Only two *present* and *different* values mean
    these are probably two people.
    """
    fields = record.get("fields") or {}
    for name, incoming in discriminators.items():
        stored = fields.get(name)
        if not isinstance(stored, dict):
            continue
        existing = str(stored.get("value") or "").strip().casefold()
        if existing and incoming and existing != incoming:
            return False
    return True


def resolve_record(
    store: dict[str, Any],
    identity_key: str,
    name: str,
    university: str,
    originating_class: str,
    discriminators: dict[str, str],
) -> tuple[dict[str, Any], bool]:
    """Find the record this candidate belongs to, or start a new one.

    Returns `(record, is_namesake_split)`. A split happens when records
    already exist under this identity key but every one of them contradicts
    the incoming discriminators — which is the `John Smith / John Smith`
    case, and the moment where merging would fabricate a person.
    """
    existing = records_for(store, identity_key)
    for record in existing:
        if is_compatible(record, discriminators):
            return record, False

    people = store.setdefault("people", {})
    suffix = len(existing) + 1
    record_id = identity_key if suffix == 1 else f"{identity_key}#{suffix}"
    record = _new_record(record_id, identity_key, name, university, originating_class)
    people[record_id] = record

    # Cross-link, so neither record can be read without the ambiguity being
    # visible. The student is told these may be two people; nothing guesses.
    for other in existing:
        other.setdefault("possible_namesakes", [])
        if record_id not in other["possible_namesakes"]:
            other["possible_namesakes"].append(record_id)
        if other["record_id"] not in record["possible_namesakes"]:
            record["possible_namesakes"].append(other["record_id"])

    return record, bool(existing)


def apply_alumni_claim(
    record: dict[str, Any],
    field_name: str,
    value: str,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    """Store one already-authorised claim, keeping every source.

    The caller is responsible for having checked authority; `admit_candidate`
    is the supported entry point and does that. Kept separate so the
    multi-source merge can be tested on its own.
    """
    tier = tier_for(str(evidence.get("source_class")), field_name)
    if tier is None:
        raise ValueError(
            f"{evidence.get('source_class')} has no standing for '{field_name}'"
        )

    fields = record.setdefault("fields", {})
    existing = fields.get(field_name)

    sources: list[dict[str, Any]] = []
    if isinstance(existing, dict):
        sources = list(existing.get("sources") or [])

    domain = evidence.get("source_domain")
    # Restating the same value from the same source refreshes it rather than
    # accumulating duplicates.
    sources = [
        s
        for s in sources
        if not (
            s.get("value") == value
            and s.get("evidence", {}).get("source_domain") == domain
        )
    ]
    sources.append({"value": value, "tier": tier, "evidence": evidence})

    preferred = max(sources, key=_rank)
    conflicts = [s for s in sources if s["value"] != preferred["value"]]
    corroborations = [
        s for s in sources if s["value"] == preferred["value"] and s is not preferred
    ]

    fields[field_name] = {
        "value": preferred["value"],
        "tier": preferred["tier"],
        "evidence": preferred["evidence"],
        "sources": sources,
        "conflicts": conflicts,
        "corroborations": corroborations,
    }

    return {
        "field": field_name,
        "value": preferred["value"],
        "tier": preferred["tier"],
        "accepted_value": value,
        "preferred_source": preferred["evidence"].get("source_domain"),
        "source_count": len(sources),
        "corroborated_by": [s["evidence"].get("source_domain") for s in corroborations],
        "conflict_with": [s["value"] for s in conflicts],
    }


# --- Admission -------------------------------------------------------------


def _reject(field: str, reason: str, message: str) -> dict[str, Any]:
    return {"field": field, "reason": reason, "message": message}


def admit_candidate(
    store: dict[str, Any],
    name: str,
    university: str,
    claims: list[dict[str, Any]],
) -> dict[str, Any]:
    """Admit a proposed person into storage, or refuse with reasons.

    `claims` are dicts of `field_name`, `value`, `evidence` — where
    `evidence` came from `make_alumni_evidence`. Every claim is re-validated
    here regardless of what any earlier layer concluded.

    The order of the checks is the safety model:

    1. an identity must be resolvable at all (name + institution anchor);
    2. some source must have standing to *originate* a person;
    3. someone must actually claim this person attended this institution;
    4. each individual claim must survive field, value, privacy and
       authority checks.

    A person who fails 1-3 is not stored at all. A person who passes them
    keeps whichever claims survive 4, with the rest named as unknown.
    """
    identity_key = make_identity_key(name, university)
    if identity_key is None:
        return {
            "status": "error",
            "reason": "identity_unresolvable",
            "message": (
                "A person needs both a usable name and an institution to be "
                "identified. Without an anchor there is no way to tell two "
                "people with the same name apart, so nothing is stored."
            ),
            "saved": [],
            "rejected": [],
        }

    usable = [c for c in claims if isinstance(c, dict)]

    originating = [
        c
        for c in usable
        if can_originate(str((c.get("evidence") or {}).get("source_class")))
    ]
    if not originating:
        return {
            "status": "error",
            "reason": "source_cannot_originate",
            "message": (
                "No source with standing to establish a person was supplied. "
                "Aggregators, snippets and self-published pages may agree "
                "with a person who already exists; they cannot create one."
            ),
            "saved": [],
            "rejected": [],
        }

    if not _has_affiliation_claim(usable):
        return {
            "status": "error",
            "reason": "no_affiliation_claim",
            "message": (
                "Nothing claims this person attended this institution. A "
                "name found near a university's name is not an alumnus."
            ),
            "saved": [],
            "rejected": [],
        }

    originating_class = str(
        (originating[0].get("evidence") or {}).get("source_class") or ""
    )
    record, split = resolve_record(
        store,
        identity_key,
        name,
        university,
        originating_class,
        _discriminators(usable),
    )

    saved: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for claim in usable:
        outcome = _admit_one(record, claim)
        (
            saved if outcome.get("field") and "reason" not in outcome else rejected
        ).append(outcome)

    return {
        "status": "success"
        if saved and not rejected
        else ("partial" if saved else "error"),
        "record_id": record["record_id"],
        "identity_key": identity_key,
        "namesake_split": split,
        "possible_namesakes": list(record.get("possible_namesakes") or []),
        "saved": saved,
        "rejected": rejected,
        "record": render_person(record),
    }


def _has_affiliation_claim(claims: list[dict[str, Any]]) -> bool:
    for claim in claims:
        if str(claim.get("field_name") or "") != UNIVERSITY_AFFILIATION:
            continue
        source_class = str((claim.get("evidence") or {}).get("source_class"))
        if can_corroborate(source_class):
            return True
    return False


def _admit_one(record: dict[str, Any], claim: dict[str, Any]) -> dict[str, Any]:
    """Validate and store one claim, or return a named refusal."""
    field_name = str(claim.get("field_name") or "")
    value = str(claim.get("value") or "")
    evidence = claim.get("evidence") or {}
    source_class = str(evidence.get("source_class") or "")

    if is_prohibited_field(field_name):
        return _reject(
            field_name,
            "prohibited_field",
            "MS Buddy does not store this about anyone, whatever a page publishes.",
        )

    if not is_writable(field_name):
        return _reject(
            field_name,
            "unknown_field",
            f"'{field_name}' is not an alumni field. Known fields: "
            f"{', '.join(ALL_FIELD_NAMES)}.",
        )

    validated = validate_alumni_value(field_name, value)
    if validated.get("status") != "ok":
        return _reject(
            field_name,
            str(validated.get("reason")),
            str(validated.get("message")),
        )

    if tier_for(source_class, field_name) is None:
        return _reject(
            field_name,
            "source_lacks_authority",
            f"A {source_class or 'unknown'} source has no standing to state "
            f"'{field_name}', so it is left unknown rather than recorded.",
        )

    return apply_alumni_claim(record, field_name, str(validated["value"]), evidence)


# --- Rendering -------------------------------------------------------------


def unknown_fields(record: dict[str, Any]) -> list[str]:
    """Fields with no stored value, named rather than omitted."""
    stored = set(record.get("fields") or {})
    return [name for name in ALL_FIELD_NAMES if name not in stored]


def render_person(record: dict[str, Any]) -> dict[str, Any]:
    """Present one alumni record with tiers, citations and staleness.

    Only registry fields can appear, because only registry fields can be
    written. Nothing prohibited can reach a reader through this path.
    """
    fields: dict[str, Any] = {}
    stale_fields: list[str] = []

    for name, entry in (record.get("fields") or {}).items():
        evidence = entry.get("evidence") or {}
        staleness = evaluate_staleness(evidence)
        if staleness["is_stale"]:
            stale_fields.append(name)
        fields[name] = {
            "value": entry.get("value"),
            "tier": entry.get("tier"),
            "source_domain": evidence.get("source_domain"),
            "source_class": evidence.get("source_class"),
            "authority": evidence.get("authority"),
            "source_url": evidence.get("source_url"),
            "resolved_url": evidence.get("resolved_url"),
            "url_resolution_status": evidence.get("url_resolution_status"),
            "supporting_quote": evidence.get("supporting_quote"),
            "retrieved_at": evidence.get("retrieved_at"),
            "staleness_class": evidence.get("staleness_class"),
            "is_stale": staleness["is_stale"],
            "staleness_notice": staleness["notice"],
            "conflicts": entry.get("conflicts", []),
            "corroborations": entry.get("corroborations", []),
            "source_count": len(entry.get("sources") or []),
            "all_source_domains": sorted(
                {
                    str((s.get("evidence") or {}).get("source_domain"))
                    for s in (entry.get("sources") or [])
                }
            ),
        }

    return {
        "record_id": record.get("record_id"),
        "identity_key": record.get("identity_key"),
        "name_as_published": record.get("name_as_published"),
        "university": record.get("university"),
        "originated_by": record.get("originated_by"),
        "fields": fields,
        "unknown_fields": unknown_fields(record),
        "stale_fields": stale_fields,
        "possible_namesakes": list(record.get("possible_namesakes") or []),
        "verified_count": sum(1 for f in fields.values() if f["tier"] == "VERIFIED"),
        "reported_count": sum(1 for f in fields.values() if f["tier"] == "REPORTED"),
    }


# --- Aggregation (Stage G) -------------------------------------------------

SELECTION_BIAS_NOTICE = (
    "These are the alumni who are publicly discoverable, which is not a "
    "representative sample — people with personal sites, conference talks or "
    "an alumni-story page are far easier to find than everyone else. Counts "
    "here describe what these sources show. This is not a placement rate and "
    "says nothing about what happens to a graduate of this program."
)


def summarize_alumni(people: list[dict[str, Any]]) -> dict[str, Any]:
    """Count what the stored records show, always against their denominator.

    Architecture §11 separates a fact from an aggregate from an
    interpretation. This function produces the middle one, and it is built so
    that the third cannot be assembled from it: **there are no ratios here,
    and no floats at all.** "3 of the 7 people I found list an employer" is
    honest; "43% of graduates are employed" is a claim about a population
    from a convenience sample, and the sample is exactly the people who are
    easy to find. Returning only counts and their denominator is what makes
    the wrong sentence unavailable rather than merely discouraged.

    `may_use_pattern_language` is the second control. Below `MIN_PATTERN_N`
    the counts are still reported — hiding them would be its own dishonesty —
    but the root is told it may not generalise from them.
    """
    total = len(people)
    coverage: dict[str, dict[str, int]] = {}
    for field_name in ALL_FIELD_NAMES:
        known = sum(1 for p in people if (p.get("fields") or {}).get(field_name))
        coverage[field_name] = {"known": known, "of": total}

    employers: dict[str, dict[str, Any]] = {}
    for person in people:
        entry = (person.get("fields") or {}).get(EMPLOYER)
        if not isinstance(entry, dict):
            continue
        value = str(entry.get("value") or "").strip()
        if not value:
            continue
        # Grouped case-insensitively, displayed as the first source wrote it.
        # Normalising the *display* string would silently rewrite a publisher's
        # own spelling of a company name.
        slot = employers.setdefault(value.casefold(), {"value": value, "count": 0})
        slot["count"] += 1

    return {
        "person_count": total,
        "is_empty": not total,
        "field_coverage": coverage,
        "employers": sorted(
            employers.values(), key=lambda e: (-e["count"], e["value"].casefold())
        ),
        "may_use_pattern_language": total >= MIN_PATTERN_N,
        "pattern_language_threshold": MIN_PATTERN_N,
        "selection_bias_notice": SELECTION_BIAS_NOTICE,
        "ruleset": VERSION,
    }


def render_alumni_store(store: dict[str, Any]) -> dict[str, Any]:
    """Present the whole directory, in a stable order.

    `is_empty` is surfaced deliberately: finding nobody is a correct result
    for a program with no public alumni footprint, and the caller needs to
    be able to say so plainly rather than treat it as a failure.

    The summary rides along on every read so that the denominator and the
    selection-bias notice are in front of the root whenever it has alumni to
    talk about — rather than being available from a separate tool it might
    not think to call.
    """
    people = store.get("people") or {}
    rendered = [render_person(people[rid]) for rid in sorted(people)]
    return {
        "person_count": len(rendered),
        "is_empty": not rendered,
        "people": rendered,
        "summary": summarize_alumni(rendered),
    }


def export_alumni(store: dict[str, Any]) -> dict[str, Any]:
    """The full stored directory, for inspection or deletion (spec P6)."""
    return {
        "schema_version": store.get("schema_version"),
        "created_at": store.get("created_at"),
        "updated_at": store.get("updated_at"),
        "ruleset": VERSION,
        **render_alumni_store(store),
    }


def normalize_person_name(name: str) -> str:
    """Re-exported for callers that need the same normalization as the key."""
    return normalize_name(name)
