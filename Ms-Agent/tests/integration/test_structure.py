"""Structural wiring — the constraints that keep the design honest.

These run offline and pin the properties that would otherwise fail only in
production: search isolation, the extractor's write-nothing contract, the
budget's coverage of every networked tool, and the instruction content the
conversation depends on.
"""

from __future__ import annotations

from google.adk.tools import AgentTool

from app.agent import RESEARCH_TOOL_NAMES, ROOT_INSTRUCTION, root_agent
from app.agents.profile_agent import create_profile_agent
from app.agents.research_agent import create_research_agent
from app.models.student import ProfileUpdate

FLAT = " ".join(ROOT_INSTRUCTION.split()).lower()


def tool_name(tool: object) -> str:
    return getattr(tool, "__name__", None) or getattr(tool, "name", "")


# --- Root wiring ------------------------------------------------------------


def test_root_holds_exactly_the_expected_tools() -> None:
    names = {tool_name(t) for t in root_agent.tools}
    assert names == {
        "get_profile",
        "update_profile",
        "get_interview_state",
        "convert_gpa",
        "clear_profile",
        "save_research",
        "get_programs",
        "match_programs",
        "get_next_steps",
        "research_agent",
        # ADK wraps task-mode sub-agents as delegation tools.
        "profile_agent",
        "resume_agent",
    }


def test_the_two_extractors_are_the_only_sub_agents() -> None:
    assert [a.name for a in root_agent.sub_agents] == [
        "profile_agent",
        "resume_agent",
    ]


def test_the_budget_covers_every_networked_tool() -> None:
    """Any agent that can reach the web must be inside the search budget."""
    networked = set()
    for tool in root_agent.tools:
        if not isinstance(tool, AgentTool):
            continue
        agent = getattr(tool, "agent", None)
        inner = {tool_name(t) for t in getattr(agent, "tools", [])}
        if "google_search" in inner:
            networked.add(tool_name(tool))
    assert networked
    assert networked <= RESEARCH_TOOL_NAMES


# --- Search isolation -------------------------------------------------------


def test_research_agent_holds_google_search_and_nothing_else() -> None:
    agent = create_research_agent()
    assert len(agent.tools) == 1
    assert tool_name(agent.tools[0]) == "google_search"


def test_research_agent_harvests_grounding() -> None:
    assert create_research_agent().after_agent_callback is not None


# --- The extractor's contract -----------------------------------------------


def test_profile_agent_is_task_mode_with_schemas() -> None:
    agent = create_profile_agent()
    assert agent.mode == "task"
    assert agent.input_schema is not None
    assert agent.output_schema is ProfileUpdate


def test_profile_agent_cannot_write_state() -> None:
    agent = create_profile_agent()
    assert {tool_name(t) for t in agent.tools} <= {"finish_task"}


def test_extractor_instruction_lists_every_profile_section() -> None:
    from app.models.student import StudentProfile

    instruction = create_profile_agent().instruction
    for section in StudentProfile.model_fields:
        assert section in instruction, f"section '{section}' missing"


# --- Instruction content ----------------------------------------------------


def test_greetings_come_before_tool_guidance_and_use_no_tools() -> None:
    section = ROOT_INSTRUCTION.index("## Talking with the student")
    first_tool = ROOT_INSTRUCTION.index("get_profile")
    assert section < first_tool
    assert "call no tools" in FLAT
    assert "who are you" in FLAT


def test_the_memory_rule_is_scoped_away_from_the_assistant() -> None:
    assert "never about you" in FLAT
    assert "can't answer from memory" in FLAT


def test_no_invention_rules_are_present() -> None:
    assert "never invent a university fact" in FLAT
    assert "never do arithmetic yourself" in FLAT
    assert "not from memory" in FLAT


def test_progressive_collection_is_instructed() -> None:
    assert "at most the one question" in FLAT
    assert "one question at a time" in FLAT


def test_match_scores_are_narrated_never_minted() -> None:
    assert "never adjust them" in FLAT
    assert "admission chance" in FLAT  # ...never present as one
