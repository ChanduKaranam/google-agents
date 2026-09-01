"""A weak answer must be recorded and marked, never refused.

These pin down the fix for a real defect: the agent was declining to record a
struggling student's differential and final diagnosis because they were thin,
so three skills scored zero on an absence the agent itself created. The student
was marked down for the agent's decision, not their own performance.
"""

from types import SimpleNamespace

import pytest

from clinical_simulator import session as S
from clinical_simulator.cases import get_case
from clinical_simulator.evaluation import score_encounter
from clinical_simulator.prompts import SIMULATOR_INSTRUCTION
from clinical_simulator.tools.reasoning_tools import (
    submit_differential,
    submit_final_diagnosis,
)


@pytest.fixture
def ctx():
    enc = S.blank()
    enc["case_id"] = "IM-002"
    return SimpleNamespace(state={S.KEY: enc})


def _enc(ctx):
    return ctx.state[S.KEY]


def test_differential_is_recorded_even_with_no_reasons(ctx):
    out = submit_differential(
        ["acute coronary syndrome", "gastritis"], ["", ""], ctx
    )
    assert out["status"] == "recorded"
    assert _enc(ctx)["differential_submitted"] == [
        {"dx": "acute coronary syndrome", "rationale": ""},
        {"dx": "gastritis", "rationale": ""},
    ]
    # The agent is told which ones lacked reasons so it can coach afterwards.
    assert out["diagnoses_given_without_a_reason"] == [
        "acute coronary syndrome",
        "gastritis",
    ]


def test_short_differential_is_recorded_not_rejected(ctx):
    out = submit_differential(["heart attack"], [""], ctx)
    assert out["status"] == "recorded"
    assert len(_enc(ctx)["differential_submitted"]) == 1
    assert out["note"], "the agent should be told it scores lower, not to refuse"


def test_final_diagnosis_is_recorded_without_a_prior_differential(ctx):
    out = submit_final_diagnosis("heart attack", "it looks like one", ctx)
    assert out["status"] == "recorded"
    assert _enc(ctx)["final_diagnosis"] == "heart attack"
    assert "skipped" in out["note"].lower()


def test_thin_reasoning_is_recorded_and_does_not_block_the_report(ctx):
    out = submit_final_diagnosis("NSTEMI", "chest pain", ctx)
    assert out["status"] == "recorded"
    assert out["reasoning_looks_thin"] is True
    assert "never withhold" in out["coaching"].lower()


def test_a_weak_but_recorded_encounter_still_scores_above_zero(ctx):
    """The whole point: a poor answer is marked as poor, not as absent."""
    submit_differential(["acute coronary syndrome", "gastritis"], ["", ""], ctx)
    submit_final_diagnosis("heart attack", "the ECG looked abnormal", ctx)

    card = score_encounter(get_case("IM-002"), _enc(ctx))
    # Credit for naming the right condition, even badly and without reasons.
    assert card["skills"]["differential_diagnosis"] > 0
    assert card["skills"]["case_synthesis"] > 0
    assert card["detail"]["case_synthesis"]["final_diagnosis_correct"] is True
    # But nowhere near a competent performance.
    assert card["overall_score"] < 45


def test_evaluation_never_depends_on_completing_the_workflow():
    """A student who stops early still gets marked."""
    enc = S.blank()
    enc["case_id"] = "IM-002"
    enc["questions_asked"] = [{"turn": 1, "text": "Do you have chest pain?"}]
    card = score_encounter(get_case("IM-002"), enc)
    assert card["overall_score"] >= 0
    assert card["band"]
    assert card["detail"]["history_taking"]["missed"]


def test_instructions_forbid_gatekeeping_and_tool_names():
    text = SIMULATOR_INSTRUCTION.lower()
    assert "record first" in text
    assert "never refuse to record" in text
    assert "never make the report conditional" in text
    assert "never name your tools" in text


def test_instructions_forbid_answering_from_memory():
    """Seen in the wild: the agent answered an examination request from its own
    conversation history instead of calling the tool, and offered a previous
    cardiovascular finding in place of examining the legs."""
    text = SIMULATOR_INSTRUCTION.lower()
    assert "never answer from memory" in text
    assert "every single time, without exception" in text
    assert "as i mentioned" in text
