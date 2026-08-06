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

"""Stage ② — deterministic scoring (spec C3, Phase 3 §4).

Weights and normalized quantities in; a ranking, the per-dimension
contributions and the arithmetic out. **No model, no network, no state.**
The module imports nothing from `google.adk` and takes no `ToolContext`,
which is what makes "the LLM never touches a number" checkable rather than
promised — `tests/unit/test_scoring.py` asserts it against the import graph.

The rules that matter, and why each exists:

**Missing is never zero.** A program with no published fee does not score
zero on cost; it is *absent* from that dimension. Its total is computed over
the dimensions it actually has, with the weights renormalized to those
dimensions. Scoring `UNKNOWN` as zero would rank a program with no published
fee as the cheapest one available.

**Renormalizing cannot become a free pass.** Averaging over whatever a
program happens to have would let a program with one cheap dimension beat a
fully-documented rival. So a program participating in less than
`PROGRAM_COVERAGE_FLOOR` of the included dimensions is not ranked at all —
it is returned in `unranked` with the reason and the list of what is
missing.

**A thin dimension is excluded, not averaged.** Ranking a dimension where 4
of 6 programs are unknown is noise presented as signal, and is a named C3
failure case.

**Ties stay tied.** Equal totals share a rank. Nothing is broken
arbitrarily to manufacture a strict order.

**Cost never crosses a currency.** There is no exchange rate in this system
by design: an unsourced rate is an unsourced institutional claim wearing a
different hat. Programs quoted in different currencies — or on different
bases — make the cost dimension non-comparable, and it is excluded with that
reason stated.

**Evidence quality rides alongside the score, never inside it.** Folding
"how sure are we" into "which is best" produces one number that answers
neither question. Both are reported separately.
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.normalize import OK, parse_amount
from app.reference.comparison_dimensions import (
    DIMENSION_KEYS,
    DIMENSIONS,
    LOWER_IS_BETTER,
)

VERSION = "scoring:v1"

# A dimension where fewer than half the programs have a comparable value is
# excluded. Below this, the ranking describes coverage rather than quality.
COVERAGE_FLOOR = 0.5

# Two programs is the minimum that can be ranked against each other.
MIN_PROGRAMS_PER_DIMENSION = 2

# A program must participate in at least this share of the included
# dimensions to receive a score at all.
PROGRAM_COVERAGE_FLOOR = 0.5

# Below this, the narration is required to lead with the data limitation
# rather than the ranking (spec C3 evaluation criterion b).
NARRATION_COVERAGE_THRESHOLD = 0.7

# Totals are rounded before comparison so that two programs whose scores
# differ only by float noise are reported as tied rather than ordered.
SCORE_PRECISION = 4

# --- Weight elicitation ----------------------------------------------------

# The qualitative -> numeric mapping, deterministic and shown to the student.
# The model may not invent a weight; it may only pick one of these words.
IMPORTANCE_WEIGHTS: dict[str, float] = {
    "critical": 4.0,
    "very important": 3.0,
    "important": 2.0,
    "slightly important": 1.0,
    "not important": 0.0,
}

IMPORTANCE_WORDS: tuple[str, ...] = tuple(IMPORTANCE_WEIGHTS)

# Applied to any dimension the student did not rank, and reported as having
# been defaulted so the assumption is visible rather than silent.
DEFAULT_IMPORTANCE = "important"


def resolve_weights(weights: dict[str, str] | None) -> dict[str, Any]:
    """Map importance words to numbers, or refuse.

    Returns the numeric weights, which dimensions were defaulted, and the
    mapping itself — C3 requires the mapping to be shown so the student is
    not anchored on a framing they never saw.
    """
    supplied = {
        str(k).strip(): str(v).strip().lower() for k, v in (weights or {}).items()
    }

    unknown_dimensions = sorted(set(supplied) - set(DIMENSION_KEYS))
    if unknown_dimensions:
        return {
            "status": "error",
            "reason": "unknown_dimension",
            "message": (
                f"Not comparison dimensions: {', '.join(unknown_dimensions)}. "
                f"Known dimensions: {', '.join(DIMENSION_KEYS)}."
            ),
        }

    bad_words = sorted({w for w in supplied.values() if w not in IMPORTANCE_WEIGHTS})
    if bad_words:
        return {
            "status": "error",
            "reason": "unknown_importance",
            "message": (
                f"Not importance levels: {', '.join(bad_words)}. Use one of: "
                f"{', '.join(IMPORTANCE_WORDS)}. Do not invent a numeric weight."
            ),
        }

    resolved: dict[str, float] = {}
    defaulted: list[str] = []
    for key in DIMENSION_KEYS:
        word = supplied.get(key)
        if word is None:
            word = DEFAULT_IMPORTANCE
            defaulted.append(key)
        resolved[key] = IMPORTANCE_WEIGHTS[word]

    return {
        "status": "success",
        "weights": resolved,
        "importance_words": {
            key: supplied.get(key, DEFAULT_IMPORTANCE) for key in DIMENSION_KEYS
        },
        "defaulted_dimensions": defaulted,
        "mapping_shown": dict(IMPORTANCE_WEIGHTS),
    }


# --- Comparability ---------------------------------------------------------


def comparability_of(dimension_key: str, entry: dict[str, Any]) -> dict[str, Any]:
    """The keys that must match across programs for this value to be ranked."""
    dimension = DIMENSIONS[dimension_key]
    if not dimension.comparability_keys:
        return {}
    return {
        "currency": entry.get("unit"),
        "basis": entry.get("basis"),
    }


def _numeric(entry: dict[str, Any]) -> float:
    """The comparable float behind a normalized value."""
    value = entry.get("value")
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    return float(value)


# --- Scoring ---------------------------------------------------------------


def score_programs(
    normalized_programs: list[dict[str, Any]],
    weights: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Rank normalized programs against weighted dimensions.

    `normalized_programs` is a list of `normalize.normalize_program` outputs.
    Nothing else is read: no state, no session, no retrieval. The same inputs
    always produce byte-identical output.
    """
    programs = list(normalized_programs or [])
    if len(programs) < 2:
        return {
            "status": "error",
            "reason": "not_enough_programs",
            "message": (
                "At least two researched programs are needed to compare. "
                f"Currently: {len(programs)}."
            ),
            "program_count": len(programs),
        }

    resolved = resolve_weights(weights)
    if resolved["status"] != "success":
        return resolved

    numeric_weights: dict[str, float] = resolved["weights"]
    total_programs = len(programs)

    included: dict[str, dict[str, Any]] = {}
    excluded: list[dict[str, Any]] = []

    for key in DIMENSION_KEYS:
        dimension = DIMENSIONS[key]
        weight = numeric_weights[key]

        entries = [
            (p, p["dimensions"][key])
            for p in programs
            if p.get("dimensions", {}).get(key, {}).get("status") == OK
        ]
        coverage = round(len(entries) / total_programs, SCORE_PRECISION)

        def exclude(
            reason: str,
            message: str,
            # Bound at definition rather than captured, so the record always
            # describes the dimension it was built for.
            key: str = key,
            label: str = dimension.label,
            coverage: float = coverage,
            found: int = len(entries),
        ) -> None:
            excluded.append(
                {
                    "dimension": key,
                    "label": label,
                    "reason": reason,
                    "message": message,
                    "coverage": coverage,
                    "programs_with_a_value": found,
                    "programs_total": total_programs,
                }
            )

        if weight == 0.0:
            exclude(
                "weight_zero",
                f"The student rated {dimension.label.lower()} as not important.",
            )
            continue

        if len(entries) < MIN_PROGRAMS_PER_DIMENSION:
            exclude(
                "too_few_values",
                (
                    f"Only {len(entries)} of {total_programs} programs have a "
                    f"comparable {dimension.label.lower()}; at least "
                    f"{MIN_PROGRAMS_PER_DIMENSION} are needed to rank."
                ),
            )
            continue

        if coverage < COVERAGE_FLOOR:
            exclude(
                "below_coverage_floor",
                (
                    f"Only {len(entries)} of {total_programs} programs have a "
                    f"comparable {dimension.label.lower()} (coverage "
                    f"{coverage}, floor {COVERAGE_FLOOR}). Ranking on it would "
                    "present a coverage gap as a quality difference."
                ),
            )
            continue

        signatures = {
            json.dumps(comparability_of(key, entry), sort_keys=True)
            for _, entry in entries
        }
        if len(signatures) > 1:
            found = sorted(f"{e.get('unit')}/{e.get('basis')}" for _, e in entries)
            exclude(
                "not_comparable",
                (
                    f"These {dimension.label.lower()} figures are quoted "
                    f"differently ({', '.join(found)}). There is no exchange "
                    "rate in this system, and converting on an unsourced rate "
                    "would be inventing a number. Compare within one currency "
                    "and basis, or treat this dimension as informational."
                ),
            )
            continue

        values = [_numeric(entry) for _, entry in entries]
        low, high = min(values), max(values)
        included[key] = {
            "dimension": dimension,
            "weight": weight,
            "coverage": coverage,
            "low": low,
            "high": high,
            "no_variation": high == low,
            "participants": {p["program_id"] for p, _ in entries},
        }

    if not included:
        return {
            "status": "insufficient_data",
            "reason": "no_scoreable_dimension",
            "message": (
                "No dimension has enough comparable data to rank these "
                "programs. Nothing is ranked; the excluded dimensions below "
                "say what is missing."
            ),
            "program_count": total_programs,
            "excluded_dimensions": excluded,
            "weights": resolved,
            "scorer_version": VERSION,
        }

    scored: list[dict[str, Any]] = []
    unranked: list[dict[str, Any]] = []

    for program in programs:
        contributions: dict[str, Any] = {}
        points = 0.0
        weight_used = 0.0
        participating: list[str] = []
        missing: list[dict[str, Any]] = []

        for key, spec in included.items():
            entry = program["dimensions"][key]
            if entry.get("status") != OK:
                missing.append(
                    {
                        "dimension": key,
                        "status": entry.get("status"),
                        "reason": entry.get("reason"),
                        "published_value": entry.get("published_value"),
                    }
                )
                continue

            raw = _numeric(entry)
            if spec["no_variation"]:
                # Every program agrees, so the dimension separates nobody.
                normalized = 1.0
            elif spec["dimension"].direction == LOWER_IS_BETTER:
                normalized = (spec["high"] - raw) / (spec["high"] - spec["low"])
            else:
                normalized = (raw - spec["low"]) / (spec["high"] - spec["low"])

            normalized = round(normalized, SCORE_PRECISION)
            contribution = round(normalized * spec["weight"], SCORE_PRECISION)
            points += contribution
            weight_used += spec["weight"]
            participating.append(key)

            provenance = entry.get("provenance") or {}
            contributions[key] = {
                "raw_value": raw,
                "unit": entry.get("unit"),
                "published_value": entry.get("published_value"),
                "normalized": normalized,
                "weight": spec["weight"],
                "points": contribution,
                "direction": spec["dimension"].direction,
                "rule_id": entry.get("rule_id"),
                # Provenance follows the number all the way into the score.
                "source_domain": provenance.get("source_domain"),
                "source_is_official": provenance.get("source_is_official"),
                "tier": provenance.get("tier"),
                "retrieved_at": provenance.get("retrieved_at"),
                "is_stale": provenance.get("is_stale"),
                "staleness_notice": provenance.get("staleness_notice"),
                "has_conflict": provenance.get("has_conflict"),
                "conflicting_values": provenance.get("conflicting_values"),
                "source_count": provenance.get("source_count"),
            }

        program_coverage = round(len(participating) / len(included), SCORE_PRECISION)
        record = {
            "program_id": program.get("program_id"),
            "university": program.get("university"),
            "program": program.get("program"),
            "contributions": contributions,
            "missing_dimensions": missing,
            "dimension_coverage": program_coverage,
            "evidence": _evidence_summary(contributions),
        }

        if weight_used == 0.0 or program_coverage < PROGRAM_COVERAGE_FLOOR:
            record["reason"] = "insufficient_data"
            record["message"] = (
                f"Has a comparable value for {len(participating)} of "
                f"{len(included)} scored dimensions (floor "
                f"{PROGRAM_COVERAGE_FLOOR}). Scoring it against the others "
                "would compare a well-documented program with a mostly "
                "unknown one and present the gap as a difference in quality."
            )
            unranked.append(record)
            continue

        record["total"] = round(points / weight_used, SCORE_PRECISION)
        record["points"] = round(points, SCORE_PRECISION)
        record["weight_used"] = round(weight_used, SCORE_PRECISION)
        record["arithmetic"] = _arithmetic(contributions, points, weight_used)
        scored.append(record)

    # Sorted by score, then by id so that equal scores always come out in the
    # same order rather than in whatever order the shortlist happened to hold.
    scored.sort(key=lambda r: (-r["total"], str(r["program_id"])))

    ranking: list[dict[str, Any]] = []
    for index, record in enumerate(scored):
        if index > 0 and record["total"] == scored[index - 1]["total"]:
            rank = ranking[-1]["rank"]  # competition ranking: 1, 1, 3
        else:
            rank = index + 1
        record["rank"] = rank
        ranking.append(
            {
                "rank": rank,
                "program_id": record["program_id"],
                "university": record["university"],
                "program": record["program"],
                "total": record["total"],
            }
        )

    by_total: dict[float, list[str]] = {}
    for record in scored:
        by_total.setdefault(record["total"], []).append(str(record["program_id"]))
    ties = [sorted(ids) for total, ids in sorted(by_total.items()) if len(ids) > 1]

    coverage = {key: spec["coverage"] for key, spec in included.items()}
    thin = sorted(k for k, v in coverage.items() if v < NARRATION_COVERAGE_THRESHOLD)

    return {
        "status": "success",
        "program_count": total_programs,
        "ranking": ranking,
        "programs": scored,
        "unranked": unranked,
        "coverage": coverage,
        "included_dimensions": sorted(included),
        "excluded_dimensions": excluded,
        "ties": ties,
        "weights": resolved,
        "narration_requirements": {
            "coverage_threshold": NARRATION_COVERAGE_THRESHOLD,
            "thin_dimensions": thin,
            "must_lead_with_limitations": bool(thin) or bool(unranked),
        },
        "scorer_version": VERSION,
        "method": (
            "Each dimension is scaled 0-1 across the programs that have a "
            "comparable value (best = 1). Each program's total is the "
            "weighted mean over the dimensions it actually has, so a missing "
            "value neither helps nor hurts it. Totals are rounded to "
            f"{SCORE_PRECISION} decimal places before ranking."
        ),
    }


def _evidence_summary(contributions: dict[str, Any]) -> dict[str, Any]:
    """Evidence quality, reported beside the score and never folded into it."""
    values = list(contributions.values())
    return {
        "verified_inputs": sum(1 for c in values if c.get("tier") == "VERIFIED"),
        "reported_inputs": sum(1 for c in values if c.get("tier") == "REPORTED"),
        "stale_inputs": sum(1 for c in values if c.get("is_stale")),
        "conflicted_inputs": sorted(
            key for key, c in contributions.items() if c.get("has_conflict")
        ),
        "official_source_share": (
            round(
                sum(1 for c in values if c.get("source_is_official")) / len(values),
                SCORE_PRECISION,
            )
            if values
            else None
        ),
    }


def _arithmetic(
    contributions: dict[str, Any], points: float, weight_used: float
) -> list[str]:
    """The derivation, in a form a student can redo by hand."""
    lines = [
        f"{key}: {c['normalized']} x weight {c['weight']} = {c['points']}"
        for key, c in sorted(contributions.items())
    ]
    lines.append(
        f"total = {round(points, SCORE_PRECISION)} / {round(weight_used, SCORE_PRECISION)}"
        f" = {round(points / weight_used, SCORE_PRECISION)}"
    )
    return lines


# --- Explanation integrity -------------------------------------------------

_NUMBER = re.compile(r"\d[\d.,]*\d|\d")


def _readings(token: str) -> set[float]:
    """Every honest numeric reading of a written number.

    A model narrating a stored `22290` will write `22,290` for a human, and
    a naive parser reads that as 22.29 and reports a fabrication. So each
    token is read every defensible way — bare, thousands-grouped, and
    through `parse_amount`, which already owns the separator convention for
    the whole codebase — and any match is accepted.

    This is deliberately permissive about *formatting* and not at all
    permissive about *provenance*: a number that appears nowhere in the
    scorer's output has no reading that matches, and still fails.
    """
    out: set[float] = set()
    for candidate in (token, token.replace(",", "")):
        try:
            out.add(float(candidate))
        except ValueError:
            continue
    parsed = parse_amount(token)
    if parsed.get("status") == OK:
        out.add(parsed["amount"])
    return out


def _collect_numbers(payload: Any, into: set[float]) -> None:
    if isinstance(payload, bool):
        return
    if isinstance(payload, (int, float)):
        into.add(float(payload))
    elif isinstance(payload, str):
        for token in _NUMBER.findall(payload):
            into |= _readings(token)
    elif isinstance(payload, dict):
        for value in payload.values():
            _collect_numbers(value, into)
    elif isinstance(payload, (list, tuple)):
        for value in payload:
            _collect_numbers(value, into)


def explanation_integrity(narration: str, result: dict[str, Any]) -> dict[str, Any]:
    """Check that a narration introduces no number the scorer did not produce.

    The C3 analogue of C2's quote verification: there, a value had to appear
    in its supporting quote; here, a number in the explanation has to appear
    in the scoring result. The scorer is authoritative for numbers, and this
    is how that is checked rather than merely instructed.

    Rounded and percentage restatements are accepted — "0.8571" narrated as
    "0.86" or "86%" is the same number, presented for a human.
    """
    allowed: set[float] = set()
    _collect_numbers(result, allowed)

    permitted: set[float] = set()
    for value in allowed:
        permitted.add(value)
        for places in range(5):
            permitted.add(round(value, places))
        permitted.add(round(value * 100, 2))
        permitted.add(float(round(value * 100)))

    unsupported: list[str] = []
    for token in _NUMBER.findall(narration or ""):
        readings = _readings(token)
        if not readings:
            continue
        if not any(
            abs(number - candidate) < 1e-9
            for number in readings
            for candidate in permitted
        ):
            unsupported.append(token)

    return {
        "ok": not unsupported,
        "unsupported_numbers": unsupported,
        "message": (
            "Every number in the explanation appears in the scoring result."
            if not unsupported
            else (
                "The explanation contains numbers the scorer never produced: "
                f"{', '.join(unsupported)}. The scorer is authoritative for "
                "numbers; the explanation may only restate them."
            )
        ),
    }
