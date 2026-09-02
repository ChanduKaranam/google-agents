# -*- coding: utf-8 -*-
"""
Structural + unit tests for placement_agent. No network, no model calls.

Run: python test_placement_agent.py
"""
import sys
import traceback

PASS, FAIL = 0, []


def check(name, fn):
    global PASS
    try:
        fn()
        PASS += 1
        print(f"  ok  {name}")
    except Exception:
        FAIL.append(name)
        print(f"FAIL  {name}")
        traceback.print_exc()


# ---------------------------------------------------------------------------
# 1. ATS scoring — no silent penalty when the student has no JD
# ---------------------------------------------------------------------------

def test_no_jd_weights_redistributed():
    from placement_agent.ats_analyzer import calculate_ats_score
    r = calculate_ats_score(100, 100, 100, job_description="")
    assert r["overall_score"] == 100, f"perfect resume without JD must score 100, got {r['overall_score']}"


def test_no_jd_breakdown_marks_jd_unscored():
    from placement_agent.ats_analyzer import calculate_ats_score
    r = calculate_ats_score(80, 80, 80, job_description="")
    jd = r["breakdown"]["jd_match_score"]
    assert jd.get("scored") is False, "jd_match must be marked unscored when no JD is given"


def test_with_jd_weights_unchanged():
    from placement_agent.ats_analyzer import calculate_ats_score
    r = calculate_ats_score(100, 100, 100, job_description="python developer",
                            jd_match_count=5, jd_total_keywords=10)
    # 35 + 30 + 25 + 0.10*50 = 95
    assert r["overall_score"] == 95, f"JD path must keep original weights, got {r['overall_score']}"


def test_no_jd_overall_beats_old_capped_formula():
    from placement_agent.ats_analyzer import calculate_ats_score
    r = calculate_ats_score(12, 56, 60, job_description="")
    old = int(12 * 0.35 + 56 * 0.30 + 60 * 0.25)  # the pre-fix capped score (36)
    assert r["overall_score"] > old, "no-JD score must not be capped at 90"


# ---------------------------------------------------------------------------
# 2. Fresher-friendly structure — projects/internships cover 'experience'
# ---------------------------------------------------------------------------

def test_projects_satisfy_experience():
    from placement_agent.ats_analyzer import analyze_structure
    sections = {
        "contact": "a@b.c", "summary": "x", "education": "B.Tech",
        "skills": "python, java, sql, git, html",
        "projects": "Built a food ordering site serving 200 users",
    }
    r = analyze_structure(sections)
    assert "experience" not in r["missing_sections"], \
        "experience must not be flagged missing when projects are present"
    assert r["structure_score"] == 100, f"expected 100, got {r['structure_score']}"


def test_experience_still_required_without_projects():
    from placement_agent.ats_analyzer import analyze_structure
    sections = {"contact": "a@b.c", "summary": "x", "education": "B.Tech", "skills": "python"}
    r = analyze_structure(sections)
    assert "experience" in r["missing_sections"]


def test_internships_header_detected_as_experience():
    from placement_agent.resume_parser import get_resume_sections
    text = "Skills\npython, sql\n\nInternships\nSDE Intern at Foo Corp, built X\n"
    r = get_resume_sections(text)
    assert "experience" in r["sections"], f"got sections {r['sections_found']}"


# ---------------------------------------------------------------------------
# 3. Role coverage — QA, core engineering, IT support, campus mass recruiters
# ---------------------------------------------------------------------------

def test_new_role_categories_detected():
    from placement_agent.interview_prep.resources import detect_role_category
    cases = {
        "qa automation tester": "qa_testing",
        "mechanical engineer core company": "core_engineering",
        "it support engineer": "it_support",
        "tcs nqt": "campus_placement",
    }
    for text, expected in cases.items():
        got = detect_role_category(text)
        assert got["matched_category"] == expected, f"{text!r} -> {got['matched_category']}, want {expected}"
        assert got["confidence"] == "high"


def test_new_categories_have_full_question_banks():
    from placement_agent.interview_prep.resources import get_practice_questions, get_prep_strategy, get_resources
    for cat in ("qa_testing", "core_engineering", "it_support", "campus_placement"):
        for diff in ("easy", "medium", "hard"):
            q = get_practice_questions(cat, difficulty=diff, question_type="all")
            assert q["questions"].get("technical"), f"{cat}/{diff}: no technical questions"
            assert q["questions"].get("behavioral"), f"{cat}: no behavioral questions"
        assert get_prep_strategy(cat)["skill_areas"], f"{cat}: no skill areas"
        assert get_resources(cat)["resources"], f"{cat}: no resources"


def test_swe_behavioral_bank_is_fresher_friendly():
    from placement_agent.interview_prep.resources import get_practice_questions
    qs = " ".join(get_practice_questions("software_engineer", question_type="behavioral")["questions"]["behavioral"]).lower()
    assert "project" in qs, "behavioral bank must include project-based (fresher) questions"
    assert "production issue" not in qs, "experienced-only production questions must not be in the default bank"


# ---------------------------------------------------------------------------
# 4. Memory wiring — persist sessions, preload on both agents
# ---------------------------------------------------------------------------

def test_root_agent_persists_sessions_to_memory():
    from placement_agent.agent import root_agent, remember_session
    cbs = root_agent.after_agent_callback
    assert isinstance(cbs, list) and remember_session in cbs, \
        "root agent must call remember_session after each turn"


def test_root_agent_keeps_a2ui_callback():
    from placement_agent.agent import root_agent
    from placement_agent.a2ui.emit import emit_queued_a2ui
    assert emit_queued_a2ui in root_agent.after_agent_callback


def test_preload_memory_on_both_agents():
    from google.adk.tools.preload_memory_tool import PreloadMemoryTool
    from placement_agent.agent import root_agent
    from placement_agent.interview_prep import interview_prep_agent
    for ag in (root_agent, interview_prep_agent):
        assert any(isinstance(t, PreloadMemoryTool) for t in ag.tools), \
            f"{ag.name} must carry PreloadMemoryTool"


# ---------------------------------------------------------------------------
# 5. Instruction contracts — rewrite mode, language, memory honesty
# ---------------------------------------------------------------------------

def test_root_instruction_has_rewrite_mode():
    from placement_agent.agent import root_agent
    ins = root_agent.instruction
    assert "REWRITE" in ins, "instruction must define the rewrite workflow"
    assert "NEVER invent" in ins or "NEVER INVENT" in ins


def test_root_instruction_has_language_rule():
    from placement_agent.agent import root_agent
    assert "language the user writes in" in root_agent.instruction


def test_no_builtin_tools_mixed_with_function_tools():
    # Code rule 1: Gemini built-ins never share an Agent with function tools.
    from google.adk.tools import google_search
    from placement_agent.agent import root_agent
    from placement_agent.interview_prep import interview_prep_agent
    for ag in (root_agent, interview_prep_agent):
        assert google_search not in ag.tools


ALL = [v for k, v in sorted(globals().items()) if k.startswith("test_")]

if __name__ == "__main__":
    for t in ALL:
        check(t.__name__, t)
    print(f"\n{PASS} passed, {len(FAIL)} failed")
    if FAIL:
        sys.exit(1)
