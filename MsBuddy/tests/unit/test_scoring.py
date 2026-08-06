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

"""Stage ② deterministic scoring.

Every test here is arithmetic over fixed inputs, so every one of them is a
pytest assertion rather than an eval question. That is the point of putting
the ranking in Python: spec C3 evaluation criterion (a).
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest

from app.normalize import normalize_program
from app.scoring import (
    COVERAGE_FLOOR,
    IMPORTANCE_WEIGHTS,
    PROGRAM_COVERAGE_FLOOR,
    explanation_integrity,
    resolve_weights,
    score_programs,
)

FRESH = "2026-07-30T10:00:00+00:00"


def rendered(program_id: str, **fields: str) -> dict:
    return {
        "program_id": program_id,
        "university": f"University {program_id.upper()}",
        "program": "MSc CS",
        "fields": {
            name: {
                "value": value,
                "tier": "VERIFIED",
                "source_domain": "example.edu",
                "source_is_official": True,
                "retrieved_at": FRESH,
                "staleness_class": "CYCLICAL",
                "is_stale": False,
                "staleness_notice": None,
                "supporting_quote": f"{name} is {value}",
                "conflicts": [],
                "corroborations": [],
                "source_count": 1,
            }
            for name, value in fields.items()
        },
        "unknown_fields": [],
        "stale_fields": [],
    }


def program(program_id: str, **fields: str) -> dict:
    return normalize_program(rendered(program_id, **fields))


def euros(program_id: str, amount: str, duration: str = "2 years") -> dict:
    return program(
        program_id,
        tuition_amount=amount,
        tuition_currency="EUR",
        tuition_basis="per year",
        duration=duration,
    )


COST_ONLY = {"cost": "critical", "duration": "not important",
             "stem": "not important", "test_burden": "not important"}  # fmt: skip
COST_AND_DURATION = {"cost": "important", "duration": "important",
                     "stem": "not important", "test_burden": "not important"}  # fmt: skip


# --- Weight elicitation ----------------------------------------------------


def test_importance_words_map_to_fixed_numbers() -> None:
    resolved = resolve_weights({"cost": "critical", "duration": "not important"})
    assert resolved["status"] == "success"
    assert resolved["weights"]["cost"] == 4.0
    assert resolved["weights"]["duration"] == 0.0


def test_unranked_dimensions_default_and_say_so() -> None:
    resolved = resolve_weights({"cost": "critical"})
    assert set(resolved["defaulted_dimensions"]) == {"duration", "stem", "test_burden"}
    assert resolved["weights"]["stem"] == IMPORTANCE_WEIGHTS["important"]


def test_the_mapping_is_returned_so_it_can_be_shown() -> None:
    assert resolve_weights({})["mapping_shown"] == IMPORTANCE_WEIGHTS


def test_an_invented_numeric_weight_is_refused() -> None:
    result = resolve_weights({"cost": "0.8"})
    assert result["status"] == "error"
    assert result["reason"] == "unknown_importance"
    assert "Do not invent a numeric weight" in result["message"]


def test_an_unknown_dimension_is_refused() -> None:
    result = resolve_weights({"prestige": "critical"})
    assert result["status"] == "error"
    assert result["reason"] == "unknown_dimension"


# --- Basic ranking ---------------------------------------------------------


def test_the_cheaper_program_ranks_first_on_cost() -> None:
    result = score_programs([euros("a", "30000"), euros("b", "20000")], COST_ONLY)
    assert result["status"] == "success"
    assert [r["program_id"] for r in result["ranking"]] == ["b", "a"]
    assert result["ranking"][0]["rank"] == 1


def test_a_zero_weighted_dimension_is_excluded_with_that_reason() -> None:
    result = score_programs([euros("a", "30000"), euros("b", "20000")], COST_ONLY)
    reasons = {e["dimension"]: e["reason"] for e in result["excluded_dimensions"]}
    assert reasons["duration"] == "weight_zero"


# --- Missing is never zero -------------------------------------------------


def test_a_missing_value_is_not_scored_as_zero() -> None:
    """The defect this rule exists to prevent.

    `c` publishes no fee. Scored as zero it would rank last on cost; scored
    as absent it is ranked on the dimension it does have. The two produce
    visibly different totals, which is what makes the rule testable.
    """
    result = score_programs(
        [
            euros("a", "10000"),
            euros("b", "50000"),
            program("c", duration="2 years"),
        ],
        COST_AND_DURATION,
    )
    totals = {r["program_id"]: r["total"] for r in result["ranking"]}

    # a is cheapest (cost 1.0) and every duration is equal (1.0)  -> 1.0
    # b is dearest (cost 0.0), duration 1.0, equal weights        -> 0.5
    # c has no cost at all, so it is scored on duration alone     -> 1.0
    assert totals["a"] == 1.0
    assert totals["b"] == 0.5
    assert totals["c"] == 1.0, "a missing fee was scored as if it were zero"

    record = next(p for p in result["programs"] if p["program_id"] == "c")
    assert "cost" not in record["contributions"]
    assert [m["dimension"] for m in record["missing_dimensions"]] == ["cost"]
    assert record["weight_used"] == 2.0


def test_a_missing_value_never_becomes_a_cheapest_claim() -> None:
    """A program with no published fee must not out-rank a documented cheap one."""
    result = score_programs(
        [euros("cheap", "10000"), euros("dear", "50000"), program("silent")],
        COST_ONLY,
    )
    ranked = [r["program_id"] for r in result["ranking"]]
    assert "silent" not in ranked, "a program with no data entered the ranking"
    assert ranked[0] == "cheap"


def test_a_program_below_the_coverage_floor_is_unranked_with_a_reason() -> None:
    result = score_programs(
        [euros("a", "10000"), euros("b", "50000"), program("silent")],
        COST_AND_DURATION,
    )
    unranked = {u["program_id"]: u for u in result["unranked"]}
    assert "silent" in unranked
    assert unranked["silent"]["reason"] == "insufficient_data"
    assert unranked["silent"]["dimension_coverage"] < PROGRAM_COVERAGE_FLOOR
    assert "total" not in unranked["silent"]


def test_program_coverage_is_reported_for_every_ranked_program() -> None:
    result = score_programs(
        [euros("a", "10000"), euros("b", "50000"), program("c", duration="2 years")],
        COST_AND_DURATION,
    )
    coverage = {p["program_id"]: p["dimension_coverage"] for p in result["programs"]}
    assert coverage["a"] == 1.0
    assert coverage["c"] == 0.5


# --- Coverage floor and exclusions -----------------------------------------


def test_a_dimension_below_the_coverage_floor_is_excluded() -> None:
    """Spec C3 failure case: ranking where 4 of 6 programs are UNKNOWN."""
    programs = [euros(f"p{i}", "20000") for i in range(2)] + [
        program(f"q{i}", duration="2 years") for i in range(4)
    ]
    result = score_programs(programs, COST_AND_DURATION)
    excluded = {e["dimension"]: e for e in result["excluded_dimensions"]}
    assert excluded["cost"]["reason"] == "below_coverage_floor"
    assert excluded["cost"]["coverage"] == pytest.approx(2 / 6, abs=1e-4)
    assert excluded["cost"]["coverage"] < COVERAGE_FLOOR
    assert "cost" not in result["included_dimensions"]


def test_a_dimension_with_one_value_cannot_be_ranked() -> None:
    result = score_programs(
        [euros("a", "20000"), program("b", duration="2 years")], COST_AND_DURATION
    )
    excluded = {e["dimension"]: e for e in result["excluded_dimensions"]}
    assert excluded["cost"]["reason"] == "too_few_values"
    assert excluded["cost"]["programs_with_a_value"] == 1


def test_every_excluded_dimension_carries_an_explicit_reason() -> None:
    result = score_programs([euros("a", "20000"), euros("b", "30000")], None)
    for entry in result["excluded_dimensions"]:
        assert entry["reason"]
        assert entry["message"]
        assert entry["coverage"] is not None


# --- Currency and basis ----------------------------------------------------


def test_different_currencies_make_cost_non_comparable() -> None:
    """No exchange rate exists in this system, by design."""
    a = program("a", tuition_amount="20000", tuition_currency="EUR",
                tuition_basis="per year", duration="2 years")  # fmt: skip
    b = program("b", tuition_amount="20000", tuition_currency="USD",
                tuition_basis="per year", duration="2 years")  # fmt: skip
    result = score_programs([a, b], COST_AND_DURATION)
    excluded = {e["dimension"]: e for e in result["excluded_dimensions"]}
    assert excluded["cost"]["reason"] == "not_comparable"
    assert "exchange rate" in excluded["cost"]["message"]
    assert "cost" not in result["included_dimensions"]


def test_different_bases_make_cost_non_comparable() -> None:
    """CHF 1460 per semester against EUR 22290 per year is not a comparison."""
    a = program("a", tuition_amount="20000", tuition_currency="EUR",
                tuition_basis="per year", duration="2 years")  # fmt: skip
    b = program("b", tuition_amount="1460", tuition_currency="EUR",
                tuition_basis="per semester", duration="2 years")  # fmt: skip
    result = score_programs([a, b], COST_AND_DURATION)
    excluded = {e["dimension"]: e for e in result["excluded_dimensions"]}
    assert excluded["cost"]["reason"] == "not_comparable"


def test_same_currency_and_basis_compares_normally() -> None:
    result = score_programs([euros("a", "20000"), euros("b", "30000")], COST_ONLY)
    assert "cost" in result["included_dimensions"]


# --- Ties ------------------------------------------------------------------


def test_equal_values_produce_a_tie() -> None:
    result = score_programs([euros("a", "20000"), euros("b", "20000")], COST_ONLY)
    assert [r["rank"] for r in result["ranking"]] == [1, 1]
    assert result["ties"] == [["a", "b"]]


def test_equal_scores_from_different_values_produce_a_tie() -> None:
    """a is cheaper, b is shorter, weights equal — neither wins."""
    a = euros("a", "10000", duration="2 years")
    b = euros("b", "50000", duration="1 year")
    result = score_programs([a, b], COST_AND_DURATION)
    assert result["ranking"][0]["total"] == result["ranking"][1]["total"] == 0.5
    assert result["ties"] == [["a", "b"]]
    assert [r["rank"] for r in result["ranking"]] == [1, 1]


def test_a_tie_is_not_broken_into_a_strict_order() -> None:
    result = score_programs(
        [euros("a", "20000"), euros("b", "20000"), euros("c", "50000")], COST_ONLY
    )
    ranks = {r["program_id"]: r["rank"] for r in result["ranking"]}
    assert ranks["a"] == ranks["b"] == 1
    assert ranks["c"] == 3, "competition ranking: a tie for first leaves rank 2 empty"


def test_a_dimension_where_everyone_agrees_separates_nobody() -> None:
    result = score_programs([euros("a", "20000"), euros("b", "20000")], COST_ONLY)
    for record in result["programs"]:
        assert record["contributions"]["cost"]["normalized"] == 1.0


# --- Arithmetic, determinism, reproducibility ------------------------------


def test_the_arithmetic_reproduces_the_total() -> None:
    result = score_programs(
        [euros("a", "10000"), euros("b", "50000")], COST_AND_DURATION
    )
    for record in result["programs"]:
        lines = record["arithmetic"]
        assert lines, "no derivation was emitted"

        recomputed = 0.0
        for line in lines[:-1]:
            match = re.match(r".*: ([\d.]+) x weight ([\d.]+) = ([\d.]+)$", line)
            assert match, line
            normalized, weight, points = (float(g) for g in match.groups())
            assert normalized * weight == pytest.approx(points, abs=1e-4)
            recomputed += points

        total_line = lines[-1]
        match = re.match(r"total = ([\d.]+) / ([\d.]+) = ([\d.]+)$", total_line)
        assert match, total_line
        points, weight_used, total = (float(g) for g in match.groups())
        assert recomputed == pytest.approx(points, abs=1e-4)
        assert points / weight_used == pytest.approx(total, abs=1e-4)
        assert total == pytest.approx(record["total"], abs=1e-4)


def test_scoring_is_reproducible_byte_for_byte() -> None:
    programs = [euros("a", "10000"), euros("b", "50000"), euros("c", "30000")]
    first = json.dumps(
        score_programs(programs, COST_AND_DURATION), sort_keys=True, default=str
    )
    second = json.dumps(
        score_programs(programs, COST_AND_DURATION), sort_keys=True, default=str
    )
    assert first == second


def test_the_ranking_does_not_depend_on_input_order() -> None:
    programs = [euros("a", "10000"), euros("b", "50000"), euros("c", "30000")]
    forward = score_programs(programs, COST_AND_DURATION)["ranking"]
    backward = score_programs(list(reversed(programs)), COST_AND_DURATION)["ranking"]
    assert [r["program_id"] for r in forward] == [r["program_id"] for r in backward]


def test_tied_programs_come_out_in_a_stable_order() -> None:
    a, b = euros("a", "20000"), euros("b", "20000")
    assert [r["program_id"] for r in score_programs([a, b], COST_ONLY)["ranking"]] == [
        r["program_id"] for r in score_programs([b, a], COST_ONLY)["ranking"]
    ]


def test_scaling_every_weight_leaves_the_order_unchanged() -> None:
    programs = [euros("a", "10000"), euros("b", "50000"), euros("c", "30000")]
    small = score_programs(programs, {"cost": "slightly important", "duration": "slightly important",
                                      "stem": "not important", "test_burden": "not important"})  # fmt: skip
    large = score_programs(programs, {"cost": "critical", "duration": "critical",
                                      "stem": "not important", "test_burden": "not important"})  # fmt: skip
    assert [r["program_id"] for r in small["ranking"]] == [
        r["program_id"] for r in large["ranking"]
    ]


# --- Insufficient data -----------------------------------------------------


def test_one_program_is_not_a_comparison() -> None:
    result = score_programs([euros("a", "20000")], COST_ONLY)
    assert result["status"] == "error"
    assert result["reason"] == "not_enough_programs"


def test_no_programs_at_all() -> None:
    assert score_programs([], COST_ONLY)["status"] == "error"


def test_nothing_scoreable_produces_no_ranking_at_all() -> None:
    result = score_programs([program("a"), program("b")], COST_AND_DURATION)
    assert result["status"] == "insufficient_data"
    assert "ranking" not in result
    assert result["excluded_dimensions"]


def test_narration_is_told_to_lead_with_limitations_when_data_is_thin() -> None:
    result = score_programs(
        [euros("a", "10000"), euros("b", "50000"), program("c", duration="2 years")],
        COST_AND_DURATION,
    )
    assert result["narration_requirements"]["must_lead_with_limitations"] is True
    assert "cost" in result["narration_requirements"]["thin_dimensions"]


# --- Provenance survives into the score ------------------------------------


def test_every_contribution_cites_its_source() -> None:
    result = score_programs(
        [euros("a", "10000"), euros("b", "50000")], COST_AND_DURATION
    )
    for record in result["programs"]:
        for key, contribution in record["contributions"].items():
            assert contribution["source_domain"] == "example.edu", key
            assert contribution["tier"] == "VERIFIED"
            assert contribution["retrieved_at"] == FRESH
            assert contribution["published_value"] is not None
            assert contribution["rule_id"]


def test_evidence_quality_is_reported_beside_the_score_not_inside_it() -> None:
    result = score_programs(
        [euros("a", "10000"), euros("b", "50000")], COST_AND_DURATION
    )
    record = result["programs"][0]
    assert record["evidence"]["verified_inputs"] == 2
    assert record["evidence"]["official_source_share"] == 1.0
    # The score is the weighted mean of the normalized values and nothing
    # else; evidence quality does not move it.
    assert record["total"] in (0.0, 0.5, 1.0)


def test_a_conflicted_input_is_surfaced_not_silently_resolved() -> None:
    a = rendered("a", tuition_amount="10000", tuition_currency="EUR",
                 tuition_basis="per year", duration="2 years")  # fmt: skip
    a["fields"]["tuition_amount"]["conflicts"] = [{"value": "12000"}]
    result = score_programs(
        [normalize_program(a), euros("b", "50000")], COST_AND_DURATION
    )
    record = next(p for p in result["programs"] if p["program_id"] == "a")
    assert record["contributions"]["cost"]["has_conflict"] is True
    assert record["contributions"]["cost"]["conflicting_values"] == ["12000"]
    assert record["evidence"]["conflicted_inputs"] == ["cost"]


# --- Boundaries ------------------------------------------------------------

# `app/affinity.py` joins these in Phase 4 for the same reason: it decides
# which alumni a student sees first, so it must be unable to call a model or
# fetch anything to do it.
PURE_MODULES = ("app/scoring.py", "app/normalize.py", "app/affinity.py")

FORBIDDEN_ROOTS = frozenset(
    {"google", "requests", "urllib", "urllib3", "httpx", "socket", "http"}
)


def imported_modules(path: Path) -> set[str]:
    """Every module `path` imports, read from its AST rather than its text."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module)
    return found


def transitively_imported(path: Path, seen: set[str] | None = None) -> set[str]:
    """Imports of `path` plus those of every first-party module it reaches."""
    seen = seen if seen is not None else set()
    everything: set[str] = set()
    for name in imported_modules(path):
        everything.add(name)
        if not name.startswith("app.") or name in seen:
            continue
        seen.add(name)
        child = Path(name.replace(".", "/") + ".py")
        if child.exists():
            everything |= transitively_imported(child, seen)
    return everything


@pytest.mark.parametrize("module", PURE_MODULES)
def test_the_deterministic_layer_cannot_reach_adk_or_the_network(module: str) -> None:
    """Structural: these modules cannot call a model or fetch anything.

    Checked against the real import graph — transitively, so the guarantee
    cannot be broken by a helper module quietly importing ADK. "The LLM
    never touches a number" is the whole architecture, so it is asserted
    rather than trusted.
    """
    for name in transitively_imported(Path(module)):
        root = name.split(".")[0]
        assert root not in FORBIDDEN_ROOTS, f"{module} transitively imports {name}"


@pytest.mark.parametrize("module", PURE_MODULES)
def test_the_deterministic_layer_names_no_retrieval_primitive(module: str) -> None:
    """A second, cruder net: no retrieval symbol appears in executable code."""
    tree = ast.parse(Path(module).read_text(encoding="utf-8"))
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)} | {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }
    # Deliberately only unambiguous symbols: `get` and `post` would match
    # every `dict.get` in the file and catch nothing real.
    for forbidden in ("google_search", "ToolContext", "urlopen", "Runner", "LlmAgent"):
        assert forbidden not in names, f"{module} references {forbidden}"


def test_the_scorer_takes_no_tool_context() -> None:
    import inspect

    parameters = inspect.signature(score_programs).parameters
    assert set(parameters) == {"normalized_programs", "weights"}


def test_the_scorer_does_not_mutate_its_input() -> None:
    programs = [euros("a", "10000"), euros("b", "50000")]
    before = json.dumps(programs, sort_keys=True, default=str)
    score_programs(programs, COST_AND_DURATION)
    assert json.dumps(programs, sort_keys=True, default=str) == before


# --- Explanation integrity -------------------------------------------------


def scored() -> dict:
    return score_programs([euros("a", "10000"), euros("b", "50000")], COST_AND_DURATION)


def test_a_narration_restating_the_scorers_numbers_passes() -> None:
    result = scored()
    narration = (
        "University A ranks 1 with a total of 1.0, against 0.5 for University B. "
        "A's tuition is 10000 EUR per year; B's is 50000."
    )
    assert explanation_integrity(narration, result)["ok"] is True


def test_a_rounded_or_percentage_restatement_still_passes() -> None:
    result = scored()
    assert (
        explanation_integrity("A scores 100% and B scores 50%.", result)["ok"] is True
    )


def test_a_narration_inventing_a_number_is_caught() -> None:
    """The C3 analogue of C2's quote verification."""
    result = scored()
    check = explanation_integrity(
        "University B costs about 43000 EUR per year.", result
    )
    assert check["ok"] is False
    assert "43000" in check["unsupported_numbers"]
    assert "authoritative for numbers" in check["message"]


def test_a_narration_recomputing_a_total_is_caught() -> None:
    result = scored()
    check = explanation_integrity(
        "Weighing these up, University B really scores 0.72 overall.", result
    )
    assert check["ok"] is False
    assert "0.72" in check["unsupported_numbers"]


def test_an_explanation_cannot_change_the_ranking() -> None:
    """The scorer's output is not a function of anything the model says."""
    result = scored()
    before = json.dumps(result["ranking"], sort_keys=True)
    explanation_integrity("B is obviously the better choice.", result)
    assert json.dumps(result["ranking"], sort_keys=True) == before


# --- Integrity checker: formatting is not fabrication (Phase 3 audit) -------


def test_a_thousands_separator_is_not_a_fabrication() -> None:
    """The bug the first real live answer exposed.

    The scorer stored 22290; the model wrote "22,290" for a human reader.
    Reading that as 22.29 reported a correct answer as invented. The check
    must be strict about provenance and relaxed about formatting.
    """
    result = {"programs": [{"raw_value": 22290.0}]}
    check = explanation_integrity("Tuition is EUR 22,290 per year.", result)
    assert check["ok"] is True, check["unsupported_numbers"]


def test_a_european_grouped_figure_is_also_accepted() -> None:
    result = {"programs": [{"raw_value": 17310.0}]}
    assert explanation_integrity("The fee is 17.310 euro.", result)["ok"] is True


def test_relaxing_formatting_did_not_blind_the_check() -> None:
    """No reading of an absent number matches, however it is punctuated."""
    result = {"programs": [{"raw_value": 22290.0}]}
    for written in ("43,000", "43.000", "43000"):
        check = explanation_integrity(f"Tuition is EUR {written}.", result)
        assert check["ok"] is False, written


def test_a_stored_value_written_back_verbatim_is_accepted() -> None:
    """Published strings reach the narration through the matrix tool."""
    result = {"programs": [{"published_value": "22290", "raw_value": 22290.0}]}
    assert explanation_integrity("TU Delft charges 22,290.", result)["ok"] is True
