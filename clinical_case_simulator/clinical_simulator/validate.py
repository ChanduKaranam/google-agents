"""Case-bank validator. Run with `python -m clinical_simulator.validate`.

Three classes of check:

1. Schema — does the JSON load into `Case` at all.
2. Leakage — could the patient's prompt or the hint ladder betray the answer.
   This is the safety property the whole design rests on, so it is tested
   rather than assumed.
3. Markability — can the deterministic scorer actually award the marks the
   rubric describes, and will the aliases match what a student will type.

Exit code is non-zero on any error, so this can gate CI on a faculty case
pull request.
"""

from __future__ import annotations

import json
import sys
from typing import Any

from .cases.loader import DATA_DIR
from .cases.matching import contains_any, normalise
from .cases.schema import Case

# Words that appear inside diagnosis names but are not themselves the answer:
# anatomy, severity, mechanism and exposure terms a patient may legitimately
# use. Flagging these produces noise, not safety.
GENERIC = {
    "acute", "chronic", "severe", "moderate", "mild", "syndrome", "disease",
    "disorder", "failure", "primary", "secondary", "systemic", "acquired",
    "community", "induced", "medication", "onset", "dependent", "unstable",
    "elevation", "imbalance", "bacterial", "viral", "infection", "chest",
    "heart", "attack", "cardiac", "coronary", "pulmonary", "venous",
    "arterial", "artery", "vein", "deep", "blood", "bowel", "stomach",
    "abdominal", "lung", "liver", "kidney", "renal", "hepatic", "alcohol",
    "alcoholic", "dietary", "nutritional", "deficiency", "reaction",
    "right", "left", "upper", "lower", "anterior", "posterior", "distal",
    "proximal", "focal", "diffuse", "generalised", "generalized", "bilateral",
}

# Terms a patient would never say and that give the game away outright.
DIAGNOSTIC_SUFFIXES = (
    "itis", "osis", "aemia", "emia", "pathy", "oma", "olism", "arction",
    "idosis", "ectasis", "thorax", "algia", "opathy",
)


def _hard_terms(case: Case) -> set[str]:
    """Tokens that must not be reachable from the patient prompt or hints.

    Built only from the *canonical names* of the correct differentials, not
    from the long prose of `final_diagnosis` — that sentence contains too much
    ordinary English to tokenise usefully.
    """
    sources = [case.final_diagnosis.split(",")[0]]
    for d in case.differentials:
        if d.status == "correct":
            sources.append(d.dx)
            sources.extend(d.aliases)

    terms: set[str] = set()
    for s in sources:
        for w in normalise(s).split():
            if len(w) >= 5 and w not in GENERIC:
                terms.add(w)
            elif w.endswith(DIAGNOSTIC_SUFFIXES) and len(w) >= 4:
                terms.add(w)

    # Anything the student is told up front is not a secret.
    public = normalise(
        " ".join([case.title, case.opening_brief, case.chief_complaint])
    )
    return {t for t in terms if f" {t} " not in f" {public} "}


def _values(obj: Any) -> list[str]:
    """Flatten a nested structure to its string values, dropping the keys."""
    if isinstance(obj, str):
        return [obj]
    if isinstance(obj, dict):
        return [s for v in obj.values() for s in _values(v)]
    if isinstance(obj, (list, tuple)):
        return [s for v in obj for s in _values(v)]
    return []


def check_case(case: Case) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    cid = case.case_id
    hard = _hard_terms(case)

    # --- 2. Leakage -------------------------------------------------------
    patient_text = f" {normalise(' | '.join(_values(case.patient_view())))} "
    leaked = sorted(t for t in hard if f" {t} " in patient_text)
    if leaked:
        errors.append(
            f"{cid}: the patient can say the answer — {', '.join(leaked)}. "
            f"Rewrite those history entries in lay language."
        )

    for i, hint in enumerate(case.hints, 1):
        hit = sorted(t for t in hard if f" {t} " in f" {normalise(hint)} ")
        if hit:
            errors.append(
                f"{cid}: hint {i} names the answer ({', '.join(hit)}). "
                f"A hint should point at the reasoning, not the diagnosis: {hint!r}"
            )

    # Softer signal: the full name of a correct diagnosis appearing as a phrase
    # in the patient's own words. Sometimes legitimate (family history), so a
    # reviewer decides.
    for d in case.differentials:
        if d.status != "correct":
            continue
        for phrase in [d.dx, *d.aliases]:
            n = normalise(phrase)
            if len(n.split()) > 1 and f" {n} " in patient_text:
                warnings.append(
                    f"{cid}: the phrase {phrase!r} appears in the patient's own words. "
                    f"Confirm this is legitimate (e.g. family history) and not a giveaway."
                )

    jargon = []
    for field in (
        case.history.present_illness.character,
        case.history.present_illness.radiation,
        *case.history.review_of_systems_positive,
        *case.history.review_of_systems_negative,
    ):
        for term in (
            "dyspnoea", "dyspnea", "haemoptysis", "hemoptysis", "syncope",
            "diaphoresis", "orthopnoea", "orthopnea", "melaena", "melena",
        ):
            if contains_any(field, [term]):
                jargon.append(f"{term!r} in {field!r}")
    if jargon:
        warnings.append(f"{cid}: medical jargon in the patient's own words: {jargon}")

    # --- 3. Markability ---------------------------------------------------
    if not case.rubric.history:
        errors.append(f"{cid}: no history rubric — history taking will always score 0.")
    if not case.rubric.investigations:
        warnings.append(f"{cid}: no investigation rubric.")
    if not case.rubric.examination:
        warnings.append(f"{cid}: no examination rubric.")

    for _scope, item in case.rubric_items():
        if not item.keywords:
            warnings.append(
                f"{cid}: rubric item {item.id} has no keywords; only its label will match."
            )
        if not item.teaching_note:
            warnings.append(
                f"{cid}: rubric item {item.id} has no teaching_note; feedback will be thin."
            )
        for kw in item.keywords:
            n = normalise(kw)
            if len(n) < 2:
                warnings.append(f"{cid}: rubric {item.id} keyword {kw!r} is too short to match safely.")
            if n in {"the", "and", "you", "for", "any", "was", "has", "did"}:
                warnings.append(f"{cid}: rubric {item.id} keyword {kw!r} matches ordinary speech.")

    # Every investigation the rubric expects must actually be resultable.
    inv_text = " | ".join(
        " ".join([f.id, f.label, *f.aliases]) for f in case.investigations
    )
    for item in case.rubric.investigations:
        if not contains_any(inv_text, item.keywords or [item.label]):
            warnings.append(
                f"{cid}: investigation rubric item {item.id} matches no investigation defined "
                f"in the case — a student cannot both order it and get a result."
            )

    exam_text = " | ".join(
        " ".join([f.id, f.label, *f.aliases]) for f in case.examination
    )
    for item in case.rubric.examination:
        if not contains_any(exam_text, item.keywords or [item.label]):
            warnings.append(
                f"{cid}: examination rubric item {item.id} matches no examination defined in the case."
            )

    if not any(d.status == "correct" for d in case.differentials):
        errors.append(f"{cid}: no differential marked 'correct'.")
    if not any(d.status == "must-exclude" for d in case.differentials):
        warnings.append(f"{cid}: no 'must-exclude' differential; safety reasoning is unmarked.")

    # Every must-exclude diagnosis has to be actionable. Telling a student to
    # rule something out while giving them no examination or investigation that
    # bears on it marks them down for the author's omission, not their own.
    finding_ids = {f.id for f in case.examination} | {f.id for f in case.investigations}
    for d in case.differentials:
        if d.status != "must-exclude":
            continue
        if not d.excluded_by:
            errors.append(
                f"{cid}: must-exclude diagnosis {d.dx!r} has no 'excluded_by'. "
                f"List the examination or investigation ids that let a student "
                f"actually act on it, or downgrade it to 'plausible'."
            )
            continue
        unknown = [i for i in d.excluded_by if i not in finding_ids]
        if unknown:
            errors.append(
                f"{cid}: must-exclude {d.dx!r} points at {', '.join(unknown)}, "
                f"which this case does not define. A student cannot rule it out."
            )
    for d in case.differentials:
        if d.status == "must-exclude" or not d.excluded_by:
            continue
        unknown = [i for i in d.excluded_by if i not in finding_ids]
        if unknown:
            warnings.append(
                f"{cid}: differential {d.dx!r} references undefined findings: "
                f"{', '.join(unknown)}."
            )

    if not case.critical_clues:
        warnings.append(f"{cid}: no critical_clues; the reasoning score will be crude.")
    if len(case.hints) < 3:
        warnings.append(f"{cid}: fewer than 3 hints; the progressive ladder is incomplete.")
    if not case.examination:
        errors.append(f"{cid}: no examination findings defined.")
    if not case.investigations:
        errors.append(f"{cid}: no investigations defined.")
    if not case.teaching_points:
        warnings.append(f"{cid}: no teaching points.")

    if case.provenance.status != "expert-reviewed":
        warnings.append(
            f"{cid}: provenance.status is '{case.provenance.status}' — not cleared for "
            f"student assessment until a clinician signs it off."
        )
    if case.difficulty == 4 and not case.evolution:
        warnings.append(f"{cid}: level 4 case with no evolution steps.")

    return errors, warnings


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []
    paths = sorted(p for p in DATA_DIR.glob("*.json") if not p.name.startswith("_"))
    if not paths:
        print("No case files found in", DATA_DIR)
        return 1

    cases: list[Case] = []
    for path in paths:
        try:
            cases.append(Case.model_validate(json.loads(path.read_text(encoding="utf-8"))))
        except Exception as exc:  # noqa: BLE001 — report every file, don't abort
            errors.append(f"{path.name}: failed to load — {exc}")

    for case in cases:
        e, w = check_case(case)
        errors += e
        warnings += w

    print(f"Checked {len(cases)} case(s) in {DATA_DIR}\n")
    for w in warnings:
        print(f"  WARN   {w}")
    for e in errors:
        print(f"  ERROR  {e}")

    reviewed = sum(1 for c in cases if c.provenance.status == "expert-reviewed")
    print(f"\n{len(cases)} cases, {len(errors)} error(s), {len(warnings)} warning(s).")
    print(f"{reviewed}/{len(cases)} cleared for student assessment (expert-reviewed).")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
