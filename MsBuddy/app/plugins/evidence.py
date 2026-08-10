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

"""`EvidencePlugin` — last line of defence on the way to the student (spec §7.5).

A plugin rather than an agent because this concern spans every agent and tool
(spec §4.1). It runs after the **root's** model call and asks one question:
did this answer assert an institutional fact that nothing retrieved supports?

Two outcomes, deliberately asymmetric:

* **No evidence available at all + institutional claims present** → the
  answer is replaced with a refusal. If nothing was retrieved *and* nothing
  is stored, every deadline, fee or requirement in the answer came from
  model priors, which spec §7.1 defines as a suppressed claim rather than a
  low-confidence one.
* **Evidence exists** → the answer passes through, and any numeric claim not
  found in that evidence is logged as an attribution alarm (spec §10.2)
  rather than deleted.

**"Evidence" means retrieved *or* stored.** Until Phase 3 the two were the
same thing, because every answer containing a fee had to have fetched it in
that session. C3 broke that assumption: comparison answers from the stored
shortlist and never retrieves, so a comparison turn legitimately has an
empty ledger. Treating that as "unsourced" refused every cross-session
comparison outright — the facts were sourced, just in an earlier session.
A stored ProgramRecord field is not a model prior: it only exists because
`save_program_record` verified that the domain was genuinely retrieved, the
quote genuinely appeared on it, and the value genuinely appeared in the
quote.

**Why not sentence-level deletion.** Spec §16.4 flagged claim detection as
the hard part of this design, and it was right. Excising individual sentences
from a model's answer reliably produces incoherent text, and a detector with
false positives would silently mangle correct answers. So the plugin blocks
whole answers only on the unambiguous signal, and otherwise reports. The
guarantee that a *stored* fact is sourced does not rest here at all — it
rests on `save_program_record`, which can verify deterministically.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_response import LlmResponse
from google.adk.plugins.base_plugin import BasePlugin
from google.genai import types

from app.config import STATE_SHORTLIST
from app.evidence import collect_sources
from app.program_store import read_shortlist

logger = logging.getLogger("msbuddy.evidence")

ROOT_AGENT_NAME = "root_agent"

# Phrasings that assert a fact about an institution. Deliberately narrow:
# a false positive here would block a correct answer.
#
# "Assert" is the operative word. The original `deadline` and `tuition`
# alternatives matched the bare noun, which meant a capability list —
# "I can check tuition and deadlines for you" — counted as a claim. In a
# fresh session (no harvest, no shortlist) that is precisely the blocking
# condition, so the very first "who are you?" of a conversation was replaced
# with the memory refusal (observed live, 2026-08-07). Offering to look
# something up asserts nothing; only stating a value does, so these now
# require the assertive form: "the deadline is …", "tuition is …".
INSTITUTIONAL_CLAIM_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    # The assertive verb may sit across a `for/of/at <subject>` phrase —
    # "the deadline for MIT EECS is 15 December" asserts as hard as "the
    # deadline is 15 December". Only those prepositions bridge, so a
    # capability list ("deadlines and requirements are things I can check")
    # still is not a claim.
    (
        "deadline",
        re.compile(
            r"\b(deadlines?(\s+(for|of|at)\s+[^.?!]{0,40})?"
            r"\s+(is|are|was|were|falls?|:)"
            r"|due\s+date|closes?\s+on|applications?\s+close)\b",
            re.I,
        ),
    ),
    (
        "tuition",
        re.compile(
            r"\b(tuition(\s+(for|of|at)\s+[^.?!]{0,40})?\s+(is|was|:|runs)"
            r"|fees?\s+(are|is)|costs?\s+(about|around)?\s*[\$€£₹])",
            re.I,
        ),
    ),
    (
        "requirement",
        re.compile(
            r"\b(requires?|minimum\s+(gpa|score|gre|toefl|ielts)|cut\s?off|eligibility\s+criteria)\b",
            re.I,
        ),
    ),
    (
        "acceptance",
        re.compile(r"\b(acceptance\s+rate|admission\s+rate|accepts?\s+\d+%)", re.I),
    ),
    ("ranking", re.compile(r"\b(ranked\s+#?\d+|ranking\s+is)\b", re.I)),
)

# Numbers that would carry a factual payload: dates, money, scores.
#
# Unbounded on the upper end since the Phase 3 audit. The original `\d{2,4}`
# silently skipped every five-figure tuition — `22290` and `15605` are both
# real retrieved values — so the attribution alarm was blind to the single
# most common numeric institutional claim there is.
NUMERIC_CLAIM = re.compile(r"\b\d{2,}(?:[/-]\d{1,2}[/-]\d{1,4})?\b")

REFUSAL_TEXT = (
    "I can't answer that from memory.\n\n"
    "That question needs facts about a university — a deadline, a fee, a "
    "requirement — and nothing was retrieved to support them in this "
    "conversation. Anything I produced without a source would be a guess "
    "dressed up as an answer, and in an application cycle that costs you "
    "real time and money.\n\n"
    "Ask me to look it up and I'll search, then tell you exactly which "
    "source each fact came from and how recent it is — and I'll name what I "
    "couldn't find rather than filling the gap."
)


def _response_text(llm_response: LlmResponse) -> str:
    content = getattr(llm_response, "content", None)
    if content is None:
        return ""
    return "".join(
        part.text
        for part in (getattr(content, "parts", None) or [])
        if getattr(part, "text", None)
    )


def find_institutional_claims(text: str) -> list[str]:
    """Claim categories asserted in `text`."""
    return [
        name for name, pattern in INSTITUTIONAL_CLAIM_PATTERNS if pattern.search(text)
    ]


def stored_evidence(state: Any) -> tuple[int, list[str]]:
    """Sourced facts already in the shortlist, with the text supporting them.

    Returns the number of stored fields and the strings a numeric claim
    could legitimately have come from — each stored value and the verbatim
    quote that was verified against retrieved content when it was saved.

    This is what stops C3 from being refused. A comparison turn retrieves
    nothing by design, so without this the ledger is empty and every answer
    naming a fee looks like a fabrication.
    """
    fields = 0
    texts: list[str] = []
    for record in (
        read_shortlist(state, STATE_SHORTLIST).get("programs") or {}
    ).values():
        for entry in (record.get("fields") or {}).values():
            fields += 1
            texts.append(str(entry.get("value") or ""))
            quote = (entry.get("evidence") or {}).get("supporting_quote")
            if quote:
                texts.append(str(quote))
    return fields, texts


def unsupported_numbers(text: str, segments: list[str]) -> list[str]:
    """Numeric tokens in `text` that appear in no retrieved segment."""
    haystack = " ".join(segments)
    return sorted(
        {token for token in NUMERIC_CLAIM.findall(text) if token not in haystack}
    )


class EvidencePlugin(BasePlugin):
    """Blocks unsourced institutional answers and reports attribution health."""

    def __init__(self, name: str = "evidence") -> None:
        super().__init__(name=name)

    async def after_model_callback(
        self,
        *,
        callback_context: CallbackContext,
        llm_response: LlmResponse,
    ) -> LlmResponse | None:
        """Screen the root's answer. Returns a replacement only when blocking."""
        try:
            if getattr(callback_context, "agent_name", None) != ROOT_AGENT_NAME:
                return None
            if getattr(llm_response, "partial", False):
                return None

            text = _response_text(llm_response)
            if not text.strip():
                return None

            claims = find_institutional_claims(text)

            invocation = callback_context.get_invocation_context()
            harvest = collect_sources(
                getattr(invocation, "session", None), callback_context.state
            )
            stored_count, stored_texts = stored_evidence(callback_context.state)
            segments = [s for entry in harvest for s in entry["segments"]]
            segments.extend(stored_texts)

            record: dict[str, Any] = {
                "event": "evidence_screen",
                "invocation_id": getattr(callback_context, "invocation_id", None),
                "claim_categories": claims,
                "sources_retrieved": len(harvest),
                "official_sources": sum(1 for e in harvest if e["is_official"]),
                "stored_facts": stored_count,
                "blocked": False,
                "alarm": False,
            }

            if claims and not harvest and not stored_count:
                record["blocked"] = True
                record["alarm"] = True
                record["reason"] = "institutional_claims_with_no_evidence"
                logger.warning(json.dumps(record))
                return LlmResponse(
                    content=types.Content(
                        role="model",
                        parts=[types.Part.from_text(text=REFUSAL_TEXT)],
                    )
                )

            if claims and (harvest or stored_count):
                orphans = unsupported_numbers(text, segments)
                record["unsupported_numeric_tokens"] = orphans
                record["alarm"] = bool(orphans)

            logger.info(json.dumps(record))
            return None
        # Broad by intent: a screening failure must not break the turn.
        except Exception:
            logger.exception("evidence screening failed")
            return None
