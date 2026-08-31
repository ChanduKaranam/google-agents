"""ADK function tools — the code the agent calls to produce real artifacts.

Design choices that matter here:

* **``resume_json`` is a JSON *string*, not a typed object.** ADK builds a
  Gemini function-call schema from each parameter's annotation. A deeply
  nested ``dict`` (experience → bullets, skills → groups) generates a schema
  the model fills unreliably, and ADK's automatic-function-calling doesn't
  round-trip arbitrary nested objects cleanly. A single ``str`` the model
  fills with JSON sidesteps all of that — the model is good at emitting JSON,
  and we parse it here where we can give a precise error back on malformed
  input instead of failing silently.

* **The PDF is delivered as an artifact, not a file path.** In Gemini
  Enterprise there is no shared filesystem with the user; ``save_artifact``
  is the only channel that produces something they can download. We render to
  bytes in memory and hand those bytes to ``tool_context.save_artifact``.
"""

from __future__ import annotations

import json
import re
from io import BytesIO
from typing import Any

from google.adk.tools.tool_context import ToolContext
from google.genai import types

from . import analysis
from .pdf_templates import GENERATORS, normalize_resume, render

TEMPLATE_ALIASES = {
    "classic": "classic", "traditional": "classic",
    "modern": "modern", "sidebar": "modern",
    "minimal": "minimal", "clean": "minimal",
    "creative": "creative", "bold": "creative",
    "ats": "ats", "ats-safe": "ats", "atssafe": "ats", "plain": "ats",
}


def _parse_resume_json(resume_json: str) -> tuple[dict | None, str]:
    """Parse the model-supplied JSON string, returning (data, error)."""
    if isinstance(resume_json, dict):  # tolerate a dict if ADK ever passes one
        return resume_json, ""
    if not resume_json or not resume_json.strip():
        return None, "resume_json is empty. Pass the resume as a JSON string."
    try:
        data = json.loads(resume_json)
    except json.JSONDecodeError as e:
        return None, f"resume_json is not valid JSON ({e}). Re-emit it as a single JSON object."
    if not isinstance(data, dict):
        return None, "resume_json must be a JSON object (with keys like name, experience…)."
    return data, ""


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", (text or "").strip()).strip("_") or "Resume"


async def generate_resume_pdf(
    resume_json: str,
    template: str,
    tool_context: ToolContext,
) -> dict:
    """Render the resume to a PDF and attach it for the user to download.

    Args:
      resume_json: The full resume as a JSON *string*. Recognised keys:
        name, role, email, phone, location, linkedin, github, website,
        summary, skills (a list, or an object grouping like
        {"Technical": [...], "Tools": [...], "Soft": [...]}),
        experience (list of {role, company, location, duration, bullets:[...]}),
        education (list of {degree, school, duration, details}),
        projects (list of {name, tech, link, bullets:[...]}),
        certifications (list of strings), achievements (list of strings).
        Only include what the user actually provided — never invent entries.
      template: One of "classic", "modern", "minimal", "creative", "ats".

    Returns:
      A dict with the saved artifact filename and version, or an "error" key
      the agent should read back to the user.
    """
    data, err = _parse_resume_json(resume_json)
    if err:
        return {"error": err}

    tpl = TEMPLATE_ALIASES.get((template or "").strip().lower(), "classic")

    d = normalize_resume(data)
    filename = f"{_slug(d['name'])}_Resume_{_slug(d['role']) if d['role'] else 'Profile'}.pdf"

    # Render to a temp path then read bytes — the generators write to a path,
    # and a scratch file keeps that contract without a filesystem dependency
    # on the caller.
    import os
    import tempfile

    tmp = os.path.join(tempfile.gettempdir(), filename)
    try:
        render(data, tpl, tmp)
        with open(tmp, "rb") as fh:
            pdf_bytes = fh.read()
    except Exception as e:  # noqa: BLE001 - surface render failures, don't crash the turn
        return {"error": f"Could not generate the PDF: {e}"}
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass

    part = types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf")
    try:
        version = await tool_context.save_artifact(filename=filename, artifact=part)
    except Exception as e:  # noqa: BLE001
        return {"error": f"Rendered the PDF but could not attach it for download: {e}"}

    return {
        "status": "generated",
        "filename": filename,
        "template": tpl,
        "version": version,
        "size_kb": round(len(pdf_bytes) / 1024, 1),
        "note": "The PDF is attached to this turn. Tell the user it's ready to download by name.",
    }


def analyze_resume(
    resume_json: str,
    target_role: str,
    job_description: str,
) -> dict:
    """Score the resume: ATS score, keyword gap vs a JD, and per-bullet impact.

    Use this before presenting the STAGE_3 analysis so the numbers are real and
    reproducible, not estimated. Interpret the output for the user — decide
    which missing keywords actually matter for their target role.

    Args:
      resume_json: The resume as a JSON string (same shape as
        generate_resume_pdf).
      target_role: The role the user is targeting, e.g. "Backend Engineer".
        Pass "" if not yet known.
      job_description: The pasted job description to compare against. Pass ""
        if the user hasn't given one — the ATS score adapts.

    Returns:
      A dict with ats_score/breakdown, keyword_gap, and impact ratings.
    """
    data, err = _parse_resume_json(resume_json)
    if err:
        return {"error": err}

    d = normalize_resume(data)
    bullets = []
    for exp in d["experience"]:
        bullets.extend(exp["bullets"])
    for proj in d["projects"]:
        bullets.extend(proj["bullets"])

    result: dict[str, Any] = {
        "ats": analysis.ats_score(data, job_description or ""),
        "impact": analysis.score_impact(bullets),
        "target_role": target_role,
    }
    if job_description.strip():
        result["keyword_gap"] = analysis.keyword_gap(data, job_description)
    return result


def export_json_resume(resume_json: str) -> dict:
    """Convert the resume to jsonresume.org schema for dev portfolios.

    Args:
      resume_json: The resume as a JSON string (same shape as
        generate_resume_pdf).

    Returns:
      A dict with the jsonresume-formatted document under "json_resume", ready
      to hand to the user as a code block.
    """
    data, err = _parse_resume_json(resume_json)
    if err:
        return {"error": err}
    d = normalize_resume(data)

    profiles = []
    if d["linkedin"]:
        profiles.append({"network": "LinkedIn", "url": d["linkedin"]})
    if d["github"]:
        profiles.append({"network": "GitHub", "url": d["github"]})

    jr = {
        "basics": {
            "name": d["name"],
            "label": d["role"],
            "email": d["email"],
            "phone": d["phone"],
            "url": d["website"],
            "summary": d["summary"],
            "location": {"city": d["location"]} if d["location"] else {},
            "profiles": profiles,
        },
        "work": [
            {
                "name": e["company"],
                "position": e["role"],
                "location": e["location"],
                "startDate": e["duration"],
                "highlights": e["bullets"],
            }
            for e in d["experience"]
        ],
        "education": [
            {
                "institution": e["school"],
                "studyType": e["degree"],
                "endDate": e["duration"],
                "score": e["details"],
            }
            for e in d["education"]
        ],
        "projects": [
            {"name": p["name"], "keywords": [p["tech"]] if p["tech"] else [],
             "url": p["link"], "highlights": p["bullets"]}
            for p in d["projects"]
        ],
        "skills": (
            [{"name": grp, "keywords": items} for grp, items in d["skill_groups"].items()]
            if d["skill_groups"]
            else [{"name": "Skills", "keywords": d["skills"]}]
        ),
        "certificates": [{"name": c} for c in d["certifications"]],
        "awards": [{"title": a} for a in d["achievements"]],
    }
    return {"json_resume": jr, "schema": "https://jsonresume.org/schema/"}
