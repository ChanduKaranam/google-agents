"""Resume Intelligence Agent — reads a resume, proposes, writes nothing.

Same contract as the profile extractor, richer input: a full resume text.
Its output is one `ProfileUpdate` with the three channels kept strictly
apart — facts the resume *states* go in `profile`, admission-relevant
signals the resume merely *suggests* go in `inferred_domains` with a
confidence and the evidence, and anything unclear goes in `ambiguities`.

The resume must reduce questions (V2 brief §4): whatever lands here is
merged with source="resume" and never asked again.
"""

from __future__ import annotations

from google.adk.agents import LlmAgent
from google.adk.models import Gemini
from google.genai import types
from pydantic import BaseModel, ConfigDict, Field

from app.config.settings import MODEL
from app.models.student import ProfileUpdate

AGENT_NAME = "resume_agent"


class ResumeText(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(
        description="The resume content as plain text, faithful "
        "to the document — not summarized."
    )


INSTRUCTION = """\
You analyze one student resume for MS-admissions signals and return a
ProfileUpdate. You extract; you never invent, pad, or improve.

## Into `profile` — only what the resume STATES

- education: degree, major, institution, graduation_year, cgpa,
  grading_scale (only if the resume shows the scale, e.g. "8.2/10"),
  backlogs (ONLY if the resume states a number — "no backlogs" is 0;
  nothing said means omit the field, never 0).
- test_scores: IELTS/TOEFL/GRE only if scores are printed.
- technical.skills: languages, frameworks, tools, as listed.
- technical.certifications: as listed.
- experience.internships: one short entry per internship, as written
  (role + company when given).
- experience.work_experience_months: ONLY if durations are explicit —
  never estimate from dates you'd have to assume.
- research.publications: a count only if publications are listed.
- research.research_interests: only interests the resume states as
  interests — a project is not a stated interest.
- projects.projects: one short entry per project, title plus one line.

## Into `inferred_domains` — what the evidence SUGGESTS

Domains the projects/skills point to (AI/ML, NLP, Computer Vision, Data
Science, Systems, Security, Web…), each with:
- confidence 0-1 (three ML projects + PyTorch ≈ 0.85; one course ≈ 0.4)
- basis: the actual evidence items, e.g. ["Crop recommendation ML project",
  "PyTorch", "TensorFlow"].

An inference NEVER goes into profile fields. The student confirms it in
conversation, or it stays a suggestion.

## Into `ambiguities`

Anything that needs the student: an unclear scale, two degrees, a gap you
cannot read. Short questions, not guesses.

Rules: numbers must appear in the resume; nothing about anyone other than
the student; an empty section is correct when the resume has nothing for
it; never grade or judge the resume.
"""


def create_resume_agent() -> LlmAgent:
    """Factory — ADK forbids attaching one agent instance to two parents."""
    return LlmAgent(
        name=AGENT_NAME,
        model=Gemini(model=MODEL, retry_options=types.HttpRetryOptions(attempts=3)),
        description=(
            "Analyzes a resume's plain text for MS-admissions signals: "
            "education, scores, skills, projects, internships, research — "
            "plus domain inferences with confidence and evidence. Proposes a "
            "ProfileUpdate; stores nothing itself."
        ),
        instruction=INSTRUCTION,
        mode="task",
        input_schema=ResumeText,
        output_schema=ProfileUpdate,
        generate_content_config=types.GenerateContentConfig(temperature=0.0),
    )
