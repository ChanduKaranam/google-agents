"""Deterministic scoring of a completed encounter.

Design rule: the *numbers* are computed here, in Python, from the case rubric.
The LLM only writes prose around a scorecard it did not produce.  That keeps
marks reproducible and reviewable, and stops the model from grading generously
because the student was polite — the "overly agreeable AI" failure mode called
out in the research.
"""

from __future__ import annotations

from typing import Any

from ..cases.matching import contains_any, normalise
from ..cases.schema import Case, RubricItem
from . import rubric as R


def _pct(got: float, total: float) -> float:
    return 100.0 * got / total if total else 0.0


def _cover(items: list[RubricItem], haystack: str) -> tuple[float, float, list[dict]]:
    """Weighted coverage of rubric items against everything the student said."""
    got = 0.0
    total = 0.0
    missed: list[dict] = []
    for item in items:
        total += item.weight
        if contains_any(haystack, item.keywords or [item.label]):
            got += item.weight
        else:
            missed.append(
                {
                    "id": item.id,
                    "label": item.label,
                    "critical": item.critical,
                    "why_it_matters": item.teaching_note,
                }
            )
    return got, total, missed


# ---------------------------------------------------------------------------
# Individual skills
# ---------------------------------------------------------------------------


def _score_history(case: Case, enc: dict) -> dict:
    asked = " | ".join(q["text"] for q in enc.get("questions_asked", []))
    got, total, missed = _cover(case.rubric.history, asked)
    score = _pct(got, total)
    critical_missed = [m for m in missed if m["critical"]]
    if critical_missed:
        score *= 0.85 ** len(critical_missed)
    return {
        "score": round(score),
        "asked_count": len(enc.get("questions_asked", [])),
        "covered": round(got, 1),
        "available": round(total, 1),
        "missed": missed,
    }


def _score_communication(case: Case, enc: dict) -> dict:
    questions = [q["text"] for q in enc.get("questions_asked", [])]
    if not questions:
        return {"score": 0, "signals": {}, "notes": ["No questions were asked."]}

    n = len(questions)
    open_q = sum(1 for q in questions if any(normalise(q).startswith(normalise(s)) for s in R.OPEN_STARTERS))
    jargon_hits = sorted({j for q in questions if (j := contains_any(q, R.JARGON))})
    compound = sum(1 for q in questions if q.count("?") > 1)
    empathy = sum(1 for q in questions if contains_any(q, R.EMPATHY_MARKERS))

    score = 60.0
    score += min(25.0, 100.0 * open_q / n * 0.35)          # open questions
    score += min(10.0, empathy * 5.0)                       # rapport
    score += 5.0 if n >= 8 else 0.0                         # sustained interview
    score -= min(25.0, 6.0 * len(jargon_hits))              # unexplained jargon
    score -= min(10.0, 4.0 * compound)                      # multi-barrelled
    score = max(0.0, min(100.0, score))

    notes = []
    if jargon_hits:
        notes.append(
            "Medical terms used with the patient without explaining them: "
            + ", ".join(jargon_hits)
        )
    if open_q == 0:
        notes.append("Every question was closed-ended; open the interview more broadly.")
    if compound:
        notes.append(f"{compound} question(s) asked more than one thing at a time.")
    if empathy == 0:
        notes.append("No acknowledgement of the patient's concern or discomfort.")

    return {
        "score": round(score),
        "signals": {
            "questions": n,
            "open_questions": open_q,
            "jargon_terms": jargon_hits,
            "compound_questions": compound,
            "empathy_statements": empathy,
        },
        "notes": notes,
    }


def _score_investigations(case: Case, enc: dict) -> dict:
    ordered = enc.get("investigations_ordered", [])
    ordered_text = " | ".join(o["query"] for o in ordered)
    got, total, missed = _cover(case.rubric.investigations, ordered_text)
    score = _pct(got, total)

    matched_ids = {
        i
        for o in ordered
        for i in (o.get("matched_all") or ([o["matched"]] if o.get("matched") else []))
    }
    by_id = {f.id: f for f in case.investigations}
    inappropriate = [
        by_id[i].label for i in matched_ids if i in by_id and not by_id[i].appropriate
    ]
    over_ordering = [
        by_id[i].label
        for i in matched_ids
        if i in by_id and by_id[i].tier in ("second-line", "specialist")
    ]
    if inappropriate:
        score -= 8.0 * len(inappropriate)
    # Blanket-ordering everything is not investigation *selection*.
    if len(matched_ids) > max(4, len(case.rubric.investigations) + 2):
        score -= 10.0
    score = max(0.0, min(100.0, score))

    return {
        "score": round(score),
        "ordered": [o["query"] for o in ordered],
        "missed": missed,
        "low_yield_or_premature": sorted(set(inappropriate + over_ordering)),
    }


def _score_differential(case: Case, enc: dict) -> dict:
    submitted = enc.get("differential_submitted", [])
    text = " | ".join(d.get("dx", "") for d in submitted)

    correct = [d for d in case.differentials if d.status == "correct"]
    must_exclude = [d for d in case.differentials if d.status == "must-exclude"]
    plausible = [d for d in case.differentials if d.status == "plausible"]

    def hit(item) -> bool:
        return bool(contains_any(text, [item.dx, *item.aliases]))

    got_correct = [d.dx for d in correct if hit(d)]
    got_exclude = [d.dx for d in must_exclude if hit(d)]
    got_plausible = [d.dx for d in plausible if hit(d)]

    score = 0.0
    if correct:
        score += 50.0 * len(got_correct) / len(correct)
    else:
        score += 50.0
    if must_exclude:
        score += 30.0 * len(got_exclude) / len(must_exclude)
    else:
        score += 30.0
    if plausible:
        score += 20.0 * min(1.0, len(got_plausible) / min(2, len(plausible)))
    else:
        score += 20.0

    # A differential list without reasons is a guess list.
    with_rationale = sum(1 for d in submitted if (d.get("rationale") or "").strip())
    if submitted and with_rationale / len(submitted) < 0.5:
        score *= 0.85
    if len(submitted) < 3:
        score *= 0.9

    return {
        "score": round(max(0.0, min(100.0, score))),
        "submitted": [d.get("dx", "") for d in submitted],
        "identified_leading": got_correct,
        "missed_leading": [d.dx for d in correct if not hit(d)],
        "missed_must_exclude": [
            {"dx": d.dx, "why": d.why} for d in must_exclude if not hit(d)
        ],
        "credited_alternatives": got_plausible,
    }


def _score_reasoning(case: Case, enc: dict) -> dict:
    submitted = enc.get("differential_submitted", [])
    rationales = " | ".join(d.get("rationale", "") for d in submitted)
    plan = enc.get("distinguishing_plan", "")
    final = enc.get("final_reasoning", "")
    blob = " | ".join([rationales, plan, final])

    clues_used = [c for c in case.critical_clues if contains_any(blob, [c])]
    flags_used = [f for f in case.red_flags if contains_any(blob, [f])]

    score = 0.0
    score += 30.0 * (len(clues_used) / len(case.critical_clues)) if case.critical_clues else 30.0
    score += 15.0 * (len(flags_used) / len(case.red_flags)) if case.red_flags else 15.0
    score += 20.0 if len(normalise(plan).split()) >= 12 else (10.0 if plan else 0.0)
    score += 20.0 if len(normalise(final).split()) >= 25 else (10.0 if final else 0.0)
    if submitted:
        score += 15.0 * (
            sum(1 for d in submitted if (d.get("rationale") or "").strip()) / len(submitted)
        )

    return {
        "score": round(max(0.0, min(100.0, score))),
        "critical_clues_used": clues_used,
        "critical_clues_unused": [c for c in case.critical_clues if c not in clues_used],
        "red_flags_addressed": flags_used,
        "red_flags_unaddressed": [f for f in case.red_flags if f not in flags_used],
        "had_discriminating_plan": bool(plan),
    }


def _score_synthesis(case: Case, enc: dict) -> dict:
    final_dx = enc.get("final_diagnosis", "")
    correct_items = [d for d in case.differentials if d.status == "correct"]
    targets = [case.final_diagnosis] + [
        a for d in correct_items for a in ([d.dx] + d.aliases)
    ]
    dx_right = bool(contains_any(final_dx, targets))

    exam_text = " | ".join(e["query"] for e in enc.get("exams_requested", []))
    exam_got, exam_total, exam_missed = _cover(case.rubric.examination, exam_text)

    score = (55.0 if dx_right else 0.0) + 0.25 * _pct(exam_got, exam_total)
    if not dx_right and enc.get("differential_submitted"):
        # Partial credit: the right answer was on the list but not chosen.
        if contains_any(
            " | ".join(d.get("dx", "") for d in enc["differential_submitted"]), targets
        ):
            score += 20.0
    if len(normalise(enc.get("final_reasoning", "")).split()) >= 25:
        score += 20.0
    return {
        "score": round(max(0.0, min(100.0, score))),
        "final_diagnosis_given": final_dx,
        "final_diagnosis_correct": dx_right,
        "examination_missed": exam_missed,
        "examination_coverage_pct": round(_pct(exam_got, exam_total)),
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def score_encounter(case: Case, enc: dict) -> dict[str, Any]:
    """Return a full scorecard.  Pure function — no I/O, no model calls."""
    skills = {
        "history_taking": _score_history(case, enc),
        "communication": _score_communication(case, enc),
        "clinical_reasoning": _score_reasoning(case, enc),
        "differential_diagnosis": _score_differential(case, enc),
        "investigation_selection": _score_investigations(case, enc),
        "case_synthesis": _score_synthesis(case, enc),
    }

    raw_overall = sum(
        skills[k]["score"] * w for k, w in R.SKILL_WEIGHTS.items()
    )
    multiplier = (
        R.REVEAL_PENALTY
        if enc.get("revealed")
        else R.HINT_PENALTY.get(min(3, int(enc.get("hints_used", 0))), 0.75)
    )
    overall = round(raw_overall * multiplier)
    label, note = R.band(overall)

    return {
        "case_id": case.case_id,
        "case_title": case.title,
        "difficulty": case.difficulty,
        "overall_score": overall,
        "overall_before_support_penalty": round(raw_overall),
        "support_multiplier": multiplier,
        "hints_used": int(enc.get("hints_used", 0)),
        "answer_revealed": bool(enc.get("revealed")),
        "band": label,
        "band_note": note,
        "skills": {k: v["score"] for k, v in skills.items()},
        "detail": skills,
        "true_final_diagnosis": case.final_diagnosis,
        "diagnosis_reasoning": case.diagnosis_reasoning,
        "teaching_points": case.teaching_points,
        "revision_topics": case.revision_topics,
        "transcript_size": {
            "questions": len(enc.get("questions_asked", [])),
            "examinations": len(enc.get("exams_requested", [])),
            "investigations": len(enc.get("investigations_ordered", [])),
        },
    }
