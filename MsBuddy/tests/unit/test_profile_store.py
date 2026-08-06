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

"""Deterministic profile state operations."""

from __future__ import annotations

from types import SimpleNamespace

from app.config import MAX_VALUE_HISTORY, STATE_PROFILE
from app.profile_store import (
    apply_field,
    clear_fields,
    collect_student_text,
    compute_completeness,
    derive_gpa,
    empty_profile,
    evidence_supports,
    export_profile,
    read_profile,
    unmet_dependencies,
    write_profile,
)
from app.schemas import ClaimTier


def _text_content(role: str, text: str) -> SimpleNamespace:
    return SimpleNamespace(role=role, parts=[SimpleNamespace(text=text)])


# --- Evidence verification -------------------------------------------------


def test_evidence_matches_ignoring_case_and_spacing() -> None:
    assert evidence_supports("8.1 CGPA", "I got  8.1   cgpa in my BTech")


def test_evidence_matches_across_light_punctuation() -> None:
    assert evidence_supports("GRE: 320", "my GRE 320 overall")


def test_evidence_not_present_is_rejected() -> None:
    assert evidence_supports("9.4 CGPA", "I got 8.1 CGPA") is False


def test_empty_evidence_is_rejected() -> None:
    assert evidence_supports("", "anything at all") is False
    assert evidence_supports("   ", "anything at all") is False


def test_only_student_authored_text_becomes_evidence() -> None:
    """Model output must never be able to serve as its own evidence."""
    session = SimpleNamespace(
        events=[
            SimpleNamespace(content=_text_content("user", "I studied ECE")),
            SimpleNamespace(content=_text_content("model", "Your GPA is 9.9")),
        ]
    )
    collected = collect_student_text(session, None)
    assert "I studied ECE" in collected
    assert "9.9" not in collected


def test_collect_student_text_includes_current_turn() -> None:
    session = SimpleNamespace(events=[])
    current = _text_content("user", "targeting Fall 2027")
    assert "Fall 2027" in collect_student_text(session, current)


def test_collect_student_text_survives_missing_attributes() -> None:
    assert collect_student_text(None, None) == ""
    assert collect_student_text(SimpleNamespace(), None) == ""
    assert collect_student_text(SimpleNamespace(events=[SimpleNamespace()]), None) == ""


# --- Field application -----------------------------------------------------


def test_apply_field_records_provenance() -> None:
    profile = empty_profile()
    apply_field(profile, "gre_quant", 168, ClaimTier.USER_STATED, "GRE 168 Q", None)
    entry = profile["fields"]["gre_quant"]
    assert entry["value"] == 168
    assert entry["tier"] == "USER_STATED"
    assert entry["evidence_span"] == "GRE 168 Q"
    assert entry["recorded_at"]


def test_overwrite_is_reported_and_previous_value_kept() -> None:
    """Silent overwrite of a corrected value is a named C1 failure case."""
    profile = empty_profile()
    apply_field(profile, "gre_quant", 165, ClaimTier.USER_STATED, "165", None)
    outcome = apply_field(profile, "gre_quant", 168, ClaimTier.USER_STATED, "168", None)
    assert outcome["replaced_previous_value"] == 165
    assert profile["fields"]["gre_quant"]["superseded"] == ["165"]


def test_rewriting_the_same_value_is_not_a_supersede() -> None:
    profile = empty_profile()
    apply_field(profile, "gre_quant", 168, ClaimTier.USER_STATED, "168", None)
    outcome = apply_field(profile, "gre_quant", 168, ClaimTier.USER_STATED, "168", None)
    assert outcome["replaced_previous_value"] is None
    assert profile["fields"]["gre_quant"]["superseded"] == []


def test_value_history_is_bounded() -> None:
    profile = empty_profile()
    for score in range(150, 150 + MAX_VALUE_HISTORY + 4):
        apply_field(profile, "gre_quant", score, ClaimTier.USER_STATED, "x", None)
    assert len(profile["fields"]["gre_quant"]["superseded"]) == MAX_VALUE_HISTORY


# --- Derivation ------------------------------------------------------------


def test_derivation_needs_both_inputs() -> None:
    profile = empty_profile()
    apply_field(profile, "gpa_value", 8.1, ClaimTier.USER_STATED, "8.1", None)
    assert derive_gpa(profile) is None
    assert "gpa_us_4pt" not in profile["fields"]


def test_derived_gpa_is_inference_with_a_rule_id() -> None:
    profile = empty_profile()
    apply_field(profile, "gpa_value", 8.1, ClaimTier.USER_STATED, "8.1", None)
    apply_field(profile, "gpa_scale", "cgpa_10", ClaimTier.USER_STATED, "CGPA", None)
    derive_gpa(profile)
    entry = profile["fields"]["gpa_us_4pt"]
    assert entry["value"] == 3.24
    assert entry["tier"] == ClaimTier.INFERENCE.value
    assert entry["rule_id"] == "gpa_conv:cgpa_10_to_us_4pt:v1"
    assert entry["evidence_span"] is None


def test_impossible_pair_removes_any_stale_derivation() -> None:
    profile = empty_profile()
    apply_field(profile, "gpa_value", 8.1, ClaimTier.USER_STATED, "8.1", None)
    apply_field(profile, "gpa_scale", "cgpa_10", ClaimTier.USER_STATED, "CGPA", None)
    derive_gpa(profile)
    # Student corrects the scale; 8.1 is impossible out of 4.
    apply_field(profile, "gpa_scale", "cgpa_4", ClaimTier.USER_STATED, "out of 4", None)
    result = derive_gpa(profile)
    assert result["status"] == "error"
    assert "gpa_us_4pt" not in profile["fields"]


# --- Clearing --------------------------------------------------------------


def test_clearing_an_input_also_clears_what_was_derived_from_it() -> None:
    profile = empty_profile()
    apply_field(profile, "gpa_value", 8.1, ClaimTier.USER_STATED, "8.1", None)
    apply_field(profile, "gpa_scale", "cgpa_10", ClaimTier.USER_STATED, "CGPA", None)
    derive_gpa(profile)
    removed = clear_fields(profile, ["gpa_value"])
    assert "gpa_value" in removed
    assert "gpa_us_4pt" in removed
    assert "gpa_us_4pt" not in profile["fields"]


def test_clearing_an_absent_field_is_a_no_op() -> None:
    profile = empty_profile()
    assert clear_fields(profile, ["gre_quant"]) == []


# --- Dependencies and completeness ----------------------------------------


def test_unmet_dependency_is_reported() -> None:
    profile = empty_profile()
    apply_field(profile, "gpa_value", 8.1, ClaimTier.USER_STATED, "8.1", None)
    assert unmet_dependencies(profile) == {"gpa_value": ["gpa_scale"]}


def test_completeness_on_empty_profile() -> None:
    report = compute_completeness(empty_profile())
    assert report["core_complete"] is False
    assert report["ready_for_program_research"] is False
    assert report["overall_present"] == 0
    assert len(report["core_missing"]) == 7


def test_completeness_explains_every_missing_field() -> None:
    report = compute_completeness(empty_profile())
    for item in report["missing_fields"]:
        assert item["why_it_matters"].strip()
        assert item["importance"] in ("core", "recommended", "optional")


def test_core_complete_flips_when_all_core_fields_present() -> None:
    profile = empty_profile()
    for name, value in [
        ("undergrad_degree", "BTech ECE"),
        ("gpa_value", 8.1),
        ("gpa_scale", "cgpa_10"),
        ("target_intake_term", "fall"),
        ("target_intake_year", 2027),
        ("target_countries", ["Canada"]),
        ("specialization_interest", "Data Science"),
    ]:
        apply_field(profile, name, value, ClaimTier.USER_STATED, "quoted", None)
    report = compute_completeness(profile)
    assert report["core_complete"] is True
    assert report["ready_for_program_research"] is True
    assert report["core_missing"] == []


def test_derived_fields_do_not_inflate_completeness() -> None:
    profile = empty_profile()
    apply_field(profile, "gpa_value", 8.1, ClaimTier.USER_STATED, "8.1", None)
    apply_field(profile, "gpa_scale", "cgpa_10", ClaimTier.USER_STATED, "CGPA", None)
    before = compute_completeness(profile)["overall_present"]
    derive_gpa(profile)
    assert compute_completeness(profile)["overall_present"] == before


# --- State round-trip ------------------------------------------------------


def test_read_returns_a_copy_so_state_is_not_mutated_in_place() -> None:
    """ADK registers a delta on assignment; in-place edits can be missed."""
    state: dict = {}
    profile = read_profile(state, STATE_PROFILE)
    apply_field(profile, "gre_quant", 168, ClaimTier.USER_STATED, "168", None)
    assert STATE_PROFILE not in state

    write_profile(state, STATE_PROFILE, profile)
    assert state[STATE_PROFILE]["fields"]["gre_quant"]["value"] == 168

    again = read_profile(state, STATE_PROFILE)
    again["fields"]["gre_quant"]["value"] = 130
    assert state[STATE_PROFILE]["fields"]["gre_quant"]["value"] == 168


def test_read_profile_tolerates_corrupt_state() -> None:
    for junk in ("not a dict", 42, {"unexpected": True}, None):
        assert read_profile({STATE_PROFILE: junk}, STATE_PROFILE)["fields"] == {}


def test_export_preserves_provenance_on_every_value() -> None:
    profile = empty_profile()
    apply_field(profile, "gpa_value", 8.1, ClaimTier.USER_STATED, "8.1 CGPA", None)
    apply_field(profile, "gpa_scale", "cgpa_10", ClaimTier.USER_STATED, "CGPA", None)
    derive_gpa(profile)
    exported = export_profile(profile)
    assert exported["field_count"] == 3
    for entry in exported["fields"].values():
        assert entry["tier"] in ("USER_STATED", "INFERENCE")
        assert entry["recorded_at"]
        assert (entry["evidence_span"] is not None) ^ (entry["rule_id"] is not None)
