"""University analysis tools — comparison, faculty matching, resolution.

All three operate on state and static metadata only: research happens
first through the shared research system, and these interpret what the
gate admitted. No searches here, no universal scores, no leakage between
programs, and unknown stays unknown.
"""

from __future__ import annotations

from typing import Any

from google.adk.tools import ToolContext

from app.config.settings import STATE_KNOWLEDGE
from app.models.program import Program
from app.tools.profile_tools import _read_profile
from app.university.analysis import assess_deadline_freshness, match_faculty
from app.university.resolution import resolve_university

# The comparison dimensions, in presentation order.
_DIMENSIONS = (
    "location",
    "duration",
    "structure",
    "curriculum",
    "tuition",
    "tuition_currency",
    "application_deadline",
    "intake",
    "english_requirement",
    "gre_requirement",
    "gpa_requirement",
    "faculty_research",
    "research_labs",
    "scholarships",
    "coop_available",
)


def resolve_university_name(name: str, tool_context: ToolContext) -> dict:
    """Resolve a university alias to its official name.

    Args:
        name: What the student typed, e.g. `UBC`, `UofT`, `Waterloo`.

    Returns:
        `resolved` with the official name, `ambiguous` with candidates
        (ask the student which they mean), or `unknown` (research can
        proceed with the name as given).
    """
    return resolve_university(name)


def compare_programs(tool_context: ToolContext) -> dict:
    """Compare every researched program across the standard dimensions.

    Renders stored, evidence-graded facts only: a dimension nothing
    verified is `unknown`, facts never transfer between programs, every
    known value carries its source and retrieval date, deadlines carry a
    freshness assessment against the student's target intake, and recorded
    source conflicts are surfaced. No universal score exists — present
    trade-offs in words.

    Returns:
        A per-program matrix over the standard dimensions.
    """
    knowledge = tool_context.state.get(STATE_KNOWLEDGE)
    knowledge = knowledge if isinstance(knowledge, dict) else {}
    if not knowledge:
        return {
            "status": "error",
            "reason": "no_programs_researched",
            "message": "Nothing is researched yet — research programs first.",
        }
    profile = _read_profile(tool_context.state)
    target_intake = profile.target.intake or ""

    matrix: list[dict[str, Any]] = []
    for raw in knowledge.values():
        program = Program.model_validate(raw)
        dimensions: dict[str, Any] = {}
        for dimension in _DIMENSIONS:
            fact = program.facts.get(dimension)
            if fact is None:
                dimensions[dimension] = {
                    "status": "unknown",
                    "note": "Not verified for this program.",
                }
                continue
            cell: dict[str, Any] = {
                "status": fact.status,
                "value": fact.value,
                "source_domain": fact.evidence.source_domain,
                "source_type": fact.evidence.source_type,
                "url": fact.evidence.url,
                "retrieved_at": fact.evidence.retrieved_at,
            }
            if fact.conflicts:
                cell["conflicts"] = fact.conflicts
            if dimension == "application_deadline":
                cell["freshness"] = assess_deadline_freshness(fact.value, target_intake)
            dimensions[dimension] = cell
        matrix.append(
            {
                "university": program.university,
                "program": program.name,
                "country": program.country,
                "dimensions": dimensions,
            }
        )
    return {
        "status": "success",
        "matrix": matrix,
        "note": (
            "Present trade-offs in words, never a single composite number. "
            "Unknown dimensions are stated as unknown — never filled. "
            "Surface any conflicts with both sources, and relay deadline "
            "freshness (stale cycles are historical, not current)."
        ),
    }


def find_faculty_matches(tool_context: ToolContext) -> dict:
    """Match the student's stated research interests to researched faculty.

    Uses only `faculty_research` facts already admitted by the research
    gate, and only interests the student actually stated (research
    interests, specialization, stated skills). Every match names its
    overlap; no overlap means no match; supervision availability is never
    implied.

    Returns:
        Per-university matches with the overlapping terms and sources.
    """
    profile = _read_profile(tool_context.state)
    interests = [
        *profile.research.research_interests,
        *([profile.target.specialization] if profile.target.specialization else []),
        *profile.technical.skills,
    ]
    knowledge = tool_context.state.get(STATE_KNOWLEDGE)
    knowledge = knowledge if isinstance(knowledge, dict) else {}
    with_faculty = [
        Program.model_validate(raw)
        for raw in knowledge.values()
        if "faculty_research" in (raw.get("facts") or {})
    ]
    if not with_faculty:
        return {
            "status": "error",
            "reason": "no_faculty_researched",
            "message": (
                "No faculty-research facts are stored yet. Research the "
                "universities' faculty pages first."
            ),
        }
    universities = []
    for program in with_faculty:
        fact = program.facts["faculty_research"]
        result = match_faculty(interests, fact.value)
        universities.append(
            {
                "university": program.university,
                "program": program.name,
                "status": result["status"],
                "matched": result.get("matched", []),
                "note": result["note"],
                "source_domain": fact.evidence.source_domain,
                "url": fact.evidence.url,
                "retrieved_at": fact.evidence.retrieved_at,
            }
        )
    return {
        "status": "success",
        "universities": universities,
        "note": (
            "Published-research alignment only. Never state or imply that "
            "a professor will supervise or accept the student."
        ),
    }
