"""Clinical Case Simulator — root agent.

MVP shape from the research doc, section 12:
    1 ADK agent + structured case data + evaluation logic.

The root agent knows nothing about any case. It cannot leak a diagnosis it was
never given; every fact it can state came back from a tool that read the
approved case file.
"""

from __future__ import annotations

from google.adk.agents import LlmAgent
from google.genai import types

from .agents import ask_patient, clinical_evaluator
from .config import MODEL
from .prompts import SIMULATOR_INSTRUCTION
from .tools import (
    case_status,
    give_hint,
    list_available_cases,
    order_investigation,
    perform_examination,
    record_metacognition,
    reveal_answer,
    start_case,
    submit_differential,
    submit_discriminating_plan,
    submit_final_diagnosis,
)

root_agent = LlmAgent(
    name="clinical_case_simulator",
    model=MODEL,
    description=(
        "An AI virtual patient for MBBS students: take a history, examine, "
        "investigate, build a differential, commit to a diagnosis, and get "
        "scored on your clinical reasoning process."
    ),
    instruction=SIMULATOR_INSTRUCTION,
    tools=[
        list_available_cases,
        start_case,
        case_status,
        ask_patient,
        perform_examination,
        order_investigation,
        submit_differential,
        submit_discriminating_plan,
        submit_final_diagnosis,
        record_metacognition,
        give_hint,
        reveal_answer,
        clinical_evaluator,
    ],
    generate_content_config=types.GenerateContentConfig(temperature=0.3),
)
