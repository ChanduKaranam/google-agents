"""Exam reference — structure, never requirements.

Static metadata is legitimate here (§23 of the Phase 2 brief): what an
exam *is* — its provider, sections, scale, validity — changes rarely and
belongs in configuration. What a program *requires* changes constantly and
may only come from researched, evidence-graded facts. This module
therefore knows how IELTS is scored and cannot know who requires it.

Adding an exam = adding an entry; nothing in the agent core changes.
"""

from __future__ import annotations

from typing import Any

EXAMS: dict[str, dict[str, Any]] = {
    "ielts": {
        "name": "IELTS Academic",
        "category": "english",
        "provider": "IELTS Partners (British Council / IDP / Cambridge)",
        "official_domain": "ielts.org",
        "sections": ["Listening", "Reading", "Writing", "Speaking"],
        "score_scale": "bands 0-9 in 0.5 steps, overall + per section",
        "validity_years": 2,
    },
    "toefl": {
        "name": "TOEFL iBT",
        "category": "english",
        "provider": "ETS",
        "official_domain": "ets.org",
        "sections": ["Reading", "Listening", "Speaking", "Writing"],
        "score_scale": "0-120 total, 0-30 per section",
        "validity_years": 2,
    },
    "pte": {
        "name": "PTE Academic",
        "category": "english",
        "provider": "Pearson",
        "official_domain": "pearsonpte.com",
        "sections": ["Speaking & Writing", "Reading", "Listening"],
        "score_scale": "10-90",
        "validity_years": 2,
    },
    "duolingo": {
        "name": "Duolingo English Test",
        "category": "english",
        "provider": "Duolingo",
        "official_domain": "englishtest.duolingo.com",
        "sections": ["Adaptive test", "Video interview & writing sample"],
        "score_scale": "10-160",
        "validity_years": 2,
    },
    "gre": {
        "name": "GRE General Test",
        "category": "graduate_admissions",
        "provider": "ETS",
        "official_domain": "ets.org",
        "sections": [
            "Verbal Reasoning",
            "Quantitative Reasoning",
            "Analytical Writing",
        ],
        "score_scale": "130-170 per section (Verbal/Quant), 0-6 AWA",
        "validity_years": 5,
    },
    "gmat": {
        "name": "GMAT",
        "category": "graduate_admissions",
        "provider": "GMAC",
        "official_domain": "mba.com",
        "sections": ["Quantitative", "Verbal", "Data Insights"],
        "score_scale": "205-805 total (GMAT Focus scale)",
        "validity_years": 5,
    },
}


def exam_info(exam_id: str) -> dict[str, Any]:
    """Metadata for one exam. Raises KeyError for unknown exams — an exam
    this module does not know is a gap to state, never a guess."""
    return dict(EXAMS[exam_id])
