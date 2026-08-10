"""Alumni entity resolution — merge evidence, never merge people by guess.

The same person appears on a university page, LinkedIn, GitHub and a
research index; they must count once (§52). Two different people share a
name; they must never become one record (§53). The rules, all
deterministic and biased toward two records over one wrong one:

* Candidate identity = normalized name + university. Different university →
  always separate.
* Same identity, conflicting **graduation_year** → different people
  (a graduation year is immutable). Kept separate, cross-marked as
  possible namesakes.
* Same identity, different **company/role/location** → plausibly the same
  person at a different time (mutable facts). Merged, with both values
  retained as a reported conflict and freshness left to the presenter.
* Evidence strength grows with independent corroboration: 2+ distinct
  sources → strong; one Tier-1 source → strong; one Tier-2 → moderate;
  one Tier-3 → weak.
"""

from __future__ import annotations

import unicodedata

from app.alumni.models import AlumniRecord

IMMUTABLE_FIELDS = ("graduation_year",)


def normalize_name(name: str) -> str:
    decomposed = unicodedata.normalize("NFKD", str(name or ""))
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(stripped.casefold().split())


def identity_key(name: str, university: str) -> str:
    return f"{normalize_name(name)}::{' '.join(str(university).casefold().split())}"


def _immutable_conflict(a: AlumniRecord, b: AlumniRecord) -> bool:
    for field in IMMUTABLE_FIELDS:
        va = a.claims.get(field)
        vb = b.claims.get(field)
        if va and vb and va.value.strip() != vb.value.strip():
            return True
    return False


def _strength(record: AlumniRecord) -> str:
    tiers = {e.tier for e in (c.evidence for c in record.claims.values())}
    distinct_sources = set(record.source_keys)
    if len(distinct_sources) >= 2 or 1 in tiers:
        return "strong"
    if 2 in tiers:
        return "moderate"
    return "weak"


def merge_records(existing: AlumniRecord, incoming: AlumniRecord) -> AlumniRecord:
    """Fold `incoming` into `existing` (same resolved identity)."""
    merged = existing.model_copy(deep=True)
    for field, claim in incoming.claims.items():
        current = merged.claims.get(field)
        if current is None:
            merged.claims[field] = claim
        elif current.value.strip().casefold() != claim.value.strip().casefold():
            # Mutable fact, different value: retain both, decide nothing.
            conflict = {
                "value": claim.value,
                "source_domain": claim.evidence.source_domain,
                "retrieved_at": claim.evidence.retrieved_at,
            }
            if conflict not in current.conflicts:
                current.conflicts.append(conflict)
        # Same value again = corroboration, tracked at record level via
        # source_keys below; the claim keeps its first evidence.
    for key in incoming.source_keys:
        if key not in merged.source_keys:
            merged.source_keys.append(key)
    merged.evidence_strength = _strength(merged)
    return merged


def resolve_alumni_identity(
    store: dict[str, dict], incoming: AlumniRecord
) -> tuple[dict[str, dict], str]:
    """Place one incoming record into the store.

    Returns the updated store and what happened: `new`, `merged`, or
    `namesake_split`.
    """
    key = identity_key(incoming.name, incoming.university)
    raw = store.get(key)
    if raw is None:
        incoming.evidence_strength = _strength(incoming)
        store[key] = incoming.model_dump()
        return store, "new"

    existing = AlumniRecord.model_validate(raw)
    if _immutable_conflict(existing, incoming):
        # Two people. Keep both, cross-marked; the split key carries the
        # differing year so it stays deterministic and readable.
        year = incoming.claims["graduation_year"].value.strip()
        split_key = f"{key}::{year}"
        incoming.possible_namesake_of.append(key)
        if key not in [existing.possible_namesake_of]:
            existing.possible_namesake_of.append(split_key)
        incoming.evidence_strength = _strength(incoming)
        store[key] = existing.model_dump()
        store[split_key] = incoming.model_dump()
        return store, "namesake_split"

    store[key] = merge_records(existing, incoming).model_dump()
    return store, "merged"
