"""A case may not ask a student to exclude something it gives them no way to exclude.

Found in the wild: IM-001 listed pulmonary embolism as must-exclude but defined
no lower-limb examination. A student doing exactly what the case asked lost
marks for the case author's omission.
"""

import copy

import pytest

from clinical_simulator.cases import CASE_BANK, get_case
from clinical_simulator.cases.matching import match_all
from clinical_simulator.validate import check_case


def test_every_must_exclude_is_actionable_in_every_case():
    problems = []
    for case in CASE_BANK.values():
        ids = {f.id for f in case.examination} | {f.id for f in case.investigations}
        for d in case.differentials:
            if d.status != "must-exclude":
                continue
            if not d.excluded_by:
                problems.append(f"{case.case_id}: {d.dx!r} has no excluded_by")
            for ref in d.excluded_by:
                if ref not in ids:
                    problems.append(f"{case.case_id}: {d.dx!r} -> unknown finding {ref!r}")
    assert not problems, "\n".join(problems)


def test_validator_rejects_an_unactionable_must_exclude():
    case = copy.deepcopy(get_case("IM-001"))
    for d in case.differentials:
        if d.status == "must-exclude":
            d.excluded_by = []
    errors, _ = check_case(case)
    assert any("excluded_by" in e for e in errors)


def test_validator_rejects_a_dangling_finding_reference():
    case = copy.deepcopy(get_case("IM-001"))
    for d in case.differentials:
        if d.status == "must-exclude":
            d.excluded_by = ["no_such_finding"]
            break
    errors, _ = check_case(case)
    assert any("no_such_finding" in e for e in errors)


@pytest.mark.parametrize(
    "case_id,query,expected_label",
    [
        # The two requests that failed in Gemini Enterprise, on IM-001.
        ("IM-001", "Please examine the respiratory system and the legs for oedema or calf tenderness.", "Lower limb examination"),
        ("IM-001", "Can you palpate the chest wall to see if the pain is reproducible?", "Chest wall palpation"),
        ("IM-001", "examine the respiratory system", "Full respiratory examination"),
        ("IM-002", "Please examine the respiratory system and the legs for oedema or calf tenderness.", "Lower limb examination"),
        ("IM-002", "Can you palpate the chest wall to see if the pain is reproducible?", "Chest wall palpation"),
    ],
)
def test_examination_requests_that_previously_failed(case_id, query, expected_label):
    found, _ = match_all(query, get_case(case_id).examination)
    assert expected_label in [f.label for f in found], f"{query!r} -> {[f.label for f in found]}"


def test_splitting_a_system_into_parts_does_not_break_the_whole():
    """IM-001 teaches inspection, percussion and auscultation separately.

    Asking for any one part must still work, and asking for the system must
    return the combined finding rather than an ambiguity.
    """
    exams = get_case("IM-001").examination
    for query, expected in [
        ("percuss the chest", "Chest percussion"),
        ("auscultate the chest", "Chest auscultation"),
        ("chest examination", "Full respiratory examination"),
    ]:
        found, _ = match_all(query, exams)
        assert [f.label for f in found] == [expected], query
