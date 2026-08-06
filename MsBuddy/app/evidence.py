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

"""Evidence records, grounding harvest, and staleness (spec §7).

Pure Python over plain dicts, like `profile_store`. The one ADK-shaped input
is a session object, and it is read defensively through `getattr` so the
module stays unit-testable with simple stubs.

**Why harvest from `session.events` rather than trusting the model.** A
grounded turn records what was actually retrieved in `grounding_metadata`.
That record is produced by the runtime, not written by the model, so it
cannot be fabricated by a model that decides to invent a citation. Every
claim MS Buddy stores is checked against this harvest — which is what makes
spec §7.4.2 ("never fabricate admissions requirements") structural.

Two empirical facts about Vertex AI grounding drive the shapes here:

* `GroundingChunkWeb.domain` is `None` in practice; the **`title`** field
  carries the source domain (e.g. `"ethz.ch"`). Both are read, title first.
* `uri` is always a `vertexaisearch.cloud.google.com/grounding-api-redirect/`
  link, never the publisher's own URL. It resolves, but domain trust can
  never be derived from it — only from the domain string above.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import re
from typing import Any, Literal

from app.config import MAX_RETRIEVED_SEGMENT_CHARS
from app.reference.domain_trust import classify_domain, normalize_domain
from app.schemas import ClaimTier

StalenessClass = Literal["VOLATILE", "CYCLICAL", "SLOW", "PERSON"]

# Spec §7.3. Past its TTL a fact is surfaced with a staleness notice and
# becomes a re-verification candidate; it is never silently reused.
STALENESS_TTL_DAYS: dict[str, int] = {
    "VOLATILE": 7,
    "CYCLICAL": 90,
    "SLOW": 365,
    "PERSON": 180,
}

GROUNDING_REDIRECT_HOST = "vertexaisearch.cloud.google.com"

_WHITESPACE = re.compile(r"\s+")


def now_utc() -> dt.datetime:
    """Current UTC time."""
    return dt.datetime.now(dt.UTC)


def _normalize(text: str) -> str:
    return _WHITESPACE.sub(" ", (text or "").lower()).strip()


def _truncate(text: str) -> str:
    """Cap retrieved text before it can enter a prompt (spec §8.3)."""
    clean = (text or "").strip()
    if len(clean) <= MAX_RETRIEVED_SEGMENT_CHARS:
        return clean
    return clean[:MAX_RETRIEVED_SEGMENT_CHARS] + " […truncated]"


# --- Harvest ---------------------------------------------------------------


def harvest_metadata(metadatas: list[Any]) -> list[dict[str, Any]]:
    """Collect web sources from a list of `GroundingMetadata` objects.

    Returns one entry per distinct source domain, carrying the redirect URIs
    seen for it, the text segments the model grounded against it, and its
    trust classification.

    The chunk-index → supported-segment mapping follows the `deep-search`
    sample; the domain resolution and trust classification are MS Buddy's.
    """
    by_domain: dict[str, dict[str, Any]] = {}

    for metadata in metadatas:
        if metadata is None:
            continue

        chunks = getattr(metadata, "grounding_chunks", None) or []
        index_to_domain: dict[int, str] = {}

        for index, chunk in enumerate(chunks):
            web = getattr(chunk, "web", None)
            if web is None:
                continue
            # `domain` is None in practice; `title` carries the domain string.
            raw_domain = getattr(web, "domain", None) or getattr(web, "title", "")
            domain = normalize_domain(str(raw_domain))
            if not domain or domain == GROUNDING_REDIRECT_HOST:
                continue

            index_to_domain[index] = domain
            entry = by_domain.setdefault(
                domain,
                {
                    **classify_domain(domain),
                    "titles": [],
                    "uris": [],
                    "segments": [],
                    "queries": [],
                },
            )
            title = getattr(web, "title", None)
            if title and title not in entry["titles"]:
                entry["titles"].append(str(title))
            uri = getattr(web, "uri", None)
            if uri and uri not in entry["uris"]:
                entry["uris"].append(str(uri))

        for query in getattr(metadata, "web_search_queries", None) or []:
            for entry in by_domain.values():
                if query not in entry["queries"]:
                    entry["queries"].append(str(query))

        for support in getattr(metadata, "grounding_supports", None) or []:
            segment = getattr(support, "segment", None)
            text = _truncate(getattr(segment, "text", "") or "")
            if not text:
                continue
            for index in getattr(support, "grounding_chunk_indices", None) or []:
                domain = index_to_domain.get(index)
                if domain and text not in by_domain[domain]["segments"]:
                    by_domain[domain]["segments"].append(text)

    return list(by_domain.values())


def harvest_grounding(session: Any) -> list[dict[str, Any]]:
    """Collect web sources from a session's own events.

    Covers grounding produced directly in the session. A sub-agent invoked
    through `AgentTool` runs against its own private session, so its results
    reach the caller only via `record_session_grounding`.
    """
    return harvest_metadata(
        [
            getattr(event, "grounding_metadata", None)
            for event in (getattr(session, "events", None) or [])
        ]
    )


def merge_harvests(*harvests: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Union several harvests, combining URIs, queries and segments per domain."""
    merged: dict[str, dict[str, Any]] = {}
    for harvest in harvests:
        for entry in harvest or []:
            existing = merged.get(entry["domain"])
            if existing is None:
                merged[entry["domain"]] = {
                    **entry,
                    "titles": list(entry.get("titles") or []),
                    "uris": list(entry.get("uris") or []),
                    "segments": list(entry.get("segments") or []),
                    "queries": list(entry.get("queries") or []),
                }
                continue
            for key in ("titles", "uris", "segments", "queries"):
                for item in entry.get(key) or []:
                    if item not in existing[key]:
                        existing[key].append(item)
    return list(merged.values())


def read_ledger(state: Any) -> list[dict[str, Any]]:
    """Sources accumulated in the session-scoped evidence ledger (spec §6.1)."""
    from app.config import STATE_EVIDENCE_LEDGER

    stored = state.get(STATE_EVIDENCE_LEDGER)
    return stored if isinstance(stored, list) else []


def record_retrieval(state: Any, metadata: Any) -> list[dict[str, Any]]:
    """Fold one grounding metadata object into the evidence ledger."""
    from app.config import STATE_EVIDENCE_LEDGER

    merged = merge_harvests(read_ledger(state), harvest_metadata([metadata]))
    state[STATE_EVIDENCE_LEDGER] = merged
    return merged


def record_session_grounding(state: Any, session: Any) -> list[dict[str, Any]]:
    """Fold every grounded turn in `session` into the evidence ledger.

    Called from the research agent's own `after_agent_callback`, because that
    is the only place the grounding is fully visible. `AgentTool` runs the
    sub-agent against a private session, so its events never reach the
    caller; and ADK's `propagate_grounding_metadata` forwards only the
    metadata of the *last* content event, which for a summarising agent is
    routinely empty. `AgentTool` does forward `state_delta` back to the
    parent, so writing the harvest to state from inside the sub-agent is what
    gets it out.

    The ledger is session-scoped, never `user:`-scoped: structured evidence
    for the active conversation, exactly as spec §6.1 defines it, while raw
    retrieved text stays out of durable state (§6.2).
    """
    from app.config import STATE_EVIDENCE_LEDGER

    merged = merge_harvests(read_ledger(state), harvest_grounding(session))
    state[STATE_EVIDENCE_LEDGER] = merged
    return merged


def collect_sources(session: Any, state: Any) -> list[dict[str, Any]]:
    """Every source retrieved this conversation, from both channels."""
    return merge_harvests(harvest_grounding(session), read_ledger(state))


def retrieved_domains(harvest: list[dict[str, Any]]) -> set[str]:
    """The set of domains that were genuinely retrieved."""
    return {entry["domain"] for entry in harvest}


_DIGIT_RUN = re.compile(r"\d+")
# Thousands/decimal separators sitting between digits, so "22.290" and
# "22,290" both reduce to the run "22290".
# Thousands/decimal separators sitting between digits, so "22.290" and
# "22,290" both reduce to the run "22290". An unhandled separator simply
# fails to collapse, which rejects the claim rather than accepting it.
_DIGIT_SEPARATOR = re.compile(r"(?<=\d)[.,\s](?=\d)")


def digit_runs(text: str) -> set[str]:
    """Maximal digit runs in `text`, with thousands separators collapsed."""
    return set(_DIGIT_RUN.findall(_DIGIT_SEPARATOR.sub("", text or "")))


def value_is_supported_by_quote(value: str, quote: str) -> bool:
    """True if a numeric `value` is actually present in its supporting quote.

    Verifying the quote alone is not enough. A model can attach a genuine,
    retrievable quote to a number the source never stated — and did exactly
    that in testing, filing `tuition_academic_year = "2025/2026"` against a
    quote that contained no year at all. The quote check passes; the fact is
    still fabricated.

    Only values containing digits are checked, and each digit run in the
    value must match a digit run in the quote. Purely textual values
    ("EUR", "per year") are left alone, because those are legitimate
    normalisations of what a page says rather than claims of their own.

    Matching is by whole runs, not substrings, so a value of "290" cannot
    ride on a quoted "22.290".
    """
    wanted = digit_runs(value)
    if not wanted:
        return True
    return wanted <= digit_runs(quote)


def find_supporting_source(
    harvest: list[dict[str, Any]], quote: str, domain: str
) -> dict[str, Any] | None:
    """Return the harvested source that actually contains `quote`.

    A claim survives only if the quote appears in a segment the runtime
    recorded for that domain. This is the C2 analogue of the `evidence_span`
    check that guards the profile in C1.
    """
    wanted = normalize_domain(domain)
    needle = _normalize(quote)
    if not needle:
        return None
    for entry in harvest:
        if entry["domain"] != wanted:
            continue
        for segment in entry["segments"]:
            if needle in _normalize(segment):
                return entry
    return None


# --- Evidence records ------------------------------------------------------


def tier_for_source(source_class: str) -> ClaimTier:
    """Official sources yield `VERIFIED`; anything else is `REPORTED`."""
    return ClaimTier.VERIFIED if source_class == "official" else ClaimTier.REPORTED


def make_claim_id(program_id: str, field_name: str, value: str) -> str:
    """Stable id for a claim, so a repeat retrieval supersedes rather than duplicates."""
    digest = hashlib.sha256(f"{program_id}|{field_name}|{value}".encode()).hexdigest()
    return f"ev-{digest[:16]}"


def make_evidence_record(
    program_id: str,
    field_name: str,
    value: str,
    quote: str,
    source: dict[str, Any],
    staleness_class: str,
    agent_name: str,
) -> dict[str, Any]:
    """Build one evidence record with the full §7.2 field set."""
    tier = tier_for_source(source["source_class"])
    return {
        "claim_id": make_claim_id(program_id, field_name, value),
        "claim_text": f"{field_name} = {value}",
        "tier": tier.value,
        "source_url": (source.get("uris") or [None])[0],
        "source_domain": source["domain"],
        "source_is_official": bool(source["is_official"]),
        "source_class": source["source_class"],
        "trust_reason": source.get("reason"),
        "trust_ruleset": source.get("ruleset"),
        "supporting_quote": _truncate(quote),
        "retrieved_at": now_utc().isoformat(timespec="seconds"),
        "content_date": None,
        "retrieval_query": (source.get("queries") or [None])[0],
        "agent_name": agent_name,
        "staleness_class": staleness_class,
        "superseded_by": None,
        # The publisher's own URL is not exposed by Vertex grounding; the
        # citation link is Google's redirect. Recorded so a reader is never
        # misled about what they are clicking.
        "url_is_grounding_redirect": bool(
            source.get("uris") and GROUNDING_REDIRECT_HOST in (source["uris"][0] or "")
        ),
    }


def evaluate_staleness(
    record: dict[str, Any], now: dt.datetime | None = None
) -> dict[str, Any]:
    """Age a record against its TTL and produce a rendering notice."""
    moment = now or now_utc()
    ttl_days = STALENESS_TTL_DAYS.get(str(record.get("staleness_class")), 90)

    try:
        retrieved = dt.datetime.fromisoformat(str(record.get("retrieved_at")))
    except (TypeError, ValueError):
        return {
            "is_stale": True,
            "age_days": None,
            "ttl_days": ttl_days,
            "notice": "Retrieval date unreadable — treat as unverified and re-check.",
        }

    if retrieved.tzinfo is None:
        retrieved = retrieved.replace(tzinfo=dt.UTC)

    age_days = (moment - retrieved).days
    is_stale = age_days > ttl_days
    notice = None
    if is_stale:
        notice = (
            f"Retrieved {age_days} days ago, past the {ttl_days}-day freshness "
            "window for this kind of fact. Re-check the official source before "
            "relying on it."
        )
    return {
        "is_stale": is_stale,
        "age_days": age_days,
        "ttl_days": ttl_days,
        "notice": notice,
    }
