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
        "interpret_reply",
        "convert_gpa",
        "clear_profile",
        "save_research",
        "get_programs",
        "resolve_university_name",
        "analyze_career_outcomes",
        "compare_programs",
        "find_faculty_matches",
        "match_programs",
        "get_next_steps",
        "check_exam_requirements",
        "get_exam_info",
        "convert_score",
        "compare_english_tests",
        "calculate_total_cost",
        "calculate_budget_fit",
        "convert_money",
        "calculate_loan_emi",
        "calculate_payback",
        "plan_financial_research",
        "save_finance_research",
        "build_cost_breakdown",
        "get_funding_options",
        "check_application_requirements",
        "track_application",
        "update_document_status",
        "get_application_dashboard",
        "get_strategy_readiness",
        "recommend_exam_plan",
        "build_recommendations",
        "build_action_plan",
        "save_alumni_findings",
        "get_alumni_signals",
        "research_agent",
        "alumni_agent",
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


# --- Conversational intelligence (precedence refactor) ------------------------


def test_precedence_is_automatic_never_a_reconciliation_question() -> None:
    assert "never ask the student to reconcile" in FLAT
    assert "never reopen a superseded value" in FLAT
    assert "what the student says now always beats what history says" in FLAT


def test_action_beats_interrogation() -> None:
    assert "prefer acting over asking" in FLAT
    assert "never interrogate past the point of usefulness" in FLAT


def test_short_replies_are_answers_in_context() -> None:
    assert "interpret_reply" in ROOT_INSTRUCTION
    assert "never re-ask the question the student just answered" in FLAT


def test_state_management_is_never_narrated() -> None:
    assert "never narrate state management" in FLAT
    assert "i have updated your profile" in FLAT  # named as the forbidden form


def test_corrections_apply_instantly_without_permission() -> None:
    assert "corrections are instant" in FLAT
    assert "never ask permission to update" in FLAT


def test_match_scores_are_narrated_never_minted() -> None:
    assert "never adjust them" in FLAT
    assert "admission chance" in FLAT  # ...never present as one


# --- Alumni agent wiring ----------------------------------------------------


def test_alumni_agent_is_search_only_and_harvests() -> None:
    from app.agents.alumni_agent import create_alumni_agent

    agent = create_alumni_agent()
    assert len(agent.tools) == 1
    assert tool_name(agent.tools[0]) == "google_search"
    assert agent.after_agent_callback is not None


def test_alumni_agent_is_inside_the_search_budget() -> None:
    assert "alumni_agent" in RESEARCH_TOOL_NAMES


def test_alumni_instruction_scopes_to_approved_sources() -> None:
    from app.agents.alumni_agent import INSTRUCTION

    flat = " ".join(INSTRUCTION.split()).lower()
    assert "site:linkedin.com/in" in flat
    assert "ignored" in flat  # unapproved results are ignored
    assert "public information only" in flat
    assert "no emails, phones" in flat
    assert "found: none" in flat


def test_root_alumni_section_pins_the_presentation_rules() -> None:
    assert "only admitted people may be named" in FLAT
    assert "denominator" in FLAT
    assert "never a guarantee" in FLAT
    assert "approved sources" in FLAT


# --- Exams domain wiring ----------------------------------------------------


def test_exams_instruction_pins_the_unknown_rule() -> None:
    """Absence is unknown, never not_required — the domain's classic trap."""
    assert "never present unknown" in FLAT
    assert "check_exam_requirements" in ROOT_INSTRUCTION
    assert "requirements never transfer between programs" in FLAT


def test_exams_never_declare_a_universal_test_winner() -> None:
    assert "never declare a universal winner" in FLAT
    assert "get_exam_info" in ROOT_INSTRUCTION


# --- Calculation domain wiring ----------------------------------------------


def test_calculation_instruction_forbids_head_math_and_universal_conversion() -> None:
    assert "no universal cgpa conversion" in FLAT
    assert "never compute" in FLAT
    assert "explicit rate with source and date" in FLAT


def test_payback_language_is_assumption_bound() -> None:
    assert "under these assumptions" in FLAT
    assert "never a promise of recovery" in FLAT


# --- University domain wiring -------------------------------------------------


def test_university_instruction_pins_the_comparison_rules() -> None:
    assert "unknown stays unknown" in FLAT
    assert "never produce a single composite ranking" in FLAT
    assert "compare_programs" in ROOT_INSTRUCTION


def test_faculty_rules_forbid_supervision_claims() -> None:
    assert "will supervise" in FLAT  # ...never state or imply
    assert "find_faculty_matches" in ROOT_INSTRUCTION


def test_ambiguous_names_are_questions() -> None:
    assert "resolve_university_name" in ROOT_INSTRUCTION
    assert "never guess" in FLAT


# --- Strategy domain wiring ---------------------------------------------------


def test_the_strategy_flow_is_readiness_first() -> None:
    for tool in (
        "get_strategy_readiness",
        "build_recommendations",
        "recommend_exam_plan",
        "build_action_plan",
    ):
        assert tool in ROOT_INSTRUCTION, tool
    assert ROOT_INSTRUCTION.index("get_strategy_readiness") < ROOT_INSTRUCTION.index(
        "build_recommendations"
    )


def test_strategy_research_beats_interrogation() -> None:
    assert "they can be researched" in FLAT
    assert "research can answer" in FLAT


def test_strategy_categories_are_fit_language_never_estimates() -> None:
    assert "never an admission estimate" in FLAT
    assert "never a data dump" in FLAT
    assert "building their path" in FLAT


# --- Application domain wiring ------------------------------------------------


def test_the_application_flow_is_research_first() -> None:
    for tool in (
        "check_application_requirements",
        "track_application",
        "update_document_status",
        "get_application_dashboard",
    ):
        assert tool in ROOT_INSTRUCTION, tool
    assert "never assume a requirement" in FLAT
    assert "never roll a date forward" in FLAT


def test_readiness_is_never_an_admission_judgment() -> None:
    assert "never an admission judgment" in FLAT


# --- Finance domain wiring ----------------------------------------------------


def test_the_finance_flow_is_wired_planner_first() -> None:
    for tool in (
        "plan_financial_research",
        "save_finance_research",
        "build_cost_breakdown",
        "get_funding_options",
    ):
        assert tool in ROOT_INSTRUCTION, tool
    # The planner comes before any money research.
    assert ROOT_INSTRUCTION.index("plan_financial_research") < ROOT_INSTRUCTION.index(
        "save_finance_research"
    )


def test_finance_promises_are_forbidden() -> None:
    assert "never promise a scholarship" in FLAT
    assert "never assumed tuition funding" in FLAT
    assert "not a financial advisor" in FLAT
    assert "never collapse a range" in FLAT


def test_finance_freshness_is_relayed_as_its_year() -> None:
    assert "the latest official fee information i could verify" in FLAT


def test_finance_adds_no_second_research_engine() -> None:
    """§36: the finance domain reuses the one research path."""
    networked = set()
    for tool in root_agent.tools:
        if isinstance(tool, AgentTool):
            agent = getattr(tool, "agent", None)
            if "google_search" in {
                tool_name(t) for t in getattr(agent, "tools", [])
            }:
                networked.add(tool_name(tool))
    assert networked == RESEARCH_TOOL_NAMES == {"research_agent", "alumni_agent"}


# --- Placement domain wiring --------------------------------------------------


def test_placement_instruction_pins_scope_and_example_rules() -> None:
    assert "scope is sacred" in FLAT
    assert "individuals are not statistics" in FLAT
    assert "analyze_career_outcomes" in ROOT_INSTRUCTION


def test_no_placement_probabilities_are_promised() -> None:
    assert "never an employment probability" in FLAT
