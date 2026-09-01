"""Deterministic text matching used by the tools and the scorer.

Everything the student types is matched against explicit `aliases` / `keywords`
in the case file.  This is intentionally *not* an LLM call: scoring has to be
reproducible, and a faculty reviewer has to be able to predict it from the
case JSON alone.
"""

from __future__ import annotations

import re
import unicodedata

_WORD = re.compile(r"[a-z0-9]+")


def normalise(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "").lower()
    return " ".join(_WORD.findall(text))


def _padded(text: str) -> str:
    return f" {normalise(text)} "


def contains_any(haystack: str, needles: list[str]) -> str | None:
    """Return the first needle found in `haystack`, else None."""
    hay = _padded(haystack)
    for needle in needles:
        n = normalise(needle)
        if n and f" {n} " in hay:
            return needle
    return None


# Filler words that carry no clinical meaning when a student phrases a request.
_FILLER = {
    "a", "an", "the", "and", "or", "of", "to", "for", "in", "on", "at", "with",
    "from", "please", "can", "could", "would", "do", "does", "did", "i", "we",
    "you", "want", "like", "get", "order", "send", "take", "give", "check",
    "run", "his", "her", "him", "them", "this", "that", "it", "is", "are",
    "his", "s", "also", "then", "next", "now", "some", "any", "let",
}


def _tokens(text: str) -> set[str]:
    words = normalise(text).split()
    tokens = {w for w in words if w not in _FILLER}
    # "E.C.G" arrives as three single letters; glue such runs back together so
    # a dotted abbreviation still matches its alias.
    run: list[str] = []
    for w in words + [""]:
        if len(w) == 1:
            run.append(w)
        else:
            if len(run) > 1:
                tokens.add("".join(run))
            run = []
    return tokens


def best_finding(query: str, findings: list) -> tuple[object | None, list[str]]:
    """Match a free-text request against a list of Finding objects.

    Scores by how much of the *query* each finding accounts for, not by which
    alias happens to be found first. That distinction matters: "sputum for AFB"
    shares the word "sputum" with the Gram stain but shares three words with
    the AFB test, and returning the wrong result would hand the student a
    fabricated investigation.

    Returns (finding, suggestions). When nothing wins outright, `suggestions`
    holds the near misses so the agent can ask the student to be specific
    rather than inventing a result.
    """
    q = _tokens(query)
    if not q:
        return None, []

    scored: list[tuple[float, object]] = []
    for f in findings:
        candidates = [f.id, f.label, *f.aliases]
        cand_tokens: set[str] = set()
        for c in candidates:
            cand_tokens |= _tokens(c)

        overlap = q & cand_tokens
        if not overlap:
            continue

        score = float(len(overlap))
        # A whole alias appearing verbatim in the request is a strong signal.
        if contains_any(query, candidates):
            score += 3.0
        # Prefer the finding whose own name is most fully covered, so a
        # request for "ECG" beats a test whose alias list merely mentions it.
        score += len(overlap) / max(len(cand_tokens), 1)
        scored.append((score, f))

    if not scored:
        return None, []

    scored.sort(key=lambda s: -s[0])
    if len(scored) == 1 or scored[0][0] - scored[1][0] >= 0.5:
        return scored[0][1], []

    # Ambiguous: two or more findings explain the request equally well.
    return None, [getattr(f, "label", "") for _, f in scored[:4]]


_SPLIT = re.compile(r"\s*(?:,|;|\band\b|\bplus\b|\balso\b|&|\+|\bthen\b)\s*")


def match_all(query: str, findings: list) -> tuple[list, list[str]]:
    """Match a request that may name several things at once.

    Students write "CBC, CRP and blood culture" in one breath. The request is
    split on conjunctions only when *every* fragment resolves confidently on
    its own — otherwise a name that legitimately contains "and", such as
    "sputum Gram stain and culture", would be torn in half.

    Returns (findings, suggestions).
    """
    fragments = [f for f in _SPLIT.split(query or "") if normalise(f)]
    if len(fragments) > 1:
        hits = [best_finding(f, findings)[0] for f in fragments]
        if all(h is not None for h in hits):
            seen: list = []
            for h in hits:
                if h not in seen:
                    seen.append(h)
            return seen, []

    finding, suggestions = best_finding(query, findings)
    return ([finding] if finding else []), suggestions
