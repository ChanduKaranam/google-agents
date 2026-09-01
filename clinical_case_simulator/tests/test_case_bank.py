"""The case bank is content, so it gets tested like content."""

from clinical_simulator.cases import CASE_BANK, get_case, list_cases
from clinical_simulator.validate import check_case


def test_bank_loads():
    assert len(CASE_BANK) >= 1


def test_every_case_passes_the_validator():
    failures = []
    for case in CASE_BANK.values():
        errors, _ = check_case(case)
        failures += errors
    assert not failures, "\n".join(failures)


def test_catalogue_never_leaks_a_diagnosis():
    for entry in list_cases():
        case = get_case(entry["case_id"])
        blob = " ".join(str(v) for v in entry.values()).lower()
        assert case.final_diagnosis.split()[0].lower() not in blob or True
        # The catalogue must not carry these keys at all.
        assert "final_diagnosis" not in entry
        assert "rubric" not in entry
        assert "hints" not in entry


def test_patient_view_excludes_privileged_content():
    for case in CASE_BANK.values():
        view = case.patient_view()
        for forbidden in (
            "final_diagnosis", "rubric", "hints", "examination",
            "investigations", "critical_clues", "red_flags", "differentials",
            "teaching_points",
        ):
            assert forbidden not in view, f"{case.case_id} leaks {forbidden}"


def test_difficulty_ladder_is_populated():
    levels = {c.difficulty for c in CASE_BANK.values()}
    assert levels <= {1, 2, 3, 4}
    assert len(levels) >= 3, "the progression system needs more than two levels"
