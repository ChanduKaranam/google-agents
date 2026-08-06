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

"""C3 comparison tools — the three the spec §4.2 inventory names.

These are a thin state-reading shell over two pure modules. All three:

* read `user:shortlist` and `user:profile`, and **write nothing**;
* never retrieve — C3 compares what C2 already found, and a gap stays a gap
  (spec §5.2 invariant 3);
* never call a model. The arithmetic happens in `app.scoring`, which cannot
  even import ADK.

The division is deliberate. `app.normalize` and `app.scoring` are pure and
exhaustively unit-tested; this module only moves data between ADK state and
those functions, so there is very little here that can be wrong in a way a
test would not catch.
"""

from __future__ import annotations

from typing import Any

from google.adk.tools import ToolContext

from app import scoring
from app.config import STATE_PROFILE, STATE_SHORTLIST
from app.normalize import OK, normalize_program
from app.profile_store import read_profile
from app.program_store import read_shortlist, render_shortlist
from app.reference.comparison_dimensions import (
    DIMENSION_KEYS,
    DIMENSIONS,
    DISPLAY_ONLY_FIELDS,
)
from app.schemas import DimensionWeight


def _intake_year(state: Any) -> int | None:
    """The student's target intake year, if they have stated one.

    Needed to resolve a deadline that names no year. Absent, such deadlines
    stay ambiguous rather than being assumed into an admissions cycle.
    """
    profile = read_profile(state, STATE_PROFILE)
    entry = (profile.get("fields") or {}).get("target_intake_year") or {}
    try:
        return int(str(entry.get("value")).strip())
    except (TypeError, ValueError):
        return None


def _normalized(state: Any) -> list[dict[str, Any]]:
    shortlist = render_shortlist(read_shortlist(state, STATE_SHORTLIST))
    year = _intake_year(state)
    return [normalize_program(p, intake_year=year) for p in shortlist["programs"]]


def build_comparison_matrix(tool_context: ToolContext) -> dict:
    """Build the programs x dimensions comparison table.

    Every cell carries the value as the source published it, the normalized
    value where one could be computed, the tier, the source domain and the
    retrieval date. A cell that could not be normalized says why in plain
    words rather than going blank — "the fee is quoted per semester and the
    number of semesters is not published" is a useful answer.

    Reads only what C2 already stored. It never searches, so a missing fact
    stays missing.

    Returns:
        A dict with one row per program, each dimension's normalized status,
        and the deadline shown separately as information rather than a
        ranking criterion.
    """
    programs = _normalized(tool_context.state)
    if not programs:
        return {
            "status": "empty",
            "message": (
                "No programs have been researched yet. Research at least two "
                "before comparing."
            ),
            "program_count": 0,
        }

    rows: list[dict[str, Any]] = []
    for program in programs:
        cells: dict[str, Any] = {}
        for key in DIMENSION_KEYS:
            entry = program["dimensions"][key]
            provenance = entry.get("provenance") or {}
            cells[key] = {
                "published_value": entry.get("published_value"),
                "normalized_value": entry.get("value"),
                "unit": entry.get("unit"),
                "status": entry.get("status"),
                "reason": entry.get("reason"),
                "tier": provenance.get("tier") or "UNKNOWN",
                "source_domain": provenance.get("source_domain"),
                "source_is_official": provenance.get("source_is_official"),
                "retrieved_at": provenance.get("retrieved_at"),
                "is_stale": provenance.get("is_stale"),
                "staleness_notice": provenance.get("staleness_notice"),
                "has_conflict": provenance.get("has_conflict"),
                "conflicting_values": provenance.get("conflicting_values"),
            }

        deadline = program["display_only"]["application_deadline"]
        rows.append(
            {
                "program_id": program["program_id"],
                "university": program["university"],
                "program": program["program"],
                "dimensions": cells,
                "application_deadline": {
                    "published_value": deadline.get("published_value"),
                    "normalized_date": deadline.get("value"),
                    "status": deadline.get("status"),
                    "reason": deadline.get("reason"),
                    "year_caveat": deadline.get("year_caveat"),
                },
                "tuition_academic_year": program["tuition_academic_year"],
                "unknown_fields": program["unknown_fields"],
                "stale_fields": program["stale_fields"],
            }
        )

    return {
        "status": "success",
        "program_count": len(rows),
        "programs": rows,
        "dimensions": {
            key: {
                "label": DIMENSIONS[key].label,
                "direction": DIMENSIONS[key].direction,
                "description": DIMENSIONS[key].description,
            }
            for key in DIMENSION_KEYS
        },
        "not_scored": DISPLAY_ONLY_FIELDS,
        "note": (
            "Published values are what the source said. Normalized values are "
            "derived and are labelled INFERENCE. A cell with a status other "
            "than 'ok' has no comparable value and is excluded from scoring."
        ),
    }


def score_programs(weights: list[DimensionWeight], tool_context: ToolContext) -> dict:
    """Rank the researched programs against the student's stated priorities.

    The ranking is computed in Python, not by you. Report the numbers this
    returns exactly as given: do not recompute them, do not round them into
    different figures, do not reorder the ranking, and do not break a tie
    that this tool reports as tied.

    Call this only after the student has told you what matters to them. Do
    not guess their priorities; ask.

    Args:
        weights: How much each dimension matters, using the importance words
            'critical', 'very important', 'important', 'slightly important'
            or 'not important'. Dimensions you omit default to 'important'
            and are reported as defaulted.

    Returns:
        The ranking, each program's per-dimension contributions, the
        arithmetic, the dimensions excluded and why, any ties, and any
        programs with too little data to rank.
    """
    supplied: dict[str, str] = {}
    for raw in weights or []:
        item = (
            raw
            if isinstance(raw, DimensionWeight)
            else DimensionWeight.model_validate(raw)
        )
        supplied[item.dimension.strip()] = item.importance

    programs = _normalized(tool_context.state)
    result = scoring.score_programs(programs, supplied)

    if (
        result.get("status") == "error"
        and result.get("reason") == "not_enough_programs"
    ):
        result["message"] += (
            " Research more programs with the research agent before comparing."
        )
    return result


def explain_ranking_inputs(tool_context: ToolContext) -> dict:
    """Report what can and cannot be compared, before any ranking happens.

    Use this to decide what to ask the student and what still needs
    researching. It names, per dimension, how many programs have a usable
    value and what is blocking the rest — so you can say "I can compare on
    length but not cost, because two of these publish fees per semester"
    instead of producing a ranking that quietly rests on two data points.

    Returns:
        Per-dimension readiness, the importance vocabulary and its numeric
        mapping, and the specific reasons values were not usable.
    """
    programs = _normalized(tool_context.state)
    total = len(programs)

    readiness: dict[str, Any] = {}
    for key in DIMENSION_KEYS:
        usable: list[str] = []
        blocked: list[dict[str, Any]] = []
        for program in programs:
            entry = program["dimensions"][key]
            if entry.get("status") == OK:
                usable.append(str(program["program_id"]))
            else:
                blocked.append(
                    {
                        "program_id": program["program_id"],
                        "status": entry.get("status"),
                        "reason": entry.get("reason"),
                        "published_value": entry.get("published_value"),
                    }
                )

        coverage = round(len(usable) / total, 4) if total else 0.0
        readiness[key] = {
            "label": DIMENSIONS[key].label,
            "description": DIMENSIONS[key].description,
            "programs_with_a_usable_value": len(usable),
            "programs_total": total,
            "coverage": coverage,
            "would_be_scored": (
                total >= 2
                and len(usable) >= scoring.MIN_PROGRAMS_PER_DIMENSION
                and coverage >= scoring.COVERAGE_FLOOR
            ),
            "blocked": blocked,
        }

    return {
        "status": "success" if total >= 2 else "insufficient_programs",
        "program_count": total,
        "dimensions": readiness,
        "importance_vocabulary": list(scoring.IMPORTANCE_WORDS),
        "importance_mapping": dict(scoring.IMPORTANCE_WEIGHTS),
        "default_importance": scoring.DEFAULT_IMPORTANCE,
        "coverage_floor": scoring.COVERAGE_FLOOR,
        "program_coverage_floor": scoring.PROGRAM_COVERAGE_FLOOR,
        "not_scored": DISPLAY_ONLY_FIELDS,
        "note": (
            "Ask the student how much each dimension matters, in their own "
            "words, and map it to one of the importance words. Never invent "
            "a weight, and never present the dimension list as a form."
        ),
    }
