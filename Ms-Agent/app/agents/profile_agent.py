"""Profile Agent — extracts what the student *said*, proposes, writes nothing.

A task-mode agent with a structured output contract (`ProfileUpdate`). It
holds no tools and cannot touch state: the orchestrator passes its proposal
to `update_profile`, where deterministic code validates and merges. The
split is the anti-invention design — an extractor that could write would
make every extraction error permanent.
"""

from __future__ import annotations

from google.adk.agents import LlmAgent
from google.adk.models import Gemini
from google.genai import types
from pydantic import BaseModel, ConfigDict, Field

from app.config.settings import MODEL
from app.models.student import ProfileUpdate, StudentProfile

AGENT_NAME = "profile_agent"


class ExtractionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(description="The student's message, verbatim.")


def _schema_outline() -> str:
    """Render the section/field names from the model, so the prompt cannot
    drift from what `update_profile` will actually accept."""
    lines = []
    for section_name, field_info in StudentProfile.model_fields.items():
        section_model = field_info.default_factory  # type: ignore[union-attr]
        names = ", ".join(section_model.model_fields)  # type: ignore[union-attr]
        lines.append(f"- {section_name}: {names}")
    return "\n".join(lines)


INSTRUCTION = f"""\
You extract structured student-profile information from one message.

Extract ONLY what the student explicitly stated. You never infer, never
guess, and never fill a field the message does not support. An empty update
is a correct answer for a message with no profile facts in it.

Sections and fields you may fill:
{_schema_outline()}

Rules:
- "8.2 CGPA" alone gives education.cgpa = 8.2 — it does NOT give
  grading_scale unless the student said "out of 10" or similar.
- "MS in Canada" gives target.degree = "MS" and target.country = "Canada".
- Names of institutions and majors are recorded exactly as written; expand
  nothing ("CSE" stays "CSE" unless the student expanded it themselves).
- Numbers must be numbers the student stated. Never compute or convert.
- Anything you are unsure how to place goes in `ambiguities` as a short
  question for the student — not into a field.
- Never extract information about anyone other than the student.

Return the ProfileUpdate structure. Fields the message did not mention are
simply omitted.
"""


def create_profile_agent() -> LlmAgent:
    """Factory — ADK forbids attaching one agent instance to two parents."""
    return LlmAgent(
        name=AGENT_NAME,
        model=Gemini(model=MODEL, retry_options=types.HttpRetryOptions(attempts=3)),
        description=(
            "Extracts structured profile facts (education, scores, targets, "
            "preferences) from a student's message. Proposes a ProfileUpdate; "
            "stores nothing itself."
        ),
        instruction=INSTRUCTION,
        mode="task",
        input_schema=ExtractionRequest,
        output_schema=ProfileUpdate,
        generate_content_config=types.GenerateContentConfig(temperature=0.0),
    )
