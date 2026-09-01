"""Sub-agents exposed to the simulator as tools.

Both are wrapped in `AgentTool` subclasses that write to session state before
delegating. That is what gives the patient conversational memory (AgentTool
otherwise runs each call in a fresh child session) and what guarantees the
evaluator can only narrate a scorecard Python already computed.
"""

from __future__ import annotations

import json
from typing import Any

from google.adk.agents import LlmAgent
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.tools import ToolContext
from google.adk.tools.agent_tool import AgentTool
from google.genai import types

from . import session as S
from .cases import get_case
from .config import EVAL_MODEL, MODEL
from .evaluation import score_encounter
from .prompts import EVALUATOR_INSTRUCTION, patient_instruction

# ---------------------------------------------------------------------------
# Virtual patient
# ---------------------------------------------------------------------------

patient_agent = LlmAgent(
    name="ask_patient",
    model=MODEL,
    description=(
        "Ask the virtual patient a question and get their reply, in their own "
        "words. Pass the student's question through as close to verbatim as "
        "possible. This is the ONLY way to obtain history."
    ),
    instruction=patient_instruction,
    # Each call is a fresh child session; continuity comes from the transcript
    # injected into the instruction, so the default history is just noise.
    include_contents="none",
    generate_content_config=types.GenerateContentConfig(temperature=0.8),
)


class PatientTool(AgentTool):
    """AgentTool that logs the exchange so the patient stays consistent."""

    async def run_async(self, *, args: dict[str, Any], tool_context: ToolContext):
        question = args.get("request", "")
        enc = S.get(tool_context.state)
        if not enc.get("case_id"):
            return {
                "status": "no_active_case",
                "message": "Start a case before speaking to the patient.",
            }

        turn = S.bump_turn(enc)
        enc["questions_asked"].append({"turn": turn, "text": question})
        S.put(tool_context.state, enc)

        reply = await super().run_async(args=args, tool_context=tool_context)

        text = reply if isinstance(reply, str) else json.dumps(reply, ensure_ascii=False)
        # Re-read: the child run may have pushed its own state delta back.
        enc = S.get(tool_context.state)
        enc["patient_replies"].append({"turn": turn, "text": text})
        S.put(tool_context.state, enc)
        return text


ask_patient = PatientTool(agent=patient_agent)


# ---------------------------------------------------------------------------
# Evaluator
# ---------------------------------------------------------------------------


def _transcript(enc: dict) -> str:
    lines: list[str] = []
    replies = {r["turn"]: r["text"] for r in enc.get("patient_replies", [])}
    for q in enc.get("questions_asked", []):
        lines.append(f'[history] Student asked: "{q["text"]}"')
        if q["turn"] in replies:
            lines.append(f'           Patient replied: "{replies[q["turn"]]}"')
    for e in enc.get("exams_requested", []):
        state = "performed" if e.get("matched") else "not available in this case"
        lines.append(f'[exam] Student requested: "{e["query"]}" ({state})')
    for i in enc.get("investigations_ordered", []):
        state = "resulted" if i.get("matched") else "not available in this case"
        lines.append(f'[investigation] Student ordered: "{i["query"]}" ({state})')
    for d in enc.get("differential_submitted", []):
        lines.append(f'[differential] "{d["dx"]}" — reason given: "{d.get("rationale") or "(none)"}"')
    if enc.get("distinguishing_plan"):
        lines.append(f'[plan] "{enc["distinguishing_plan"]}"')
    if enc.get("final_diagnosis"):
        lines.append(f'[final] "{enc["final_diagnosis"]}" because "{enc.get("final_reasoning", "")}"')
    for m in enc.get("metacognition", []):
        lines.append(
            f'[metacognition] On "{m["question"]}" the student said: "{m["student_reason"]}"'
        )
    return "\n".join(lines) or "(the student did nothing)"


def evaluator_instruction(ctx: ReadonlyContext) -> str:
    enc = ctx.state.get(S.KEY) or {}
    scorecard = enc.get("scorecard")
    if not scorecard:
        return (
            EVALUATOR_INSTRUCTION
            + "\n\nNo scorecard is available. Reply exactly: [no encounter to evaluate]"
        )
    return f"""{EVALUATOR_INSTRUCTION}

=== SCORECARD (authoritative — reproduce these numbers exactly) ===
{json.dumps(scorecard, indent=2, ensure_ascii=False)}

=== TRANSCRIPT (the only evidence you may cite) ===
{_transcript(enc)}
"""


evaluator_agent = LlmAgent(
    name="clinical_evaluator",
    model=EVAL_MODEL,
    description=(
        "Ends the encounter and produces the student's Clinical Performance "
        "Report. Call this once the final diagnosis has been submitted, or when "
        "the student ends the case early."
    ),
    instruction=evaluator_instruction,
    include_contents="none",
    generate_content_config=types.GenerateContentConfig(temperature=0.2),
)


class EvaluatorTool(AgentTool):
    """Scores the encounter in Python, then has the model narrate the result."""

    async def run_async(self, *, args: dict[str, Any], tool_context: ToolContext):
        enc = S.get(tool_context.state)
        case = get_case(enc.get("case_id") or "")
        if case is None:
            return {
                "status": "no_active_case",
                "message": "There is no encounter to evaluate.",
            }

        enc["scorecard"] = score_encounter(case, enc)
        S.advance(enc, "evaluated")
        S.put(tool_context.state, enc)

        args = dict(args)
        args["request"] = "Write the Clinical Performance Report now."
        return await super().run_async(args=args, tool_context=tool_context)


clinical_evaluator = EvaluatorTool(agent=evaluator_agent)
