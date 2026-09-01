"""Three scripted students, played against the simulator to check the marking.

    python -m clinical_simulator.mock_students                 # all three, IM-002
    python -m clinical_simulator.mock_students --student strong
    python -m clinical_simulator.mock_students --case IM-001
    python -m clinical_simulator.mock_students --remote        # the deployed agent

The point is not that the model answers nicely — it is that a rubric-driven
scorer separates three genuinely different performances by a wide, defensible
margin. If a weak student and a strong student land within a few marks of each
other, the marking scheme is broken, and this is how you find out.

All three run the SAME case so the scores are comparable.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from typing import Any

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from . import session as S
from .agent import root_agent

APP = "clinical_simulator"
DEFAULT_CASE = "IM-002"


# ---------------------------------------------------------------------------
# 1. The strong student — systematic, curious, safety-conscious
# ---------------------------------------------------------------------------
STRONG = [
    "Start case IM-002.",
    "Good morning, I'm a medical student. I'm sorry you're feeling unwell. Can you tell me what's brought you in today?",
    "Thank you. Can you show me where exactly the discomfort is?",
    "What does it feel like — is it sharp, or more of a pressure?",
    "Does it move or spread anywhere else at all?",
    "When did it start, and how long has this episode lasted?",
    "Is there anything that brings it on, like walking or climbing stairs?",
    "And does anything make it settle?",
    "Did you notice anything else with it — any sweating, feeling sick, or being short of breath?",
    "Have you had episodes like this before over the last few weeks?",
    "Do you have any medical conditions — blood pressure, diabetes, or high cholesterol?",
    "What medication are you taking at the moment, and do you take it regularly?",
    "Do you smoke, and if so how much and for how long?",
    "Has anyone in your family had heart problems at a young age?",
    "Have you had any long journeys, leg swelling or calf pain recently?",
    "Any indigestion or heartburn, and is this pain related to meals?",
    "Please check the vital signs, including blood pressure in both arms.",
    "I'd like to do a cardiovascular examination and check the JVP.",
    "Please examine the respiratory system and the legs for oedema or calf tenderness.",
    "Can you palpate the chest wall to see if the pain is reproducible?",
    "Please do a 12-lead ECG.",
    "I'd like a troponin now and a repeat at three hours, plus a chest X-ray.",
    "Also renal function and electrolytes, blood glucose with HbA1c, and a lipid profile.",
    "My differential is: first, acute coronary syndrome, because of exertional retrosternal heaviness radiating to the left arm and jaw, relieved by rest, with diaphoresis, in a smoker with a strong family history and ST depression on the ECG. Second, aortic dissection, which I must exclude before giving any anticoagulation. Third, pulmonary embolism, given the breathlessness, though the Wells score is low. I'd also consider gastro-oesophageal reflux and pericarditis as lower probability.",
    "To discriminate: the serial troponin and repeat ECG separate acute coronary syndrome from the non-cardiac causes — a rise and fall confirms infarction. For dissection I'm reassured by equal blood pressures in both arms, no radio-femoral delay and a normal mediastinum on the chest X-ray. For pulmonary embolism the normal saturations, absence of calf signs and low Wells score make it unlikely, so I would not order a CTPA. Reflux would not be relieved by rest or raise troponin.",
    "Please arrange an echocardiogram as well.",
    "My final diagnosis is a non-ST-elevation myocardial infarction on a background of crescendo angina. The exertional retrosternal heaviness radiating to the left arm and jaw, relieved by rest and associated with diaphoresis, is ischaemic cardiac pain. The three-week crescendo pattern ending in a prolonged episode at rest defines an acute coronary syndrome. The ECG shows horizontal ST depression in V4 to V6 with inferior T-wave inversion but no ST elevation, and the troponin rises from 214 to 890, so this is an NSTEMI rather than unstable angina or a STEMI. The regional hypokinesia on echo confirms it. His risk factors are hypertension, undiagnosed diabetes with an HbA1c of 7.4, dyslipidaemia, smoking and a first-degree family history of premature coronary disease. I excluded aortic dissection on the inter-arm pressures and mediastinum, and pulmonary embolism on the clinical probability.",
    "Please evaluate my performance now.",
]

# ---------------------------------------------------------------------------
# 2. The weak student — anchors early, few questions, jargon, guesses
# ---------------------------------------------------------------------------
WEAK = [
    "Start case IM-002.",
    "Do you have chest pain?",
    "Is it severe?",
    "Any diaphoresis or dyspnoea?",
    "Is it a cardiac pain or a gastric pain?",
    "Do an ECG.",
    "Is this a heart attack?",
    "Give me a hint.",
    "My differential is acute coronary syndrome and gastritis.",
    "My final diagnosis is heart attack.",
    "Evaluate my performance.",
]

# ---------------------------------------------------------------------------
# 3. The average student — decent history, incomplete workup, right answer
# ---------------------------------------------------------------------------
AVERAGE = [
    "Start case IM-002.",
    "What brings you in today?",
    "Where is the pain exactly?",
    "What does the pain feel like?",
    "Does the pain go anywhere else?",
    "When did it start?",
    "Does anything make it worse?",
    "Does resting help?",
    "Do you have any medical problems like blood pressure or diabetes?",
    "Do you smoke?",
    "Please check the vital signs.",
    "Please examine the cardiovascular system.",
    "Please do an ECG.",
    "Please send a troponin.",
    "Please do a chest X-ray.",
    "My differential is acute coronary syndrome, because of the central chest pain radiating to the arm with risk factors; gastro-oesophageal reflux, because he gets heartburn; and musculoskeletal pain.",
    "I would use the troponin and the ECG to tell them apart.",
    "My final diagnosis is acute coronary syndrome. He has central chest pain going to the left arm, he is a smoker with high blood pressure, and the ECG shows ST depression with a raised troponin.",
    "Please evaluate my performance.",
]

STUDENTS: dict[str, list[str]] = {
    "strong": STRONG,
    "average": AVERAGE,
    "weak": WEAK,
}

LABELS = {
    "strong": "1. Perfect student",
    "average": "3. Average student",
    "weak": "2. Less-knowledge student",
}


def _retarget(script: list[str], case_id: str) -> list[str]:
    return [t.replace(DEFAULT_CASE, case_id) for t in script]


async def _play(name: str, script: list[str], verbose: bool) -> dict[str, Any]:
    service = InMemorySessionService()
    session = await service.create_session(app_name=APP, user_id=name)
    runner = Runner(app_name=APP, agent=root_agent, session_service=service)

    for turn in script:
        if verbose:
            print(f"\n\033[1m{name}>\033[0m {turn}")
        reply: list[str] = []
        content = types.Content(role="user", parts=[types.Part(text=turn)])
        async for event in runner.run_async(
            user_id=name, session_id=session.id, new_message=content
        ):
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text:
                        reply.append(part.text)
        if verbose:
            print("".join(reply).strip())
        else:
            print(".", end="", flush=True)

    final = await service.get_session(app_name=APP, user_id=name, session_id=session.id)
    enc = (final.state or {}).get(S.KEY) or {}
    return {
        "student": name,
        "turns": len(script),
        "questions": len(enc.get("questions_asked", [])),
        "examinations": len(enc.get("exams_requested", [])),
        "investigations": len(enc.get("investigations_ordered", [])),
        "hints_used": enc.get("hints_used", 0),
        "revealed": enc.get("revealed", False),
        "differential_size": len(enc.get("differential_submitted", [])),
        "scorecard": enc.get("scorecard"),
    }


DEFAULT_ENGINE = os.getenv(
    "AGENT_ENGINE_RESOURCE",
    "projects/ge-standard-trail/locations/us-central1/reasoningEngines/907116334368686080",
)


def _play_remote_sync(name: str, script: list[str], engine: str, verbose: bool) -> dict[str, Any]:
    """Drive the agent deployed on Agent Runtime, not the local copy.

    Same return shape as `_play`, so the comparison table does not care which
    one produced it. Worth using before a demo: local code passing tells you
    nothing about what students will actually hit.
    """
    import vertexai

    _, project, _, location, _, _ = engine.split("/")
    client = vertexai.Client(project=project, location=location)
    agent = client.agent_engines.get(name=engine)

    created = agent.create_session(user_id=name)
    sid = created["id"] if isinstance(created, dict) else created.id

    for turn in script:
        if verbose:
            print(f"\n\033[1m{name}>\033[0m {turn}")
        reply: list[str] = []
        for event in agent.stream_query(user_id=name, session_id=sid, message=turn):
            for part in (event.get("content", {}) or {}).get("parts", []) or []:
                if part.get("text"):
                    reply.append(part["text"])
        if verbose:
            print("".join(reply).strip())
        else:
            print(".", end="", flush=True)

    full = agent.get_session(user_id=name, session_id=sid)
    state = (full.get("state") if isinstance(full, dict) else full.state) or {}
    enc = state.get(S.KEY) or {}
    return {
        "student": name,
        "turns": len(script),
        "questions": len(enc.get("questions_asked", [])),
        "examinations": len(enc.get("exams_requested", [])),
        "investigations": len(enc.get("investigations_ordered", [])),
        "hints_used": enc.get("hints_used", 0),
        "revealed": enc.get("revealed", False),
        "differential_size": len(enc.get("differential_submitted", [])),
        "scorecard": enc.get("scorecard"),
    }


async def _play_remote(name: str, script: list[str], engine: str, verbose: bool) -> dict[str, Any]:
    return await asyncio.to_thread(_play_remote_sync, name, script, engine, verbose)


SKILL_ORDER = [
    "history_taking",
    "communication",
    "clinical_reasoning",
    "differential_diagnosis",
    "investigation_selection",
    "case_synthesis",
]


def _report(results: list[dict[str, Any]], case_id: str) -> None:
    scored = [r for r in results if r.get("scorecard")]
    if not scored:
        print("\nNo scorecards were produced — the evaluator did not run.")
        return

    order = ["strong", "average", "weak"]
    scored.sort(key=lambda r: order.index(r["student"]))

    w = 26
    print(f"\n\n{'=' * (w + 14 * len(scored))}")
    print(f"MARKING COMPARISON — case {case_id}")
    print("=" * (w + 14 * len(scored)))

    def row(label: str, values: list[Any]) -> None:
        print(f"{label:<{w}}" + "".join(f"{str(v):>14}" for v in values))

    row("", [LABELS[r["student"]].split(".")[1].strip()[:13] for r in scored])
    print("-" * (w + 14 * len(scored)))
    row("OVERALL /100", [r["scorecard"]["overall_score"] for r in scored])
    row("Band", [r["scorecard"]["band"] for r in scored])
    print("-" * (w + 14 * len(scored)))
    for skill in SKILL_ORDER:
        row(
            "  " + skill.replace("_", " ").title(),
            [r["scorecard"]["skills"][skill] for r in scored],
        )
    print("-" * (w + 14 * len(scored)))
    row("Questions asked", [r["questions"] for r in scored])
    row("Examinations", [r["examinations"] for r in scored])
    row("Investigations", [r["investigations"] for r in scored])
    row("Differentials given", [r["differential_size"] for r in scored])
    row("Hints used", [r["hints_used"] for r in scored])
    row("Correct diagnosis", [
        "yes" if r["scorecard"]["detail"]["case_synthesis"]["final_diagnosis_correct"] else "no"
        for r in scored
    ])
    print("=" * (w + 14 * len(scored)))

    for r in scored:
        card = r["scorecard"]
        d = card["detail"]
        print(f"\n--- {LABELS[r['student']]} — {card['overall_score']}/100 ({card['band']})")
        crit = [m["label"] for m in d["history_taking"]["missed"] if m["critical"]]
        if crit:
            print(f"    critical history missed : {', '.join(crit[:4])}")
        me = d["differential_diagnosis"]["missed_must_exclude"]
        if me:
            print(f"    must-exclude missed     : {', '.join(m['dx'] for m in me)}")
        notes = d["communication"]["notes"]
        if notes:
            print(f"    communication           : {notes[0]}")
        unused = d["clinical_reasoning"]["critical_clues_unused"]
        if unused:
            print(f"    clues walked past       : {', '.join(unused[:6])}")


async def _main(args) -> int:
    names = [args.student] if args.student else ["strong", "average", "weak"]

    def run(name):
        script = _retarget(STUDENTS[name], args.case)
        if args.remote:
            return _play_remote(name, script, args.engine, args.verbose)
        return _play(name, script, args.verbose)

    if args.remote:
        print(f"Target: DEPLOYED agent {args.engine.rsplit('/', 1)[-1]}")
    else:
        print("Target: local code")

    if args.serial or args.verbose or len(names) == 1:
        # Serial keeps the transcript readable; parallel interleaves it.
        results = []
        for name in names:
            print(f"\n>>> Running {LABELS[name]} ", end="", flush=True)
            results.append(await run(name))
    else:
        # The students are independent sessions, so wall-clock is the longest
        # script rather than the sum of all three.
        print(f">>> Running {len(names)} students concurrently ", end="", flush=True)
        results = list(await asyncio.gather(*(run(name) for name in names)))
    _report(results, args.case)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(results, fh, indent=2)
        print(f"\nFull results written to {args.out}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--student", choices=list(STUDENTS), help="run just one")
    p.add_argument("--case", default=DEFAULT_CASE)
    p.add_argument("--verbose", action="store_true", help="print the whole transcript")
    p.add_argument("--serial", action="store_true", help="run students one at a time")
    p.add_argument("--remote", action="store_true",
                   help="run against the deployed Agent Runtime agent instead of local code")
    p.add_argument("--engine", default=DEFAULT_ENGINE,
                   help="Agent Engine resource name to use with --remote")
    p.add_argument("--out", help="write full results as JSON")
    return asyncio.run(_main(p.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
