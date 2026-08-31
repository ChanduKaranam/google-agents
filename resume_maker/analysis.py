"""Deterministic resume scoring — the numbers the agent quotes to the user.

The model is fluent enough to *say* "ATS score: 82/100", but a number it
invents changes every time you ask and can't be defended. Users act on these
figures (they'll add skills, rewrite bullets), so the score has to come from
code that looks at the actual resume and always returns the same answer for
the same input. This module is that code. It computes three things:

  * an ATS score from concrete, checkable signals (contact info present,
    sections named the way scanners expect, bullets quantified, length sane);
  * a keyword-gap analysis against a pasted job description;
  * a per-bullet impact rating (weak verb / no number → flagged).

The model still *presents* and *interprets* these — it decides which gaps
matter for the target role. It just doesn't get to make the numbers up.
"""

from __future__ import annotations

import re
from typing import Any

from .pdf_templates import normalize_resume

# Strong, resume-appropriate action verbs. Bullets that open with one of these
# read as ownership; "Responsible for" / "Worked on" read as description.
STRONG_VERBS = {
    "led", "built", "shipped", "launched", "drove", "reduced", "increased",
    "improved", "designed", "architected", "created", "developed", "delivered",
    "grew", "scaled", "optimized", "automated", "cut", "saved", "generated",
    "spearheaded", "founded", "owned", "managed", "mentored", "trained",
    "negotiated", "won", "achieved", "accelerated", "streamlined", "migrated",
    "implemented", "engineered", "established", "boosted", "eliminated",
    "resolved", "analyzed", "orchestrated", "pioneered", "transformed",
}
WEAK_OPENERS = {
    "responsible", "worked", "helped", "assisted", "involved", "participated",
    "handled", "tasked", "duties", "various", "supported", "contributed",
}

# Common stopwords stripped before keyword matching, plus JD boilerplate that
# would otherwise show up as "missing keywords" and mislead the user.
_STOP = {
    "the", "and", "for", "with", "you", "our", "are", "will", "have", "this",
    "that", "your", "from", "who", "all", "can", "not", "but", "any", "was",
    "has", "how", "what", "why", "job", "role", "work", "team", "years", "year",
    "experience", "ability", "strong", "good", "excellent", "including", "etc",
    "plus", "must", "should", "would", "able", "well", "using", "such", "into",
    "within", "across", "their", "them", "they", "were", "more", "than", "also",
    "candidate", "candidates", "responsibilities", "requirements", "preferred",
    "qualifications", "looking", "join", "help", "build", "working",
    "need", "needs", "skilled", "skills", "skill", "knowledge", "familiar",
    "proficient", "understanding", "some", "one", "may", "day", "role's",
}

_WORD = re.compile(r"[A-Za-z][A-Za-z0-9+#.\-]{1,}")


def _norm_token(tok: str) -> str:
    """Lowercase and strip edge punctuation, keeping internals like Node.js/C++."""
    return tok.lower().strip(".-")
_NUMERIC = re.compile(r"\d|%|\$|\bpercent\b", re.IGNORECASE)


def _all_bullets(d: dict) -> list[str]:
    bullets: list[str] = []
    for exp in d.get("experience", []):
        bullets.extend(exp.get("bullets", []))
    for proj in d.get("projects", []):
        bullets.extend(proj.get("bullets", []))
    return bullets


def _tokens(text: str) -> set[str]:
    return {t for m in _WORD.finditer(text or "") if (t := _norm_token(m.group(0)))}


def score_impact(bullets: list[str]) -> list[dict]:
    """Rate each bullet weak/moderate/strong on verb + quantification."""
    out = []
    for b in bullets:
        first = (b.strip().split() or [""])[0].lower().strip(",.:;")
        strong_verb = first in STRONG_VERBS
        weak_verb = first in WEAK_OPENERS
        quantified = bool(_NUMERIC.search(b))
        score = 0
        if strong_verb:
            score += 2
        elif not weak_verb:
            score += 1
        if quantified:
            score += 2
        rating = "strong" if score >= 3 else "moderate" if score == 2 else "weak"
        fixes = []
        if not strong_verb:
            fixes.append("open with a strong action verb (Led, Built, Reduced…)")
        if not quantified:
            fixes.append("add a number — %, count, time saved, revenue")
        out.append({"bullet": b, "rating": rating, "quantified": quantified, "suggestions": fixes})
    return out


def keyword_gap(resume_data: dict, job_description: str) -> dict:
    """Compare resume tokens against the most salient JD terms."""
    jd_tokens = [t for t in _tokens(job_description) if t not in _STOP and len(t) > 2]
    if not jd_tokens:
        return {"matched": [], "missing": [], "coverage_pct": None,
                "note": "No job description provided — skip keyword gap or ask the user to paste one."}
    # Frequency-rank JD terms; the top ones are what the scanner weights.
    freq: dict[str, int] = {}
    for t in jd_tokens:
        freq[t] = freq.get(t, 0) + 1
    ranked = sorted(freq, key=lambda t: (-freq[t], t))[:30]

    d = normalize_resume(resume_data)
    blob = " ".join([
        d["summary"], " ".join(d["skills"]),
        " ".join(_all_bullets(d)),
        " ".join(e.get("role", "") + " " + e.get("company", "") for e in d["experience"]),
    ])
    resume_tokens = _tokens(blob)
    matched = [t for t in ranked if t in resume_tokens]
    missing = [t for t in ranked if t not in resume_tokens]
    coverage = round(100 * len(matched) / len(ranked)) if ranked else None
    return {
        "matched": matched,
        "missing": missing,
        "coverage_pct": coverage,
        "note": "Missing terms are the highest-frequency JD keywords absent from the resume. "
                "Only add ones the user genuinely has — never fabricate to match.",
    }


def ats_score(resume_data: dict, job_description: str = "") -> dict:
    """Compute a 0–100 ATS score from checkable structural signals.

    The breakdown is returned alongside the number so the agent can explain
    *why*, and so the score is reproducible rather than a vibe.
    """
    d = normalize_resume(resume_data)
    breakdown: dict[str, Any] = {}
    score = 0

    # Contact reachability (20) — a scanner that can't find email/phone drops you.
    contact_pts = 0
    if d["email"]:
        contact_pts += 10
    if d["phone"]:
        contact_pts += 5
    if d["linkedin"] or d["github"] or d["website"]:
        contact_pts += 5
    breakdown["contact_info"] = {"points": contact_pts, "max": 20}
    score += contact_pts

    # Core sections present and parseable (20).
    section_pts = 0
    if d["experience"]:
        section_pts += 8
    if d["education"]:
        section_pts += 4
    if d["skills"]:
        section_pts += 5
    if d["summary"]:
        section_pts += 3
    breakdown["sections"] = {"points": section_pts, "max": 20}
    score += section_pts

    # Bullet quality — quantified impact + strong verbs (30).
    bullets = _all_bullets(d)
    if bullets:
        rated = score_impact(bullets)
        strong = sum(1 for r in rated if r["rating"] == "strong")
        quantified = sum(1 for r in rated if r["quantified"])
        verb_pts = round(15 * strong / len(bullets))
        quant_pts = round(15 * quantified / len(bullets))
        breakdown["bullet_impact"] = {
            "points": verb_pts + quant_pts, "max": 30,
            "total_bullets": len(bullets), "strong": strong, "quantified": quantified,
        }
        score += verb_pts + quant_pts
    else:
        breakdown["bullet_impact"] = {"points": 0, "max": 30, "total_bullets": 0}

    # Skills depth (10) — too few reads as thin to a keyword scanner.
    n_skills = len(d["skills"])
    skill_pts = 10 if n_skills >= 8 else 6 if n_skills >= 4 else 3 if n_skills else 0
    breakdown["skills_depth"] = {"points": skill_pts, "max": 10, "count": n_skills}
    score += skill_pts

    # Keyword match against JD (20 when a JD is given, else redistributed).
    if job_description.strip():
        gap = keyword_gap(resume_data, job_description)
        cov = gap.get("coverage_pct") or 0
        kw_pts = round(20 * cov / 100)
        breakdown["keyword_match"] = {"points": kw_pts, "max": 20, "coverage_pct": cov,
                                      "missing_sample": gap["missing"][:8]}
        score += kw_pts
    else:
        # No JD: scale the other 80 up to 100 so the score stays comparable.
        breakdown["keyword_match"] = {"points": None, "max": 0,
                                      "note": "No JD pasted; score is out of the other signals, rescaled to 100."}
        score = round(score * 100 / 80)

    score = max(0, min(100, score))
    band = ("strong" if score >= 80 else "decent" if score >= 65
            else "needs work" if score >= 45 else "weak")
    return {"ats_score": score, "band": band, "breakdown": breakdown}
