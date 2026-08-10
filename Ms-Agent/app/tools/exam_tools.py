"""Exam tools — researched requirements meet the student's profile.

`check_exam_requirements` reads only what already passed the research gate
(program facts with evidence) and what the profile states, and produces the
per-program requirement matrix with score comparisons and real gaps. It
performs no research and trusts no prose: interpretation is deterministic
(`app.exams.requirements`), absence is unknown, and optional exams are
never gaps.
"""

from __future__ import annotations

from typing import Any

from google.adk.tools import ToolContext

from app.config.settings import STATE_KNOWLEDGE
from app.exams.reference import EXAMS, exam_info
from app.exams.requirements import compare_score, interpret_requirement
from app.models.program import Program
from app.tools.profile_tools import _read_profile

# Program fact slots that carry exam requirements, by exam family.
_ENGLISH_FIELDS = ("english_requirement",)
_GRE_FIELDS = ("gre_requirement", "test_requirements")


def _interpret(program: Program, fields: tuple[str, ...]) -> dict[str, Any]:
    """Interpret the first stated fact among `fields`; absence → unknown."""
    for field in fields:
        fact = program.facts.get(field)
        if fact is None:
            continue
        interpreted = interpret_requirement(fact.value)
        interpreted.update(
            {
                "from_field": field,
                "source_domain": fact.evidence.source_domain,
                "source_type": fact.evidence.source_type,
                "url": fact.evidence.url,
                "retrieved_at": fact.evidence.retrieved_at,
                "verification_status": fact.status,
            }
        )
        return interpreted
    return {
        "status": "unknown",
        "basis": "",
        "min_overall": None,
        "min_section": None,
        "text": "",
        "from_field": None,
        "source_domain": None,
        "source_type": None,
        "url": None,
        "retrieved_at": None,
        "verification_status": None,
        "note": "Not researched for this program — unknown, not waived.",
    }


def check_exam_requirements(tool_context: ToolContext) -> dict:
    """Build the exam-requirement matrix for every researched program.

    Reads the stored program facts (with their evidence) and the student's
    profile, and returns per program: the interpreted English and GRE
    requirement (required / optional / not_required / conditional / waived
    / unknown), stated minimums, the student's comparison verdict, and the
    evidence trail. Also returns the real gaps — required exams the
    student has no score for. Never treats absence as not_required, and
    never lists an optional exam as a gap.

    Returns:
        Programs with interpreted requirements and verdicts, gaps, and
        follow-up hints (e.g. ask for the lowest IELTS band only when a
        source states per-section minimums).
    """
    knowledge = tool_context.state.get(STATE_KNOWLEDGE)
    knowledge = knowledge if isinstance(knowledge, dict) else {}
    if not knowledge:
        return {
            "status": "error",
            "reason": "no_programs_researched",
            "message": (
                "No programs are researched yet, so there are no stored "
                "requirements to check. Research the named programs first."
            ),
        }

    profile = _read_profile(tool_context.state)
    ielts = profile.test_scores.ielts
    toefl = profile.test_scores.toefl
    gre = profile.test_scores.gre

    programs: list[dict[str, Any]] = []
    gaps: list[str] = []
    ask_hints: list[str] = []

    for raw in knowledge.values():
        program = Program.model_validate(raw)

        english = _interpret(program, _ENGLISH_FIELDS)
        # Comparison uses IELTS when present (the requirement sentences the
        # gate stores are predominantly IELTS-scaled); a TOEFL-only student
        # is surfaced as such rather than force-converted.
        if ielts is not None:
            english["student"] = compare_score(english, ielts, None)
        elif toefl is not None:
            english["student"] = {
                "verdict": "different_test_on_file",
                "note": (
                    f"TOEFL {toefl} is on file; the stated requirement is "
                    "IELTS-scaled — check the program's TOEFL equivalent."
                ),
            }
        else:
            english["student"] = compare_score(english, None, None)

        gre_req = _interpret(program, _GRE_FIELDS)
        gre_req["student"] = compare_score(gre_req, gre, None)

        label = f"{program.university} — {program.name}"
        if english["status"] == "required" and ielts is None and toefl is None:
            gaps.append(
                f"{label}: an English test score is required and none "
                "is on the profile."
            )
        if gre_req["status"] == "required" and gre is None:
            gaps.append(f"{label}: GRE is required and no score is on the profile.")
        if (
            english.get("min_section") is not None
            and english["student"].get("verdict") == "meets_overall_sections_unknown"
        ):
            ask_hints.append(
                f"{label}: the source states per-section minimums — ask the "
                "student for their lowest IELTS band."
            )

        programs.append(
            {
                "university": program.university,
                "program": program.name,
                "english": english,
                "gre": gre_req,
            }
        )

    return {
        "status": "success",
        "programs": programs,
        "gaps": gaps,
        "ask_hints": ask_hints,
        "note": (
            "Statuses come from stored, evidence-graded facts. 'unknown' "
            "means not verified — say so; never present unknown as "
            "not required. Present each requirement with its source and "
            "retrieval date."
        ),
    }


def get_exam_info(exam: str, tool_context: ToolContext) -> dict:
    """Describe one exam's structure: sections, scoring, validity, provider.

    Args:
        exam: One of `ielts`, `toefl`, `pte`, `duolingo`, `gre`, `gmat`.

    Returns:
        The exam's static metadata. Which programs accept or require it is
        a researched program fact, never answered from this reference.
    """
    key = str(exam or "").strip().casefold()
    try:
        info = exam_info(key)
    except KeyError:
        return {
            "status": "error",
            "reason": "unknown_exam",
            "known_exams": sorted(EXAMS),
        }
    return {
        "status": "success",
        "exam": info,
        "note": (
            "Structure only. Acceptance and requirements are program-"
            "specific facts — research the program to state them."
        ),
    }
