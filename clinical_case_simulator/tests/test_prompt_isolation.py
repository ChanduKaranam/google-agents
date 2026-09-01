"""The hidden-state guarantee, tested at the prompt level.

If these fail, the simulator can answer-dump regardless of how the instructions
are worded.
"""

from types import SimpleNamespace

from clinical_simulator import session as S
from clinical_simulator.cases import CASE_BANK
from clinical_simulator.prompts import SIMULATOR_INSTRUCTION, patient_instruction
from clinical_simulator.validate import _hard_terms


def _ctx(case_id):
    enc = S.blank()
    enc["case_id"] = case_id
    return SimpleNamespace(state={S.KEY: enc})


def test_patient_prompt_never_contains_the_diagnosis():
    for case in CASE_BANK.values():
        prompt = f" {patient_instruction(_ctx(case.case_id)).lower()} "
        leaked = [t for t in _hard_terms(case) if f" {t} " in prompt]
        assert not leaked, f"{case.case_id}: patient prompt contains {leaked}"


def test_patient_prompt_never_contains_examination_or_results():
    for case in CASE_BANK.values():
        prompt = patient_instruction(_ctx(case.case_id))
        for finding in case.examination + case.investigations:
            assert finding.result not in prompt, (
                f"{case.case_id}: patient prompt contains the result of {finding.id}"
            )


def test_patient_prompt_carries_the_running_transcript():
    case_id = next(iter(CASE_BANK.keys()))
    ctx = _ctx(case_id)
    enc = ctx.state[S.KEY]
    enc["questions_asked"].append({"turn": 1, "text": "How long has this been going on?"})
    enc["patient_replies"].append({"turn": 1, "text": "About three days now."})
    prompt = patient_instruction(ctx)
    assert "About three days now." in prompt
    assert "How long has this been going on?" in prompt


def test_patient_refuses_to_act_without_a_case():
    ctx = SimpleNamespace(state={})
    assert "[no active case]" in patient_instruction(ctx)


def test_simulator_prompt_contains_no_case_content():
    prompt = SIMULATOR_INSTRUCTION.lower()
    for case in CASE_BANK.values():
        assert case.final_diagnosis.lower() not in prompt
        assert case.case_id.lower() not in prompt
        for finding in case.investigations:
            assert finding.result.lower() not in prompt
