"""Terminal client for the simulator.

    python -m clinical_simulator.console            # interactive encounter
    python -m clinical_simulator.console --smoke    # scripted end-to-end check

Useful for trying a case without the ADK web UI, and for a smoke test that
exercises the real model, the real tools and the real scorer in one pass.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from . import session as S
from .agent import root_agent

APP = "clinical_simulator"
USER = "student"

SMOKE_SCRIPT = [
    "List the beginner cases.",
    "Start case IM-001.",
    "What brings you in today?",
    "How long have you had the fever, and did it start suddenly?",
    "Are you coughing anything up? What colour is it?",
    "Does your chest hurt when you take a deep breath?",
    "Has anyone at home had a cough for a long time?",
    "Do you smoke?",
    "Please check the vital signs.",
    "Auscultate the chest and percuss it.",
    "Order a chest x-ray, a complete blood count and sputum for AFB.",
    "My differential is: community-acquired pneumonia, because of the rigor, "
    "rusty sputum and lobar consolidation; pulmonary tuberculosis, because it "
    "is endemic and must be excluded; and pulmonary embolism, because of the "
    "pleuritic pain and low saturation.",
    "To separate them I would use the sputum AFB and GeneXpert against the "
    "chest x-ray pattern and the neutrophil count, and I would use the acute "
    "onset with a rigor to argue against tuberculosis.",
    "My final diagnosis is community-acquired pneumonia of the right lower "
    "lobe, most likely pneumococcal. The rigor at onset, rusty sputum, "
    "pleuritic pain, dullness with bronchial breathing, neutrophilia and the "
    "air bronchogram on the chest x-ray all fit, and the negative GeneXpert "
    "argues against tuberculosis. The saturation of 92% means he needs "
    "admission.",
    "Please evaluate my performance now.",
]


async def _turn(runner: Runner, session_id: str, text: str) -> str:
    content = types.Content(role="user", parts=[types.Part(text=text)])
    out: list[str] = []
    async for event in runner.run_async(
        user_id=USER, session_id=session_id, new_message=content
    ):
        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.text:
                    out.append(part.text)
                if getattr(part, "function_call", None):
                    fc = part.function_call
                    print(f"    · {fc.name}({json.dumps(dict(fc.args or {}))[:120]})", file=sys.stderr)
    return "".join(out).strip()


async def _run(script: list[str] | None) -> int:
    service = InMemorySessionService()
    session = await service.create_session(app_name=APP, user_id=USER)
    runner = Runner(app_name=APP, agent=root_agent, session_service=service)

    turns = iter(script) if script else None
    while True:
        if turns is not None:
            try:
                text = next(turns)
            except StopIteration:
                break
            print(f"\n\033[1mstudent>\033[0m {text}")
        else:
            try:
                text = input("\n\033[1mstudent>\033[0m ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not text:
                continue
            if text.lower() in {"quit", "exit"}:
                break

        reply = await _turn(runner, session.id, text)
        print(f"\n{reply}")

    final = await service.get_session(app_name=APP, user_id=USER, session_id=session.id)
    enc = (final.state or {}).get(S.KEY) or {}
    card = enc.get("scorecard")
    print("\n" + "─" * 70)
    print(
        f"case={enc.get('case_id')} phase={enc.get('phase')} "
        f"questions={len(enc.get('questions_asked', []))} "
        f"exams={len(enc.get('exams_requested', []))} "
        f"investigations={len(enc.get('investigations_ordered', []))} "
        f"hints={enc.get('hints_used', 0)}"
    )
    if card:
        print(f"overall={card['overall_score']}/100 ({card['band']})  {card['skills']}")
        return 0
    if script:
        print("No scorecard was produced — the evaluator did not run.")
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Clinical Case Simulator console")
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Replay a scripted encounter end to end and assert a report is produced.",
    )
    args = parser.parse_args()
    return asyncio.run(_run(SMOKE_SCRIPT if args.smoke else None))


if __name__ == "__main__":
    sys.exit(main())
