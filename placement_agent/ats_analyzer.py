"""
ats_analyzer.py
Tools for analyzing a resume against ATS criteria:
  - Keyword extraction and matching
  - Formatting and structure checks
  - Readability scoring
  - Overall ATS score with breakdown
"""

import re
import math
from typing import Optional

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

# Power keywords that ATS systems heavily weight
_ATS_POWER_KEYWORDS = {
    "action_verbs": [
        "achieved", "improved", "led", "managed", "developed", "designed",
        "implemented", "built", "created", "delivered", "increased", "reduced",
        "optimized", "analyzed", "collaborated", "spearheaded", "launched",
        "coordinated", "trained", "mentored", "automated", "streamlined",
        "negotiated", "resolved", "generated", "maintained", "administered",
        "established", "evaluated", "facilitated", "produced",
    ],
    "soft_skills": [
        "communication", "leadership", "teamwork", "problem-solving",
        "analytical", "critical thinking", "adaptability", "creativity",
        "time management", "attention to detail", "collaboration",
        "interpersonal", "initiative", "decision-making", "strategic",
    ],
    "measurable_terms": [
        "%", "percent", "million", "billion", "revenue", "cost", "roi",
        "growth", "increase", "decrease", "reduction", "improvement",
        "performance", "kpi", "metric", "target", "goal",
    ],
}

# Standard sections ATS systems expect
_EXPECTED_SECTIONS = [
    "contact", "summary", "experience", "education", "skills",
]

# Formatting red flags (regex patterns to detect in raw text)
_FORMATTING_RED_FLAGS = {
    "tables_or_columns": r"\|.*\|",
    "headers_footers_markers": r"(page \d+|header|footer)",
    "special_chars_overuse": r"[★✓✗►▶•]{3,}",
    "images_placeholder": r"\[image\]|\[photo\]|\[logo\]",
    "excessive_caps": r"\b[A-Z]{5,}\b",
}

# Ideal resume length range (words)
_IDEAL_WORD_MIN = 300
_IDEAL_WORD_MAX = 700


def _tokenize(text: str) -> list[str]:
    """Lowercase word tokenizer ignoring punctuation."""
    return re.findall(r"\b[a-z][a-z\-']*[a-z]\b", text.lower())


def _count_bullets(text: str) -> int:
    """Count bullet-point lines."""
    return len(re.findall(r"^\s*[-•*►▶✓]\s+", text, re.MULTILINE))


def _has_quantified_achievements(text: str) -> bool:
    """Check whether the resume contains at least one quantified achievement."""
    patterns = [
        r"\d+\s*%",          # percentage
        r"\$\s*\d+",         # dollar amount
        r"\d+\+?\s*(users?|clients?|team|employees?|projects?|systems?)",
        r"(increased|reduced|improved|grew|saved|generated)\s.*\d+",
    ]
    for p in patterns:
        if re.search(p, text, re.IGNORECASE):
            return True
    return False


# ---------------------------------------------------------------------------
# Public ADK tool functions
# ---------------------------------------------------------------------------

def analyze_keywords(resume_text: str, job_description: str = "") -> dict:
    """
    Extract and evaluate keywords in the resume.

    Args:
        resume_text: Plain text of the resume.
        job_description: Optional job description to match against.

    Returns:
        dict with:
          - action_verbs_found (list)
          - action_verbs_missing (list)
          - soft_skills_found (list)
          - measurable_terms_found (list)
          - jd_keywords_matched (list): only when job_description is provided
          - jd_keywords_missing (list): only when job_description is provided
          - keyword_score (int): 0-100
    """
    tokens = set(_tokenize(resume_text))

    action_found = [w for w in _ATS_POWER_KEYWORDS["action_verbs"] if w in tokens]
    action_missing = [w for w in _ATS_POWER_KEYWORDS["action_verbs"] if w not in tokens]
    soft_found = [w for w in _ATS_POWER_KEYWORDS["soft_skills"]
                  if any(w in sentence for sentence in resume_text.lower().split("."))]
    measure_found = [t for t in _ATS_POWER_KEYWORDS["measurable_terms"]
                     if t in resume_text.lower()]

    # Score: 40 pts for action verbs (≥10 = full), 30 for measurables, 30 for soft skills
    action_score = min(40, int(40 * len(action_found) / 10))
    measure_score = min(30, int(30 * min(len(measure_found), 5) / 5))
    soft_score = min(30, int(30 * len(soft_found) / 5))
    keyword_score = action_score + measure_score + soft_score

    result = {
        "action_verbs_found": action_found,
        "action_verbs_missing": action_missing[:10],  # top 10 suggestions
        "soft_skills_found": soft_found,
        "measurable_terms_found": measure_found,
        "keyword_score": keyword_score,
        "jd_keywords_matched": [],
        "jd_keywords_missing": [],
    }

    if job_description.strip():
        jd_tokens = set(_tokenize(job_description))
        # Filter JD tokens to meaningful words (length > 3)
        jd_important = {w for w in jd_tokens if len(w) > 3}
        matched = list(jd_important & tokens)
        missing = list(jd_important - tokens)
        result["jd_keywords_matched"] = sorted(matched)[:30]
        result["jd_keywords_missing"] = sorted(missing)[:30]

    return result


def analyze_formatting(resume_text: str) -> dict:
    """
    Check the resume for ATS-unfriendly formatting issues.

    Args:
        resume_text: Plain text extracted from the resume.

    Returns:
        dict with:
          - issues_found (list of str): detected formatting problems
          - warnings (list of str): advisory notes
          - formatting_score (int): 0-100
          - bullet_count (int)
          - has_quantified_achievements (bool)
          - word_count (int)
          - length_status (str): "too_short" | "ideal" | "too_long"
    """
    issues = []
    warnings = []

    # Check for known red-flag patterns
    for flag_name, pattern in _FORMATTING_RED_FLAGS.items():
        if re.search(pattern, resume_text, re.IGNORECASE):
            issues.append(f"Detected potentially ATS-unfriendly element: {flag_name.replace('_', ' ')}")

    word_count = len(resume_text.split())
    if word_count < _IDEAL_WORD_MIN:
        issues.append(f"Resume is too short ({word_count} words). ATS systems may rank it lower.")
        length_status = "too_short"
    elif word_count > _IDEAL_WORD_MAX:
        warnings.append(
            f"Resume is longer than ideal ({word_count} words). "
            "Consider condensing to under 700 words for single-page ATS parsing."
        )
        length_status = "too_long"
    else:
        length_status = "ideal"

    # Contact info checks
    has_email = bool(re.search(r"[\w.\-]+@[\w.\-]+\.\w+", resume_text))
    has_phone = bool(re.search(r"(\+?\d[\d\s\-().]{7,}\d)", resume_text))
    has_linkedin = bool(re.search(r"linkedin\.com", resume_text, re.IGNORECASE))

    if not has_email:
        issues.append("No email address detected. ATS systems require contact info.")
    if not has_phone:
        warnings.append("No phone number detected. Add one for recruiter accessibility.")
    if not has_linkedin:
        warnings.append("No LinkedIn URL detected. Adding one improves credibility.")

    # Bullet points
    bullet_count = _count_bullets(resume_text)
    if bullet_count < 5:
        warnings.append(
            f"Only {bullet_count} bullet points found. "
            "ATS systems parse bullet points more reliably than dense paragraphs."
        )

    # Quantified achievements
    has_quant = _has_quantified_achievements(resume_text)
    if not has_quant:
        issues.append(
            "No quantified achievements detected. "
            "Add numbers, percentages, or dollar values to make impact measurable."
        )

    # Scoring: start at 100, deduct per issue/warning
    score = 100 - (len(issues) * 15) - (len(warnings) * 7)
    score = max(0, min(100, score))

    return {
        "issues_found": issues,
        "warnings": warnings,
        "formatting_score": score,
        "bullet_count": bullet_count,
        "has_quantified_achievements": has_quant,
        "word_count": word_count,
        "length_status": length_status,
        "has_email": has_email,
        "has_phone": has_phone,
        "has_linkedin": has_linkedin,
    }


def analyze_structure(sections: dict) -> dict:
    """
    Evaluate whether the resume contains all ATS-expected sections.

    Args:
        sections: A dict of {section_name: section_text} as returned by
                  get_resume_sections() in resume_parser.py.

    Returns:
        dict with:
          - present_sections (list)
          - missing_sections (list)
          - structure_score (int): 0-100
          - notes (list of str)
    """
    present = [s for s in _EXPECTED_SECTIONS if s in sections]
    missing = [s for s in _EXPECTED_SECTIONS if s not in sections]
    notes = []

    # Fresher rule: a student with no work history but a real Projects section
    # is not structurally broken — projects ARE their experience. Count it and
    # coach the framing instead of flagging a CRITICAL gap they cannot fill.
    experience_via_projects = "experience" in missing and "projects" in sections
    if experience_via_projects:
        missing.remove("experience")
        present.append("experience")
        notes.append(
            "No formal Experience section, but Projects found — for a student "
            "resume that's fine. Frame each project like a job: what you built, "
            "the tech used, and a measurable outcome (users, marks, speed)."
        )

    # Check content quality for present sections
    if "experience" in sections:
        exp_text = sections["experience"]
        if len(exp_text.split()) < 50:
            notes.append("Experience section seems very brief. Expand with detailed bullet points.")
        if not _has_quantified_achievements(exp_text):
            notes.append("Experience section lacks quantified results. Add metrics to each role.")

    if "skills" in sections:
        skills_text = sections["skills"]
        skill_count = len(re.findall(r"[,\n|]", skills_text)) + 1
        if skill_count < 5:
            notes.append("Skills section lists fewer than 5 skills. ATS matching improves with more.")

    if "summary" not in sections:
        notes.append(
            "No Summary/Objective section found. A 2-3 line professional summary "
            "significantly boosts ATS keyword density."
        )

    structure_score = int(100 * len(present) / len(_EXPECTED_SECTIONS))

    return {
        "present_sections": present,
        "missing_sections": missing,
        "structure_score": structure_score,
        "notes": notes,
    }


def calculate_ats_score(
    keyword_score: int,
    formatting_score: int,
    structure_score: int,
    job_description: str = "",
    jd_match_count: int = 0,
    jd_total_keywords: int = 0,
) -> dict:
    """
    Aggregate individual dimension scores into a single ATS score with breakdown.

    Args:
        keyword_score: Score from analyze_keywords() (0-100).
        formatting_score: Score from analyze_formatting() (0-100).
        structure_score: Score from analyze_structure() (0-100).
        job_description: Original JD text (used to compute JD match bonus).
        jd_match_count: Number of JD keywords found in the resume.
        jd_total_keywords: Total important JD keywords identified.

    Returns:
        dict with:
          - overall_score (int): weighted ATS score 0-100
          - grade (str): A/B/C/D/F
          - breakdown (dict): per-dimension scores and weights
          - summary (str): one-line verdict
    """
    # Weights. Without a JD there is nothing to match against, so the JD slice
    # is redistributed proportionally across the other three dimensions —
    # otherwise every student who has no JD handy is silently capped at 90.
    jd_scored = bool(job_description.strip()) and jd_total_keywords > 0
    if jd_scored:
        weights = {
            "keywords": 0.35,
            "formatting": 0.30,
            "structure": 0.25,
            "jd_match": 0.10,
        }
        jd_match_score = int(100 * jd_match_count / jd_total_keywords)
    else:
        weights = {
            "keywords": 0.35 / 0.90,
            "formatting": 0.30 / 0.90,
            "structure": 0.25 / 0.90,
            "jd_match": 0.0,
        }
        jd_match_score = 0

    overall = round(
        keyword_score * weights["keywords"]
        + formatting_score * weights["formatting"]
        + structure_score * weights["structure"]
        + jd_match_score * weights["jd_match"]
    )

    if overall >= 80:
        grade = "A"
        summary = "Excellent — your resume is well-optimized for ATS systems."
    elif overall >= 65:
        grade = "B"
        summary = "Good — a few targeted improvements will make a significant difference."
    elif overall >= 50:
        grade = "C"
        summary = "Fair — several important gaps need to be addressed before applying."
    elif overall >= 35:
        grade = "D"
        summary = "Needs work — this resume is likely to be filtered out by most ATS systems."
    else:
        grade = "F"
        summary = "Critical — major restructuring required to pass ATS screening."

    return {
        "overall_score": overall,
        "grade": grade,
        "summary": summary,
        "breakdown": {
            "keyword_score": {"score": keyword_score, "weight": f"{weights['keywords']:.0%}", "max": 100},
            "formatting_score": {"score": formatting_score, "weight": f"{weights['formatting']:.0%}", "max": 100},
            "structure_score": {"score": structure_score, "weight": f"{weights['structure']:.0%}", "max": 100},
            "jd_match_score": {
                "score": jd_match_score,
                "weight": "10%" if jd_scored else "0%",
                "max": 100,
                "scored": jd_scored,
                "note": "" if jd_scored else (
                    "Not scored — no job description was provided. Share the JD "
                    "of a role you're targeting for a more precise, tailored score."
                ),
            },
        },
    }


def full_ats_analysis(resume_text: str, job_description: str = "") -> dict:
    """
    Run a complete ATS analysis pipeline on the given resume text.
    This is the primary entry point — it calls all sub-analyzers and
    returns a unified result.

    Args:
        resume_text: Plain text of the resume (from parse_resume).
        job_description: Optional job description to tailor the analysis.

    Returns:
        Comprehensive analysis dict containing:
          - ats_score (dict): overall score and breakdown
          - keyword_analysis (dict)
          - formatting_analysis (dict)
          - structure_analysis (dict)
    """
    try:
        from .resume_parser import get_resume_sections
    except ImportError:
        from resume_parser import get_resume_sections

    # Run all analyzers
    keyword_result = analyze_keywords(resume_text, job_description)
    formatting_result = analyze_formatting(resume_text)
    section_result = get_resume_sections(resume_text)
    structure_result = analyze_structure(section_result.get("sections", {}))

    jd_match_count = len(keyword_result.get("jd_keywords_matched", []))
    jd_total = jd_match_count + len(keyword_result.get("jd_keywords_missing", []))

    score_result = calculate_ats_score(
        keyword_score=keyword_result["keyword_score"],
        formatting_score=formatting_result["formatting_score"],
        structure_score=structure_result["structure_score"],
        job_description=job_description,
        jd_match_count=jd_match_count,
        jd_total_keywords=jd_total,
    )

    return {
        "ats_score": score_result,
        "keyword_analysis": keyword_result,
        "formatting_analysis": formatting_result,
        "structure_analysis": structure_result,
    }
