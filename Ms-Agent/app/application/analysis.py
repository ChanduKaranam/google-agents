"""Application analysis — requirements, deadlines and readiness, in code.

Deterministic interpretation over researched application facts:

* Requirement sentences are classified by the exams interpreter
  (`interpret_requirement`) — reused, not re-implemented — so "not
  required" can never read as required, and absence is `unknown`, never a
  default (§6 of the Phase 9 brief).
* LOR counts and reference types are extracted only when literally stated.
* A deadline date parses only when the text states one; a past date is
  `passed` and is never rolled forward to the next cycle (§9).
* Readiness compares researched requirements against the profile and the
  tracked documents, row by row, each with a verdict and the action that
  clears it (§7). Exam rows defer to `check_exam_requirements` — no second
  exam engine.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from app.exams.requirements import interpret_requirement
from app.models.program import Program
from app.models.student import StudentProfile

_WORD_NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}

_LOR_COUNT = re.compile(
    r"(?:at least\s+)?(one|two|three|four|five|\d)\s+"
    r"(?:letters?|references?|recommendations?)",
    re.IGNORECASE,
)

_MONTHS = {
    name: index
    for index, names in enumerate(
        (
            ("january", "jan"),
            ("february", "feb"),
            ("march", "mar"),
            ("april", "apr"),
            ("may",),
            ("june", "jun"),
            ("july", "jul"),
            ("august", "aug"),
            ("september", "sep", "sept"),
            ("october", "oct"),
            ("november", "nov"),
            ("december", "dec"),
        ),
        start=1,
    )
    for name in names
}
_MONTH_PATTERN = "|".join(sorted(_MONTHS, key=len, reverse=True))
_ISO_DATE = re.compile(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b")
_MONTH_FIRST = re.compile(
    rf"\b({_MONTH_PATTERN})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(20\d{{2}})",
    re.IGNORECASE,
)
_DAY_FIRST = re.compile(
    rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({_MONTH_PATTERN})\.?\s+(20\d{{2}})",
    re.IGNORECASE,
)


def interpret_document_requirement(text: str) -> dict[str, Any]:
    """Interpret a document-requirement sentence.

    Same interpreter as exams, with one difference in what `unknown`
    means: these slots hold the program's own requirements listing, so a
    bare listing ("Three letters of recommendation") is a positive
    statement and reads as required. Negations, "optional" and conditions
    still win — they are checked first — and a slot nothing researched
    remains unknown, because there is no text at all.
    """
    interpretation = interpret_requirement(text)
    if interpretation["status"] == "unknown" and str(text or "").strip():
        interpretation = {
            **interpretation,
            "status": "required",
            "basis": "stated on the requirements page without qualifiers",
        }
    return interpretation


def extract_lor_details(text: str) -> dict[str, Any]:
    """LOR count and reference type — only what the text states."""
    raw = str(text or "")
    flat = raw.casefold()
    count: int | None = None
    match = _LOR_COUNT.search(raw)
    if match:
        token = match.group(1).casefold()
        count = _WORD_NUMBERS.get(token) or (int(token) if token.isdigit() else None)
    has_academic = "academic" in flat
    has_professional = "professional" in flat
    if has_academic and has_professional:
        reference_type = "mixed"
    elif has_academic:
        reference_type = "academic"
    elif has_professional:
        reference_type = "professional"
    else:
        reference_type = None
    return {"count": count, "reference_type": reference_type}


def parse_deadline_date(text: str) -> date | None:
    """A concrete date, only when the text literally states one."""
    raw = str(text or "")
    iso = _ISO_DATE.search(raw)
    if iso:
        try:
            return date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
        except ValueError:
            return None
    month_first = _MONTH_FIRST.search(raw)
    if month_first:
        month = _MONTHS[month_first.group(1).casefold()]
        try:
            return date(int(month_first.group(3)), month, int(month_first.group(2)))
        except ValueError:
            return None
    day_first = _DAY_FIRST.search(raw)
    if day_first:
        month = _MONTHS[day_first.group(2).casefold()]
        try:
            return date(int(day_first.group(3)), month, int(day_first.group(1)))
        except ValueError:
            return None
    return None


def deadline_urgency(deadline_text: str, today: date) -> dict[str, Any]:
    """Days remaining and urgency — from a stated date, never an assumed one."""
    parsed = parse_deadline_date(deadline_text)
    if parsed is None:
        return {
            "deadline_date": None,
            "days_remaining": None,
            "urgency": "unknown",
            "note": (
                "The stored deadline text states no parseable date — verify "
                "it on the program page before planning around it."
            ),
        }
    days = (parsed - today).days
    if days < 0:
        urgency, note = (
            "passed",
            f"The stored deadline ({parsed.isoformat()}) has passed — verify "
            "the current cycle's deadline; never assume it repeats.",
        )
    elif days <= 30:
        urgency, note = "urgent", f"{days} days remaining."
    elif days <= 90:
        urgency, note = "soon", f"{days} days remaining."
    else:
        urgency, note = "comfortable", f"{days} days remaining."
    return {
        "deadline_date": parsed.isoformat(),
        "days_remaining": days,
        "urgency": urgency,
        "note": note,
    }


# Requirement slot → (tracked document key, human label). Exam slots are
# handled separately — their verdicts belong to check_exam_requirements.
_DOCUMENT_REQUIREMENTS: tuple[tuple[str, str, str], ...] = (
    ("sop_requirement", "sop", "SOP"),
    ("lor_requirement", "lor", "letters of recommendation"),
    ("transcript_requirement", "transcripts", "transcripts"),
    ("resume_requirement", "resume", "resume"),
    ("portfolio_requirement", "portfolio", "portfolio"),
)

_EXAM_REQUIREMENTS: tuple[tuple[str, str], ...] = (
    ("english_requirement", "English test"),
    ("gre_requirement", "GRE"),
)

_REVIEW_REQUIREMENTS: tuple[str, ...] = (
    "prerequisite_requirement",
    "additional_documents",
)

APPLICATION_REQUIREMENT_FIELDS: tuple[str, ...] = (
    *(field for field, _, _ in _DOCUMENT_REQUIREMENTS),
    *(field for field, _ in _EXAM_REQUIREMENTS),
    *_REVIEW_REQUIREMENTS,
    "application_portal",
    "application_fee",
    "application_deadline",
)

_DOC_READY = ("ready", "submitted", "verified")


def _row(
    field: str,
    fact: Any,
    verdict: str,
    action: str,
    interpretation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "requirement": field,
        "value": fact.value,
        "interpretation": interpretation or interpret_requirement(fact.value),
        "verdict": verdict,
        "action": action,
        "source_domain": fact.evidence.source_domain,
        "retrieved_at": fact.evidence.retrieved_at,
    }


def application_readiness(
    profile: StudentProfile,
    program: Program,
    documents: dict[str, str],
) -> dict[str, Any]:
    """Profile + tracked documents vs researched requirements, row by row."""
    rows: list[dict[str, Any]] = []

    for field, doc_key, label in _DOCUMENT_REQUIREMENTS:
        fact = program.facts.get(field)
        if fact is None:
            continue
        interpretation = interpret_document_requirement(fact.value)
        status = interpretation["status"]
        doc_state = str(documents.get(doc_key, "missing"))
        if status in ("not_required", "waived"):
            verdict, action = "not_needed", "Nothing to do — the source says so."
        elif status == "optional":
            verdict, action = (
                "optional",
                f"Optional per the source — submit a {label} only if it "
                "strengthens the application.",
            )
        elif status == "conditional":
            verdict, action = (
                "conditional",
                f"Conditional — the source's own words decide: {fact.value}",
            )
        elif status == "unknown":
            verdict, action = (
                "unknown",
                f"The stored text does not establish whether the {label} "
                "is required — verify on the program page.",
            )
        elif doc_state in _DOC_READY:
            verdict, action = "ready", f"Your {label} is {doc_state}."
        elif doc_state == "draft":
            verdict, action = "in_progress", f"Finish the {label} draft."
        else:
            verdict, action = "missing", f"Prepare your {label}: {fact.value}"
        row = _row(field, fact, verdict, action, interpretation)
        if field == "lor_requirement":
            row["lor_details"] = extract_lor_details(fact.value)
        rows.append(row)

    for field, label in _EXAM_REQUIREMENTS:
        fact = program.facts.get(field)
        if fact is None:
            continue
        status = interpret_requirement(fact.value)["status"]
        has_score = (
            profile.test_scores.gre is not None
            if field == "gre_requirement"
            else (
                profile.test_scores.ielts is not None
                or profile.test_scores.toefl is not None
            )
        )
        if status in ("not_required", "waived"):
            verdict, action = "not_needed", "Nothing to do — the source says so."
        elif status == "optional":
            verdict, action = (
                "optional",
                f"{label} is optional per the source — a strong score can "
                "still help; never required.",
            )
        elif status == "conditional":
            verdict, action = (
                "conditional",
                f"Conditional — the source's own words decide: {fact.value}",
            )
        elif has_score:
            verdict, action = (
                "have_score",
                "Score on file — verify the stated minimums with "
                "check_exam_requirements.",
            )
        elif status == "required":
            verdict, action = "missing", f"Book the {label} — this program requires it."
        else:
            verdict, action = (
                "unknown",
                f"Whether the {label} is required is not established — "
                "verify on the program page.",
            )
        rows.append(_row(field, fact, verdict, action))

    for field in _REVIEW_REQUIREMENTS:
        fact = program.facts.get(field)
        if fact is None:
            continue
        rows.append(
            _row(field, fact, "review", f"Review against your record: {fact.value}")
        )

    unknown_requirements = sorted(
        field
        for field in APPLICATION_REQUIREMENT_FIELDS
        if field not in program.facts
    )
    if not rows:
        overall = "unknown"
    elif any(r["verdict"] == "missing" for r in rows):
        overall = "not_ready"
    elif any(r["verdict"] == "in_progress" for r in rows):
        overall = "in_progress"
    else:
        overall = "ready"
    return {
        "rows": rows,
        "overall": overall,
        "unknown_requirements": unknown_requirements,
        "note": (
            "Verdicts come only from researched requirements, the profile "
            "and tracked documents. An unresearched requirement is unknown "
            "— never assumed either way."
        ),
    }
