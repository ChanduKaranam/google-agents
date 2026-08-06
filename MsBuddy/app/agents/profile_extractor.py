# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""`profile_extractor_agent` — free text to structured profile fields.

Spec §4.1 classifies this as the one part of C1 that genuinely needs a model:
storage, validation, conversion and completeness are all deterministic, but
turning "I did my BTech in ECE, 8.1 CGPA, targeting Fall 2027 in Canada" into
typed fields is not.

Runs in `mode="task"` so the root delegates with a typed request and receives
a typed result. It writes nothing: its output is a *proposal* that the root
passes to `save_profile_fields`, where the evidence check decides what is
actually stored.
"""

from __future__ import annotations

from google.adk.agents import Agent
from google.adk.models import Gemini
from google.genai import types

from app.config import MODEL
from app.reference.gpa_scales import SCALE_KEYS
from app.reference.profile_fields import FIELDS
from app.schemas import ExtractionInput, ExtractionOutput


def _field_catalogue() -> str:
    """Render the registry as instruction text, so it can never drift."""
    lines: list[str] = []
    for name, spec in FIELDS.items():
        detail = f"- {name} ({spec.kind}"
        if spec.choices:
            detail += f"; one of: {', '.join(spec.choices)}"
        elif spec.minimum is not None and spec.maximum is not None:
            detail += f"; range {spec.minimum}-{spec.maximum}"
        detail += ")"
        lines.append(detail)
    return "\n".join(lines)


INSTRUCTION = f"""\
You extract MS-application profile facts from a student's own words.

Return ONLY fields the student explicitly stated. You are not helping by
guessing: a wrong GPA or a wrong intake year does real damage to a real
application. If the student did not say it, it is not there.

For every field you return, `evidence_span` MUST be an exact substring copied
from the student's text — character for character, not paraphrased and not
reconstructed. A field whose evidence cannot be found in their text will be
discarded downstream, so inventing one wastes the extraction.

Fields you may extract:
{_field_catalogue()}

Rules:
- A GPA needs BOTH `gpa_value` and `gpa_scale`. If the student gives a number
  without saying which scale it is on, do NOT guess the scale — put the
  question in `ambiguous` instead. A percentage is `pct_100`; "8.1 CGPA" in
  the Indian system is `cgpa_10`. Valid scales: {", ".join(SCALE_KEYS)}.
- `target_intake_year` must be a full four-digit year. If the student wrote
  "Fall 25", that is ambiguous — ask which year via `ambiguous`, do not
  assume.
- Convert units only when the student's own words make it unambiguous:
  "3 years of work" becomes work_experience_months = 36, with the evidence
  span quoting "3 years of work".
- GRE sections are separate fields. If the student gives only a total, do not
  split it — put it in `ambiguous`.
- `target_countries` is a comma-separated list.
- Never infer citizenship, nationality, or gender from a name, an institution,
  or anything else. Record `citizenship` only if the student states it.
- Extract nothing at all rather than something uncertain. An empty result is
  a correct result.

Put anything the student mentioned but that you could not resolve into
`ambiguous`, phrased as the question to ask them.

When you are done, call `finish_task` with your result.
"""


def create_profile_extractor_agent() -> Agent:
    """Build the profile extractor.

    A factory rather than a module-level instance: ADK raises "agent already
    has a parent" if one instance is attached to two parents, and tests build
    the tree more than once per process.
    """
    return Agent(
        name="profile_extractor_agent",
        model=Gemini(
            model=MODEL,
            retry_options=types.HttpRetryOptions(attempts=3),
        ),
        description=(
            "Extracts explicitly-stated MS-application profile fields from a "
            "student's own words, with a verbatim evidence quote for each. "
            "Does not store anything and does not guess."
        ),
        instruction=INSTRUCTION,
        mode="task",
        input_schema=ExtractionInput,
        output_schema=ExtractionOutput,
        generate_content_config=types.GenerateContentConfig(
            # Extraction should be as reproducible as the model allows; this
            # is transcription, not composition.
            temperature=0.0,
        ),
    )
