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

"""C4 Stage C — the deterministic admission gate for alumni.

This is the anti-fabrication stage. A model may *propose* a person; only the
checks below may admit one. Nothing here reasons, and nothing here trusts a
caller: every claim is re-derived from what the runtime actually retrieved.

The gate, in the order the Stage 0 decision fixes it:

| # | Check | On failure |
|---|---|---|
| 1 | The cited domain was genuinely retrieved this turn | **reject** |
| 2 | A grounded segment from that domain contains the **name** | **reject** |
| 3 | That **same** segment supports the claimed value | **reject** |
| 4 | The source class may originate a person | **reject** |
| 5 | Identity resolves without an unsafe merge | **reject / split** |
| 6 | The grounding redirect resolves to a publisher URL | **degrade** |
| 7 | The resolved host agrees with the cited domain | **reject** |

**Checks 1-5 are blocking and offline.** They are the guarantee, and they
hold with the network unplugged. Check 6 is best-effort precisely so that
evidence quality never depends on transient network conditions — a
resolution failure marks the record `url_unresolved` and keeps it. Check 7
is blocking whenever it runs: a citation that resolves somewhere else is a
wrong citation, and a wrong citation is worse than none.

**Same-segment is the load-bearing rule.** Checks 2 and 3 must be satisfied
by *one* segment, not by two convenient fragments of the same page. A name
in one sentence and an employer in another is how a real person acquires a
job they never had.

Outbound HTTP is confined to `resolve_grounding_redirect`: stdlib `urllib`,
`HEAD` only, redirects deliberately *not* followed. Only Google's redirect
service is contacted — the publisher's own server is never touched, so
there is no robots or terms question to answer.
"""

from __future__ import annotations

import copy
import urllib.error
import urllib.request
from typing import Any

from google.adk.tools import ToolContext

from app.affinity import (
    anchor_values_from_profile,
    describe_anchors,
    rank_people,
)
from app.alumni_store import (
    URL_NOT_ATTEMPTED,
    URL_RESOLVED,
    URL_UNRESOLVED,
    admit_candidate,
    make_alumni_evidence,
    read_alumni_store,
    render_alumni_store,
    write_alumni_store,
)
from app.config import (
    MAX_URL_RESOLUTIONS_PER_TURN,
    STATE_ALUMNI,
    STATE_ALUMNI_ANCHOR,
    STATE_PROFILE,
    STATE_URL_RESOLUTION_CACHE,
    URL_RESOLUTION_TIMEOUT_SECONDS,
)
from app.evidence import (
    GROUNDING_REDIRECT_HOST,
    collect_sources,
    digit_runs,
    retrieved_domains,
)
from app.identity import normalize_name
from app.profile_store import read_profile
from app.reference.domain_trust import normalize_domain
from app.reference.source_authority import (
    EMPLOYER,
    can_originate,
    classify_alumni_source,
)
from app.schemas import AlumniCandidate

# The architecture calls for "reusing C2's screening", so this imports the
# actual C2 helper rather than restating the rule. A second copy of a
# privacy check is a second thing to forget to update.
from app.tools.program_tools import _sensitive_values

DISCOVERY_AGENT_NAME = "alumni_discovery_agent"

_WHITESPACE_CHARS = " \t\n\r\f\v"


def _flatten(text: str) -> str:
    """Lower-case with whitespace collapsed, for substring comparison."""
    return " ".join(str(text or "").lower().split())


# --- Checks 2 and 3: name and claim in the same grounded segment -----------


def segments_for_domain(harvest: list[dict[str, Any]], domain: str) -> list[str]:
    """Every text segment the runtime grounded against `domain`."""
    wanted = normalize_domain(domain)
    return [
        segment
        for entry in harvest
        if entry.get("domain") == wanted
        for segment in (entry.get("segments") or [])
    ]


def value_supported_by(segment: str, value: str) -> bool:
    """True if `segment` actually states `value`.

    Textual values must appear as written; numeric ones must match by whole
    digit run, reusing the same primitive C2 uses so a graduation year of
    `2021` cannot ride on a quoted `12021`.

    A paraphrase fails. That is intentional: refusing a value the source did
    not write is the correct direction to err for a fact about a person.
    """
    flat_segment = _flatten(segment)
    flat_value = _flatten(value)
    if not flat_value:
        return False
    if flat_value in flat_segment:
        return True

    wanted = digit_runs(flat_value)
    return bool(wanted) and wanted <= digit_runs(flat_segment)


def find_supporting_segment(
    harvest: list[dict[str, Any]],
    domain: str,
    name: str,
    value: str,
) -> dict[str, Any]:
    """Locate one segment from `domain` that carries the name *and* the claim.

    Returns a verdict dict rather than raising, so the caller can hand the
    student a precise reason instead of a silent omission. The matched
    `segment` comes back with it, and that — not the agent's wording — is what
    gets stored as provenance.

    **The reported quote is deliberately not matched against.** Segments are
    spans of the *agent's own answer* that the search runtime chose to
    attribute to a domain (`evidence.harvest_metadata`), and which spans those
    are is invisible to the agent producing them. Requiring the quote to be
    one of them asked the model to guess an unobservable target; observed live
    2026-08-06, a candidate whose quote carried both the name and the value
    was refused because the attributed sentence was worded differently.

    Nothing is conceded by dropping it. The quote never carried authority of
    its own — it was the model's restatement, checked against the model's own
    text. What decides admission is what always decided it, and all of it is
    deterministic: the domain was retrieved this turn, and one segment
    attributed to it contains the name and the value *together*. The agent
    does not choose the attribution and cannot forge it, so a person or a fact
    no source supports still matches nothing.
    """
    segments = segments_for_domain(harvest, domain)
    if not segments:
        return {
            "ok": False,
            "reason": "domain_not_retrieved",
            "message": (
                f"Nothing was retrieved from '{domain}' this turn, so it "
                "cannot support a claim about anyone."
            ),
        }

    flat_name = _flatten(normalize_name(name))
    named = [s for s in segments if flat_name and flat_name in _flatten(s)]
    if not named:
        return {
            "ok": False,
            "reason": "name_not_in_source",
            "message": (
                f"No retrieved text from '{domain}' contains the name "
                f"'{name}'. A person who appears in no source does not exist "
                "as far as this system is concerned."
            ),
        }

    for segment in named:
        if value_supported_by(segment, value):
            return {"ok": True, "segment": segment}

    return {
        "ok": False,
        "reason": "claim_not_in_same_segment",
        "message": (
            f"'{domain}' names {name}, but no single passage there states "
            f"'{value}' alongside the name. A name in one sentence and a "
            "claim in another is not evidence that they belong together."
        ),
    }


# --- Checks 6 and 7: bounded redirect resolution ---------------------------


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Stops urllib following the redirect; the `Location` header is the point."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, newurl, headers, fp)


def _head_location(url: str) -> str | None:
    """Return the `Location` a HEAD on `url` redirects to, or None."""
    try:
        # Inside the guard: `Request` rejects a malformed URL with
        # ValueError, and `source_url` is model-supplied. A bad URL must
        # cost this claim its resolved link, never the whole tool call.
        opener = urllib.request.build_opener(_NoRedirect)
        request = urllib.request.Request(url, method="HEAD")
        opener.open(request, timeout=URL_RESOLUTION_TIMEOUT_SECONDS)
    except urllib.error.HTTPError as exc:
        # `reason` carries the redirect target, per `_NoRedirect` above.
        if 300 <= exc.code < 400:
            return str(exc.reason)
        return None
    except Exception:
        # Any transport problem at all. Deliberately broad: this path must
        # degrade, never crash, and never reject a content-verified record.
        return None
    return None


def resolve_grounding_redirect(
    url: str | None,
    cache: dict[str, Any],
    remaining: int,
) -> dict[str, Any]:
    """Resolve one grounding redirect to its publisher URL, within budget.

    One request per unique URL; the cache is session-scoped so a source seen
    twice costs nothing. `remaining` bounds how many *new* resolutions this
    call may perform.
    """
    if not url:
        return {"status": URL_NOT_ATTEMPTED, "resolved_url": None, "spent": 0}

    if url in cache:
        return {**cache[url], "spent": 0}

    if GROUNDING_REDIRECT_HOST not in url:
        # Not a Google redirect, so there is nothing to unwrap and no reason
        # to make a request.
        outcome = {"status": URL_NOT_ATTEMPTED, "resolved_url": None}
        cache[url] = outcome
        return {**outcome, "spent": 0}

    if remaining <= 0:
        return {
            "status": URL_UNRESOLVED,
            "resolved_url": None,
            "reason": "resolution_budget_exhausted",
            "spent": 0,
        }

    location = _head_location(url)
    outcome: dict[str, Any] = (
        {"status": URL_RESOLVED, "resolved_url": location}
        if location
        else {
            "status": URL_UNRESOLVED,
            "resolved_url": None,
            "reason": "redirect_did_not_resolve",
        }
    )
    cache[url] = outcome
    return {**outcome, "spent": 1}


def hosts_agree(resolved_url: str, cited_domain: str) -> bool:
    """True if a resolved URL belongs to the domain that was cited.

    Compared on the registrable domain, so `alumni.tudelft.nl` agrees with
    `tudelft.nl` while `tudelft.nl.example.com` does not.
    """
    host = normalize_domain(resolved_url)
    cited = normalize_domain(cited_domain)
    if not host or not cited:
        return False
    return host == cited or host.endswith("." + cited)


# --- Stage D: query construction and the privacy screen --------------------

# Appended so the assembled string asks for people rather than for the
# program itself. It is a scoping word, not student data, and it is visible
# in the returned `query` so nothing is added behind the caller's back.
ALUMNI_SCOPE_TERM = "alumni"


def _assemble_query(parts: list[str]) -> str:
    """Join the scope terms, dropping any part an earlier one already covers.

    The first live run produced `TU Delft MSc Computer Science Computer
    Science alumni`, because the caller passed a program and a field that
    overlapped. A repeated term adds no scope and costs recall, and low
    recall is what turns "nobody was found" from an honest answer into an
    artifact of the query.

    A part is dropped only when *every* word in it has already appeared, and
    is otherwise kept verbatim. Dropping individual words instead would turn
    `MSc Computer Science` + `data science` into `... data`, which is not
    the field anyone asked about — a phrase survives or it does not.
    """
    seen: set[str] = set()
    kept: list[str] = []
    for part in parts:
        words = {w.casefold() for w in part.split()}
        if words and words <= seen:
            continue
        seen |= words
        kept.append(part)
    return " ".join(kept)


def build_alumni_query(
    university: str,
    program: str,
    field: str,
    tool_context: ToolContext,
) -> dict:
    """Build a privacy-safe web search query for alumni of a program.

    Assembles the query from the institution, program and field only, then
    checks it against the student's own stored profile and refuses if any of
    their private details appear. Use this before asking for an alumni
    search; never hand-write a query, and never add the student's scores,
    institution, budget or citizenship to one.

    An institution is required. MS Buddy answers "who did this program", so
    a search with no institution to anchor it is refused rather than run.

    Args:
        university: The institution whose alumni are being sought. Required.
        program: Program or degree, e.g. 'MSc Computer Science', or an
            empty string.
        field: Career or study field to scope to, e.g. 'data science', or
            an empty string.

    Returns:
        A dict with the assembled `query` and the `anchor` it was scoped to,
        or an error naming what would have leaked or what was missing.
    """
    anchor = str(university or "").strip()
    if not anchor:
        return {
            "status": "error",
            "reason": "no_university_anchor",
            "message": (
                "An alumni search needs an institution to scope it. Without "
                "one this becomes a search for a person, which MS Buddy does "
                "not do. Ask which university or program the student means."
            ),
        }

    scope = str(program or "").strip()
    area = str(field or "").strip()
    query = _assemble_query([p for p in (anchor, scope, area, ALUMNI_SCOPE_TERM) if p])
    lowered = query.lower()

    profile = read_profile(tool_context.state, STATE_PROFILE)
    for leaked_field, value in _sensitive_values(profile):
        if value in lowered:
            return {
                "status": "error",
                "reason": "profile_data_in_query",
                "message": (
                    f"The query contains the student's '{leaked_field}', which "
                    "must never be sent to a search engine. Rebuild it from "
                    "the institution, program and field only."
                ),
            }

    # Recorded only once the query has actually passed. A refused query
    # scopes nothing, so it must not leave an anchor behind for a later step
    # to pick up.
    tool_context.state[STATE_ALUMNI_ANCHOR] = {
        "university": anchor,
        "program": scope,
        "field": area,
    }

    return {
        "status": "success",
        "query": query,
        "anchor": {"university": anchor, "program": scope, "field": area},
        "note": (
            "Privacy-checked against the stored profile. Search only for "
            "what this query asks; do not add the student's details to it, "
            "and do not search for a named individual."
        ),
    }


# --- The tools -------------------------------------------------------------


def _candidate_employer(candidate: AlumniCandidate) -> str:
    for claim in candidate.claims:
        if claim.field_name == EMPLOYER:
            return claim.value
    return ""


def save_alumni_records(
    candidates: list[AlumniCandidate], tool_context: ToolContext
) -> dict:
    """Record alumni that public sources actually support, and refuse the rest.

    Every proposed person is checked against what search really returned. A
    name that appears in no retrieved source is not stored and not reported,
    however plausible it looks. Facts are recorded only from sources with
    standing to state them; anything else is returned as unknown.

    An empty list is a valid, successful result: a program with no publicly
    discoverable alumni is a real answer.

    Args:
        candidates: People proposed by the research step. Each needs a
            `name`, the `university` they are claimed to have attended, and
            `claims` carrying `field_name`, `value`, `source_domain` and a
            verbatim `supporting_quote`.

    Returns:
        A dict with the people admitted, per-candidate `rejected` reasons,
        and the fields that remain unknown.
    """
    if not candidates:
        return {
            "status": "success",
            "is_empty": True,
            "admitted": [],
            "rejected": [],
            "message": (
                "No candidates were supplied. Finding nobody is a correct "
                "result for a program with no public alumni footprint — say "
                "so plainly rather than offering general impressions."
            ),
        }

    harvest = collect_sources(
        getattr(tool_context, "session", None), tool_context.state
    )
    if not harvest:
        return {
            "status": "error",
            "reason": "no_sources_retrieved",
            "message": (
                "Nothing was retrieved this session, so no person can be "
                "recorded. Search first. Never record a person from memory."
            ),
            "admitted": [],
            "rejected": [],
        }

    available = retrieved_domains(harvest)
    store = read_alumni_store(tool_context.state, STATE_ALUMNI)
    cache = tool_context.state.setdefault(STATE_URL_RESOLUTION_CACHE, {})
    if not isinstance(cache, dict):
        cache = {}
        tool_context.state[STATE_URL_RESOLUTION_CACHE] = cache

    budget = MAX_URL_RESOLUTIONS_PER_TURN
    admitted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for raw in candidates:
        candidate = (
            raw
            if isinstance(raw, AlumniCandidate)
            else AlumniCandidate.model_validate(raw)
        )
        # Each candidate is admitted against its own copy, and the copy is
        # kept only if the gate admits it. This tool is the boundary between
        # an untrusted candidate and persisted state, so the boundary is
        # where the transaction belongs — Stage B stays a deterministic
        # primitive that simply does what it is asked.
        #
        # Discarding rather than undoing is the point. Admission creates
        # linked state: a namesake split writes `possible_namesakes` onto
        # *other* records too, so removing "the record that was added" would
        # mean guessing what else was touched. A discarded copy cannot guess
        # wrong.
        #
        # ponytail: deep copy per candidate. The store is capped at
        # MAX_ALUMNI_RESULTS, so this is a handful of small dicts; revisit
        # only if that cap grows by orders of magnitude.
        working = copy.deepcopy(store)
        outcome, budget = _admit(candidate, harvest, working, cache, budget, available)
        if outcome.get("admitted"):
            store = working
            admitted.append(outcome)
        else:
            rejected.append(outcome)

    if admitted:
        write_alumni_store(tool_context.state, STATE_ALUMNI, store)

    if admitted and rejected:
        status = "partial"
    elif admitted:
        status = "success"
    else:
        status = "error"

    return {
        "status": status,
        "is_empty": not admitted,
        "admitted": admitted,
        "rejected": rejected,
        "retrieved_domains": sorted(available),
    }


def _admit(
    candidate: AlumniCandidate,
    harvest: list[dict[str, Any]],
    store: dict[str, Any],
    cache: dict[str, Any],
    budget: int,
    available: set[str],
) -> tuple[dict[str, Any], int]:
    """Run the gate for one candidate. Returns the outcome and the budget left."""
    verified: list[dict[str, Any]] = []
    refused: list[dict[str, Any]] = []
    employer = _candidate_employer(candidate)

    for claim in candidate.claims:
        domain = normalize_domain(claim.source_domain)

        # Check 1 — the cited domain was genuinely retrieved this turn.
        if domain not in available:
            refused.append(
                {
                    "field": claim.field_name,
                    "reason": "domain_not_retrieved",
                    "message": (
                        f"'{claim.source_domain}' was not retrieved this turn. "
                        f"Domains actually retrieved: {', '.join(sorted(available)) or 'none'}."
                    ),
                }
            )
            continue

        # Checks 2 and 3 — name and claim in one segment from that domain.
        support = find_supporting_segment(harvest, domain, candidate.name, claim.value)
        if not support["ok"]:
            refused.append(
                {
                    "field": claim.field_name,
                    "reason": support["reason"],
                    "message": support["message"],
                }
            )
            continue

        # Check 4 — may this class of source establish a person at all.
        classified = classify_alumni_source(
            domain, url=claim.source_url or "", claimed_employer=employer
        )
        source_class = str(classified["source_class"])

        # Checks 6 and 7 — resolve the redirect, then insist it agrees.
        resolution = resolve_grounding_redirect(claim.source_url, cache, budget)
        budget -= int(resolution.get("spent", 0))

        resolved_url = resolution.get("resolved_url")
        if resolution["status"] == URL_RESOLVED and resolved_url:
            if not hosts_agree(str(resolved_url), domain):
                return (
                    {
                        "name": candidate.name,
                        "admitted": False,
                        "reason": "resolved_host_mismatch",
                        "message": (
                            f"The citation claims '{domain}' but its link "
                            f"resolves to '{normalize_domain(str(resolved_url))}'. "
                            "A citation that points somewhere else is wrong, "
                            "and nothing from this candidate is stored."
                        ),
                        "rejected_claims": refused,
                    },
                    budget,
                )

        verified.append(
            {
                "field_name": claim.field_name,
                "value": claim.value,
                "evidence": make_alumni_evidence(
                    source_domain=domain,
                    source_class=source_class,
                    # The segment the gate matched, not the agent's wording.
                    # This is the text the runtime actually attributed to
                    # `domain`, so it is the honest record of why the claim
                    # was admitted — and it is what a student would be shown
                    # if they asked how we know.
                    supporting_quote=support["segment"],
                    field_name=claim.field_name,
                    source_url=claim.source_url,
                    resolved_url=resolved_url,
                    url_resolution_status=str(resolution["status"]),
                ),
            }
        )

    if not verified:
        return (
            {
                "name": candidate.name,
                "admitted": False,
                "reason": "no_verifiable_claim",
                "message": (
                    f"Nothing about {candidate.name} could be verified against "
                    "retrieved content, so they are not recorded."
                ),
                "rejected_claims": refused,
            },
            budget,
        )

    # Check 4 again, at candidate level, and check 5 — both inside Stage B.
    if not any(can_originate(str(c["evidence"]["source_class"])) for c in verified):
        return (
            {
                "name": candidate.name,
                "admitted": False,
                "reason": "source_cannot_originate",
                "message": (
                    "Only aggregators, publications or self-published pages "
                    "support this person. Those may corroborate someone who "
                    "already exists; they cannot establish that someone does."
                ),
                "rejected_claims": refused,
            },
            budget,
        )

    result = admit_candidate(store, candidate.name, candidate.university, verified)
    if result["status"] == "error" and not result.get("saved"):
        return (
            {
                "name": candidate.name,
                "admitted": False,
                "reason": result.get("reason", "not_admitted"),
                "message": result.get("message", ""),
                "rejected_claims": refused + list(result.get("rejected", [])),
            },
            budget,
        )

    return (
        {
            "name": candidate.name,
            "admitted": True,
            "record_id": result["record_id"],
            "identity_key": result["identity_key"],
            "namesake_split": result["namesake_split"],
            "possible_namesakes": result["possible_namesakes"],
            "saved": result["saved"],
            "rejected_claims": refused + list(result.get("rejected", [])),
            "record": result["record"],
        },
        budget,
    )


def rank_alumni_by_affinity(tool_context: ToolContext) -> dict:
    """Order recorded alumni by what they demonstrably share with the student.

    Ranking is by the number of matched anchors — same undergraduate
    institution, same undergraduate field, same specialization — each computed
    locally from the stored profile and shown with the rationale that produced
    it. There is no similarity score to explain away: a match either rests on
    two evidenced values or it does not happen.

    Nobody is filtered out. Someone sharing nothing with the student is still
    a real alumnus of the program, and ties are left tied.

    Returns:
        A dict with the ranked people, the anchors that were available to
        match on, and the aggregate summary with its denominator.
    """
    rendered = render_alumni_store(read_alumni_store(tool_context.state, STATE_ALUMNI))
    student_values = anchor_values_from_profile(
        read_profile(tool_context.state, STATE_PROFILE)
    )
    ranked = rank_people(rendered["people"], student_values)

    return {
        "status": "success",
        "person_count": rendered["person_count"],
        "is_empty": rendered["is_empty"],
        # Names only. The values themselves reach the student through each
        # match's rationale, and they never go anywhere else — an anchor is
        # computed here and is structurally incapable of reaching a query.
        "anchors_matched_on": sorted(student_values),
        "anchors_available": describe_anchors(),
        "people": ranked,
        "summary": rendered["summary"],
        "note": (
            "Ranked by matched anchors only. Equal ranks are genuinely equal — "
            "do not break a tie. Say what each match was, and say plainly when "
            "someone shares nothing: that is not a mark against them."
        ),
    }


def get_alumni(tool_context: ToolContext) -> dict:
    """Return every alumnus recorded so far, with sources and staleness.

    Read this before searching again — someone already recorded and still
    fresh does not need looking up twice.

    Returns:
        A dict containing the stored people and each claim's provenance.
        `is_empty` being true is a valid answer, not a failure.
    """
    store = read_alumni_store(tool_context.state, STATE_ALUMNI)
    rendered = render_alumni_store(store)
    return {"status": "success", **rendered}
