"""The scorer is the graded component, so its behaviour is pinned down here."""

import pytest

from clinical_simulator import session as S
from clinical_simulator.cases import get_case
from clinical_simulator.evaluation import score_encounter

CASE_ID = "IM-002"


def _blank():
    enc = S.blank()
    enc["case_id"] = CASE_ID
    return enc


def _ask(enc, *questions):
    for i, q in enumerate(questions, len(enc["questions_asked"]) + 1):
        enc["questions_asked"].append({"turn": i, "text": q})
    return enc


@pytest.fixture
def case():
    return get_case(CASE_ID)


def test_doing_nothing_scores_near_zero(case):
    card = score_encounter(case, _blank())
    assert card["overall_score"] < 20
    assert card["skills"]["history_taking"] == 0
    assert card["detail"]["case_synthesis"]["final_diagnosis_correct"] is False


def test_a_good_encounter_outscores_a_poor_one(case):
    poor = _ask(_blank(), "does it hurt?")
    poor["differential_submitted"] = [{"dx": "gastritis", "rationale": ""}]
    poor["final_diagnosis"] = "gastritis"
    poor["final_reasoning"] = "probably acidity"

    good = _ask(
        _blank(),
        "What brings you in today?",
        "Where exactly is the pain and what does it feel like?",
        "Does the pain radiate anywhere, into your arm or jaw?",
        "What makes it worse — does walking or exertion bring it on?",
        "What makes it better, does rest help?",
        "Did you have any sweating, nausea or breathlessness with it?",
        "Have you had episodes like this before?",
        "Do you have high blood pressure, diabetes or high cholesterol?",
        "Do you smoke, and how much?",
        "Has anyone in your family had heart problems?",
        "What medication are you currently taking?",
        "Any recent long journeys, leg swelling or calf pain?",
    )
    good["exams_requested"] = [
        {"turn": 20, "query": "vital signs in both arms", "matched": "vitals"},
        {"turn": 21, "query": "cardiovascular examination", "matched": "cvs"},
        {"turn": 22, "query": "JVP", "matched": "jvp"},
        {"turn": 23, "query": "respiratory examination", "matched": "chest"},
    ]
    good["investigations_ordered"] = [
        {"turn": 30, "query": "ECG", "matched": "ecg"},
        {"turn": 31, "query": "serial troponin", "matched": "troponin"},
        {"turn": 32, "query": "chest x ray", "matched": "cxr"},
        {"turn": 33, "query": "renal function and electrolytes", "matched": "rft"},
    ]
    good["differential_submitted"] = [
        {"dx": "Acute coronary syndrome", "rationale": "exertional retrosternal heaviness with radiation to the left arm and jaw, diaphoresis, ST depression"},
        {"dx": "Aortic dissection", "rationale": "must exclude before anticoagulation, though no inter-arm difference"},
        {"dx": "Pulmonary embolism", "rationale": "low Wells score but considered"},
    ]
    good["distinguishing_plan"] = (
        "Serial troponin and repeat ECG separate ACS from the rest; both arm "
        "blood pressures and the mediastinum on chest x ray address dissection."
    )
    good["final_diagnosis"] = "NSTEMI"
    good["final_reasoning"] = (
        "Exertional chest heaviness with radiation to the left arm and jaw, "
        "relieved by rest, with diaphoresis, in a smoker with a family history "
        "of premature coronary disease. ST depression on ECG with a rising "
        "troponin and no ST elevation makes this an NSTEMI rather than "
        "unstable angina or a STEMI."
    )

    poor_card = score_encounter(case, poor)
    good_card = score_encounter(case, good)
    assert good_card["overall_score"] > poor_card["overall_score"] + 30
    assert good_card["detail"]["case_synthesis"]["final_diagnosis_correct"]
    assert "Acute coronary syndrome (NSTEMI)" in good_card["detail"]["differential_diagnosis"]["identified_leading"]


def test_hints_and_reveal_reduce_the_score(case):
    base = _ask(_blank(), "Does the pain radiate to your arm or jaw?")
    plain = score_encounter(case, dict(base))

    hinted = dict(base)
    hinted["hints_used"] = 2
    revealed = dict(base)
    revealed["revealed"] = True

    assert score_encounter(case, hinted)["overall_score"] <= plain["overall_score"]
    assert score_encounter(case, revealed)["overall_score"] < plain["overall_score"]
    assert score_encounter(case, revealed)["support_multiplier"] == 0.60


def test_missing_a_critical_history_item_is_reported(case):
    enc = _ask(_blank(), "Where is the pain?")
    card = score_encounter(case, enc)
    missed_ids = {m["id"] for m in card["detail"]["history_taking"]["missed"]}
    assert "h_radiation" in missed_ids
    assert any(m["critical"] for m in card["detail"]["history_taking"]["missed"])


def test_jargon_with_the_patient_costs_communication_marks(case):
    plain = _ask(_blank(), "Does the pain spread anywhere?", "Did you sweat with it?")
    jargon = _ask(_blank(), "Any radiation of the pain?", "Any diaphoresis or dyspnoea?")
    assert (
        score_encounter(case, jargon)["skills"]["communication"]
        < score_encounter(case, plain)["skills"]["communication"]
    )


def test_missing_a_must_exclude_diagnosis_is_flagged(case):
    enc = _blank()
    enc["differential_submitted"] = [
        {"dx": "Acute coronary syndrome", "rationale": "classic history"},
        {"dx": "GERD", "rationale": "postprandial"},
        {"dx": "musculoskeletal", "rationale": "possible"},
    ]
    card = score_encounter(case, enc)
    missed = [m["dx"] for m in card["detail"]["differential_diagnosis"]["missed_must_exclude"]]
    assert "Aortic dissection" in missed


def test_scores_are_reproducible(case):
    enc = _ask(_blank(), "Does the pain radiate?", "Do you smoke?")
    assert score_encounter(case, enc) == score_encounter(case, enc)
