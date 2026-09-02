"""
suggestions.py
Tools for generating targeted, actionable resume improvement recommendations
based on ATS analysis results. Each suggestion is prioritized and step-by-step.
"""

from typing import Optional

# ---------------------------------------------------------------------------
# Priority levels
# ---------------------------------------------------------------------------
PRIORITY_CRITICAL = "CRITICAL"   # Will almost certainly cause ATS rejection
PRIORITY_HIGH     = "HIGH"       # Significantly impacts score
PRIORITY_MEDIUM   = "MEDIUM"     # Noticeable improvement
PRIORITY_LOW      = "LOW"        # Polish / nice-to-have


def _make_suggestion(priority: str, category: str, issue: str, steps: list[str]) -> dict:
    return {
        "priority": priority,
        "category": category,
        "issue": issue,
        "steps": steps,
    }


# ---------------------------------------------------------------------------
# Per-dimension suggestion generators
# ---------------------------------------------------------------------------

def _keyword_suggestions(keyword_analysis: dict) -> list[dict]:
    suggestions = []

    # Missing action verbs
    missing_verbs = keyword_analysis.get("action_verbs_missing", [])
    if missing_verbs:
        top_verbs = missing_verbs[:8]
        suggestions.append(_make_suggestion(
            priority=PRIORITY_HIGH,
            category="Keyword Optimization",
            issue="Insufficient action verbs — ATS systems and recruiters look for strong opening verbs on bullet points.",
            steps=[
                "Review each bullet point in your Experience section.",
                f"Start bullets with strong action verbs such as: {', '.join(top_verbs)}.",
                "Replace weak openers like 'Responsible for' or 'Helped with' with direct action verbs.",
                "Example: ❌ 'Responsible for managing a team' → ✅ 'Led a cross-functional team of 8 engineers'.",
            ],
        ))

    # Measurable achievements
    measure_found = keyword_analysis.get("measurable_terms_found", [])
    if len(measure_found) < 2:
        suggestions.append(_make_suggestion(
            priority=PRIORITY_CRITICAL,
            category="Quantified Achievements",
            issue="No quantified achievements found — resumes without metrics are consistently ranked lower by ATS.",
            steps=[
                "For every role in your Experience section, add at least one measurable result.",
                "Use numbers, percentages, timeframes, or dollar values.",
                "Ask yourself: How much? How many? How fast? What was the impact?",
                "Example: ❌ 'Improved sales performance' → ✅ 'Increased quarterly sales by 32% over 6 months'.",
                "Example: ❌ 'Managed cloud infrastructure' → ✅ 'Reduced AWS costs by $18K/year through resource optimization'.",
            ],
        ))

    # Soft skills
    soft_found = keyword_analysis.get("soft_skills_found", [])
    if len(soft_found) < 3:
        suggestions.append(_make_suggestion(
            priority=PRIORITY_MEDIUM,
            category="Soft Skills",
            issue="Few soft skills detected — many job descriptions require these and ATS scans for them.",
            steps=[
                "Add a concise professional summary at the top of your resume.",
                "Weave soft skills naturally into your experience bullets rather than just listing them.",
                "Target skills like: communication, leadership, collaboration, problem-solving, adaptability.",
                "Example: '…collaborating with cross-functional teams to deliver the project on schedule.'",
            ],
        ))

    # JD keyword gaps
    jd_missing = keyword_analysis.get("jd_keywords_missing", [])
    if jd_missing:
        top_missing = jd_missing[:10]
        suggestions.append(_make_suggestion(
            priority=PRIORITY_CRITICAL,
            category="Job Description Alignment",
            issue=f"Your resume is missing {len(jd_missing)} keywords from the job description.",
            steps=[
                "Open the job description side-by-side with your resume.",
                f"These high-priority missing keywords should be incorporated: {', '.join(top_missing)}.",
                "For each missing keyword, find a genuine place in your experience or skills to include it.",
                "Do NOT keyword-stuff — integrate naturally into bullet points or the summary.",
                "Mirror the exact phrasing used in the JD (e.g., if they say 'CI/CD pipelines', use that exact phrase).",
            ],
        ))

    return suggestions


def _formatting_suggestions(formatting_analysis: dict) -> list[dict]:
    suggestions = []

    issues = formatting_analysis.get("issues_found", [])
    warnings = formatting_analysis.get("warnings", [])
    length_status = formatting_analysis.get("length_status", "ideal")
    bullet_count = formatting_analysis.get("bullet_count", 0)
    has_email = formatting_analysis.get("has_email", True)
    has_phone = formatting_analysis.get("has_phone", True)
    has_linkedin = formatting_analysis.get("has_linkedin", False)

    # Contact info
    if not has_email:
        suggestions.append(_make_suggestion(
            priority=PRIORITY_CRITICAL,
            category="Contact Information",
            issue="No email address found — ATS systems and recruiters cannot contact you.",
            steps=[
                "Add a professional email address to the top of your resume.",
                "Use a format like firstname.lastname@gmail.com.",
                "Avoid unprofessional addresses (e.g., coolhacker99@hotmail.com).",
            ],
        ))

    if not has_phone:
        suggestions.append(_make_suggestion(
            priority=PRIORITY_HIGH,
            category="Contact Information",
            issue="No phone number detected.",
            steps=[
                "Add your phone number in the header/contact section.",
                "Format: +1 (555) 123-4567 or 555-123-4567.",
            ],
        ))

    if not has_linkedin:
        suggestions.append(_make_suggestion(
            priority=PRIORITY_MEDIUM,
            category="Contact Information",
            issue="No LinkedIn profile URL found.",
            steps=[
                "Add your LinkedIn URL: linkedin.com/in/yourname.",
                "Ensure your LinkedIn profile is complete and matches your resume.",
                "A LinkedIn URL adds credibility and is expected in most tech/corporate roles.",
            ],
        ))

    # Length
    if length_status == "too_short":
        suggestions.append(_make_suggestion(
            priority=PRIORITY_HIGH,
            category="Resume Length",
            issue="Resume is too short. ATS systems may not find enough content to rank it accurately.",
            steps=[
                "Expand your Experience section with detailed bullet points (3-5 per role).",
                "Add a Professional Summary (3-4 sentences about your background and goals).",
                "Include a Projects section with descriptions if you lack extensive work experience.",
                "Add any certifications, courses, or volunteer experience.",
                "Target 400-600 words for a single-page resume.",
            ],
        ))
    elif length_status == "too_long":
        suggestions.append(_make_suggestion(
            priority=PRIORITY_MEDIUM,
            category="Resume Length",
            issue="Resume is longer than recommended. Conciseness improves ATS parsing reliability.",
            steps=[
                "Limit to one page (or two pages max for 10+ years of experience).",
                "Remove roles older than 10-15 years unless highly relevant.",
                "Cut bullets that don't demonstrate clear impact or relevance.",
                "Combine similar bullet points into one stronger statement.",
            ],
        ))

    # Bullet points
    if bullet_count < 5:
        suggestions.append(_make_suggestion(
            priority=PRIORITY_HIGH,
            category="Formatting Structure",
            issue=f"Only {bullet_count} bullet point(s) found. Dense paragraphs are harder for ATS to parse.",
            steps=[
                "Convert paragraphs in your Experience section into concise bullet points.",
                "Each bullet should follow the format: [Action Verb] + [Task] + [Result/Impact].",
                "Aim for 3-5 bullets per job role.",
                "Keep each bullet to 1-2 lines (15-25 words is ideal).",
            ],
        ))

    # ATS-unfriendly elements
    for issue in issues:
        if "table" in issue.lower() or "column" in issue.lower():
            suggestions.append(_make_suggestion(
                priority=PRIORITY_CRITICAL,
                category="ATS-Unfriendly Formatting",
                issue="Tables or multi-column layouts detected — most ATS systems cannot parse these correctly.",
                steps=[
                    "Rebuild your resume using a single-column, left-aligned layout.",
                    "Replace table-based skills grids with a comma-separated or bulleted list.",
                    "Use standard fonts: Arial, Calibri, Times New Roman, or Helvetica.",
                    "Test by copying your resume text into Notepad — it should read in logical order.",
                ],
            ))
        if "special_chars" in issue.lower() or "symbol" in issue.lower():
            suggestions.append(_make_suggestion(
                priority=PRIORITY_HIGH,
                category="ATS-Unfriendly Formatting",
                issue="Overuse of special characters/symbols detected.",
                steps=[
                    "Replace decorative symbols (★, ✓, ►) with standard hyphens or plain bullets.",
                    "ATS systems often convert unsupported characters to garbled text.",
                    "Use only standard ASCII characters in your resume.",
                ],
            ))

    return suggestions


def _structure_suggestions(structure_analysis: dict) -> list[dict]:
    suggestions = []

    missing_sections = structure_analysis.get("missing_sections", [])
    notes = structure_analysis.get("notes", [])

    section_guidance = {
        "contact": {
            "priority": PRIORITY_CRITICAL,
            "steps": [
                "Add a Contact Information section at the very top of your resume.",
                "Include: Full Name, Phone, Email, LinkedIn URL, City/State (optional).",
                "Do NOT include full street address — city and state is sufficient.",
            ],
        },
        "summary": {
            "priority": PRIORITY_HIGH,
            "steps": [
                "Add a Professional Summary section directly below your contact info.",
                "Write 2-4 sentences: who you are, your top skills, and your career goal.",
                "Pack it with keywords that match your target role.",
                "Example: 'Results-driven Software Engineer with 5 years of experience in Python, "
                "AWS, and microservices. Proven track record of delivering scalable systems "
                "and reducing infrastructure costs. Seeking a senior backend role at a growth-stage company.'",
            ],
        },
        "experience": {
            "priority": PRIORITY_CRITICAL,
            "steps": [
                "Add a Work Experience section listing your relevant roles.",
                "For each role include: Job Title, Company, Location, Dates (Month/Year).",
                "List 3-5 bullet points per role describing your accomplishments.",
                "Focus on impact and results, not just duties.",
            ],
        },
        "education": {
            "priority": PRIORITY_HIGH,
            "steps": [
                "Add an Education section with your highest degree first.",
                "Include: Degree, Major, Institution, Graduation Year.",
                "Add GPA if above 3.5, and relevant coursework if you're a recent graduate.",
            ],
        },
        "skills": {
            "priority": PRIORITY_HIGH,
            "steps": [
                "Add a dedicated Skills section for fast ATS keyword matching.",
                "Separate into categories: Technical Skills, Tools, Languages, Soft Skills.",
                "Use the exact terminology from job descriptions (e.g., 'React.js' not just 'React').",
                "Avoid rating systems like stars or bars — ATS cannot parse them.",
            ],
        },
    }

    for section in missing_sections:
        if section in section_guidance:
            guide = section_guidance[section]
            suggestions.append(_make_suggestion(
                priority=guide["priority"],
                category="Missing Section",
                issue=f"'{section.title()}' section is missing — this is expected by most ATS systems.",
                steps=guide["steps"],
            ))

    # Add notes from structure analysis as LOW priority improvements
    for note in notes:
        suggestions.append(_make_suggestion(
            priority=PRIORITY_MEDIUM,
            category="Section Quality",
            issue=note,
            steps=[
                "Review the relevant section and expand its content.",
                "Use specific, achievement-oriented language.",
                "Cross-check against the target job description for alignment.",
            ],
        ))

    return suggestions


# ---------------------------------------------------------------------------
# Public ADK tool functions
# ---------------------------------------------------------------------------

def generate_improvement_suggestions(
    keyword_analysis: dict,
    formatting_analysis: dict,
    structure_analysis: dict,
) -> dict:
    """
    Generate a prioritized, actionable list of resume improvement suggestions.

    Args:
        keyword_analysis: Result from analyze_keywords().
        formatting_analysis: Result from analyze_formatting().
        structure_analysis: Result from analyze_structure().

    Returns:
        dict with:
          - suggestions (list): all improvement suggestions, each with priority/category/issue/steps
          - total_suggestions (int)
          - critical_count (int)
          - high_count (int)
          - medium_count (int)
          - low_count (int)
          - quick_wins (list): top 3 easiest high-impact improvements
    """
    all_suggestions: list[dict] = []
    all_suggestions.extend(_keyword_suggestions(keyword_analysis))
    all_suggestions.extend(_formatting_suggestions(formatting_analysis))
    all_suggestions.extend(_structure_suggestions(structure_analysis))

    # Sort by priority: CRITICAL > HIGH > MEDIUM > LOW
    priority_order = {
        PRIORITY_CRITICAL: 0,
        PRIORITY_HIGH: 1,
        PRIORITY_MEDIUM: 2,
        PRIORITY_LOW: 3,
    }
    all_suggestions.sort(key=lambda s: priority_order.get(s["priority"], 99))

    counts = {
        "critical_count": sum(1 for s in all_suggestions if s["priority"] == PRIORITY_CRITICAL),
        "high_count": sum(1 for s in all_suggestions if s["priority"] == PRIORITY_HIGH),
        "medium_count": sum(1 for s in all_suggestions if s["priority"] == PRIORITY_MEDIUM),
        "low_count": sum(1 for s in all_suggestions if s["priority"] == PRIORITY_LOW),
    }

    # Quick wins: first 3 MEDIUM or HIGH suggestions with fewest steps
    quick_win_pool = [s for s in all_suggestions if s["priority"] in (PRIORITY_HIGH, PRIORITY_MEDIUM)]
    quick_win_pool.sort(key=lambda s: len(s["steps"]))
    quick_wins = quick_win_pool[:3]

    return {
        "suggestions": all_suggestions,
        "total_suggestions": len(all_suggestions),
        **counts,
        "quick_wins": quick_wins,
    }


def generate_step_by_step_action_plan(suggestions: list[dict]) -> dict:
    """
    Convert the suggestion list into a numbered, step-by-step action plan
    grouped by priority tier.

    Args:
        suggestions: The 'suggestions' list from generate_improvement_suggestions().

    Returns:
        dict with:
          - action_plan (dict): keyed by priority tier, each containing ordered action items
          - estimated_effort (str): rough time estimate to implement all changes
          - total_steps (int)
    """
    plan: dict[str, list[dict]] = {
        PRIORITY_CRITICAL: [],
        PRIORITY_HIGH: [],
        PRIORITY_MEDIUM: [],
        PRIORITY_LOW: [],
    }

    step_number = 1
    total_steps = 0

    for suggestion in suggestions:
        tier = suggestion.get("priority", PRIORITY_LOW)
        action_item = {
            "step": step_number,
            "category": suggestion["category"],
            "what_to_fix": suggestion["issue"],
            "how_to_fix": suggestion["steps"],
        }
        plan[tier].append(action_item)
        step_number += 1
        total_steps += len(suggestion["steps"])

    # Estimate effort
    critical_count = len(plan[PRIORITY_CRITICAL])
    high_count = len(plan[PRIORITY_HIGH])
    if critical_count == 0 and high_count == 0:
        effort = "30-60 minutes (mostly polish)"
    elif critical_count <= 2:
        effort = "1-2 hours (some key changes needed)"
    elif critical_count <= 4:
        effort = "2-4 hours (significant revisions required)"
    else:
        effort = "4-8 hours (major rewrite recommended)"

    # Remove empty tiers
    plan_clean = {k: v for k, v in plan.items() if v}

    return {
        "action_plan": plan_clean,
        "estimated_effort": effort,
        "total_steps": total_steps,
    }


def compare_resume_versions(
    previous_score: int,
    current_score: int,
    previous_analysis: dict,
    current_analysis: dict,
) -> dict:
    """
    Compare two versions of an analyzed resume and highlight what improved,
    what regressed, and what still needs work. Used for iterative feedback.

    Args:
        previous_score: Overall ATS score from the first version.
        current_score: Overall ATS score from the revised version.
        previous_analysis: Full analysis dict from the first version.
        current_analysis: Full analysis dict from the revised version.

    Returns:
        dict with:
          - score_delta (int): positive = improved
          - improvements (list of str)
          - regressions (list of str)
          - remaining_issues (list of str)
          - verdict (str)
    """
    delta = current_score - previous_score
    improvements = []
    regressions = []
    remaining_issues = []

    # Compare dimension scores
    prev_kw = previous_analysis.get("keyword_analysis", {}).get("keyword_score", 0)
    curr_kw = current_analysis.get("keyword_analysis", {}).get("keyword_score", 0)
    prev_fmt = previous_analysis.get("formatting_analysis", {}).get("formatting_score", 0)
    curr_fmt = current_analysis.get("formatting_analysis", {}).get("formatting_score", 0)
    prev_str = previous_analysis.get("structure_analysis", {}).get("structure_score", 0)
    curr_str = current_analysis.get("structure_analysis", {}).get("structure_score", 0)

    if curr_kw > prev_kw:
        improvements.append(f"Keyword score improved by {curr_kw - prev_kw} points.")
    elif curr_kw < prev_kw:
        regressions.append(f"Keyword score dropped by {prev_kw - curr_kw} points — check for removed keywords.")

    if curr_fmt > prev_fmt:
        improvements.append(f"Formatting score improved by {curr_fmt - prev_fmt} points.")
    elif curr_fmt < prev_fmt:
        regressions.append(f"Formatting score dropped by {prev_fmt - curr_fmt} points.")

    if curr_str > prev_str:
        improvements.append(f"Structure score improved by {curr_str - prev_str} points (new sections added).")
    elif curr_str < prev_str:
        regressions.append(f"Structure score dropped by {prev_str - curr_str} points — check for missing sections.")

    # Remaining critical issues
    curr_fmt_issues = current_analysis.get("formatting_analysis", {}).get("issues_found", [])
    curr_str_missing = current_analysis.get("structure_analysis", {}).get("missing_sections", [])
    curr_jd_missing = current_analysis.get("keyword_analysis", {}).get("jd_keywords_missing", [])

    remaining_issues.extend(curr_fmt_issues)
    if curr_str_missing:
        remaining_issues.append(f"Still missing sections: {', '.join(curr_str_missing)}")
    if curr_jd_missing:
        remaining_issues.append(f"Still missing {len(curr_jd_missing)} JD keywords.")

    # Verdict
    if delta >= 15:
        verdict = f"Great progress! Your score jumped by {delta} points. Keep refining with the remaining suggestions."
    elif delta >= 5:
        verdict = f"Solid improvement — {delta} points gained. A few more targeted changes will push you into the next grade."
    elif delta == 0:
        verdict = "Score unchanged. Review the suggestions again — focus on CRITICAL items first."
    elif delta > -5:
        verdict = "Slight regression. Double-check that you haven't removed important keywords or sections."
    else:
        verdict = f"Score dropped by {abs(delta)} points. Review what was changed and compare against the original suggestions."

    return {
        "score_delta": delta,
        "previous_score": previous_score,
        "current_score": current_score,
        "improvements": improvements,
        "regressions": regressions,
        "remaining_issues": remaining_issues,
        "verdict": verdict,
    }
