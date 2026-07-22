"""Exercise every PRD module against the deployed agent, in one conversation.

The smoke test proves the plumbing. This proves the *product*: that each of the
eight modules actually does its job on a real resume, with real search.

Judgement is deliberately left to a human -- each turn prints what came back so
it can be read. The automated checks below only catch hard failures (empty
reply, quota error, wrong specialist, refusal), because "is this a good alumni
recommendation" is not something an assertion can answer.

Usage: python scripts/prd_walkthrough.py <resource> <resume.pdf>
"""

import asyncio
import base64
import json
import sys

import vertexai
from vertexai import agent_engines

USER = "prd-walkthrough2@tilicho.in"
PAUSE = 20  # seconds between turns; 90 QPM is shared and fan-out is expensive

JD = """Machine Learning Engineer, New Grad - Stripe
Requirements: 2+ years Python, production ML systems, PyTorch or TensorFlow,
distributed training, Kubernetes, feature stores, model monitoring, A/B testing
at scale, strong SQL. Nice to have: Go, Ray, streaming (Kafka/Flink), MLOps
tooling (Kubeflow, MLflow), experience with recommendation or ranking systems."""

TURNS = [
    ("M1 Profile", "Here is my resume. Build my profile.", True),
    ("M2 Companies", "Which companies should I target, and what's open right now?", False),
    ("M3 Alumni", "Find alumni or people at Stripe who could refer me.", False),
    ("M4 Matching", "Rank those people by how likely they are to actually refer me.", False),
    ("M5 Resume gap", f"Compare me against this job description and tell me what I'm missing:\n\n{JD}", False),
    ("M6 Outreach", "Write a referral request to the best-ranked person.", False),
    ("M7 Tracker", "I applied to Stripe for ML Engineer New Grad. Status Applied.", False),
    ("M8 Coach", "What should I focus on over the next month?", False),
]

EXPECTED = {
    "M1 Profile": "profile_agent", "M2 Companies": "company_agent",
    "M3 Alumni": "alumni_agent", "M4 Matching": "matching_agent",
    "M5 Resume gap": "resume_gap_agent", "M6 Outreach": "outreach_agent",
    "M7 Tracker": "tracker_agent", "M8 Coach": "coach_agent",
}


async def run_turn(agent, sid, label, text, pdf, attach):
    parts = [{"text": text}]
    req = {"message": {"role": "user", "parts": parts}, "user_id": USER, "session_id": sid}
    if attach:
        fn = "asha_rangan_resume.pdf"
        parts += [{"text": f"\n<start_of_user_uploaded_file: {fn}>"},
                  {"text": f"<end_of_user_uploaded_file: {fn}>\n"}]
        req["artifacts"] = [{"file_name": fn, "versions": [{"version": "0", "data": {
            "inline_data": {"mime_type": "application/pdf",
                            "data": base64.b64encode(pdf).decode()}}}]}]

    out, calls, errs = [], [], []
    async for ev in agent.streaming_agent_run_with_events(request_json=json.dumps(req)):
        for e in (ev.get("events") or [ev]):
            if e.get("errorMessage"):
                errs.append(e["errorMessage"][:150])
            for p in ((e.get("content") or {}).get("parts") or []):
                fc = p.get("functionCall") or p.get("function_call")
                if fc:
                    calls.append(fc.get("name"))
                if p.get("text"):
                    out.append(p["text"])

    reply = "".join(out).strip()
    print(f"\n{'='*72}\n{label}\n{'='*72}")
    print("delegated to:", calls or "(nothing)")
    if errs:
        print("ERRORS:", errs)
    print(reply[:2200] + ("..." if len(reply) > 2200 else "") or "(EMPTY REPLY)")

    want = EXPECTED[label]
    return {
        "label": label,
        "right_specialist": want in calls,
        "non_empty": bool(reply),
        "no_error": not errs,
        "reply": reply,
    }


async def main(resource, pdf_path):
    vertexai.init(project="supadha-dev", location="us-central1")
    agent = agent_engines.get(resource)
    pdf = open(pdf_path, "rb").read()
    s = agent.create_session(user_id=USER)
    sid = s["id"] if isinstance(s, dict) else s.id
    print("session:", sid)

    results = []
    for i, (label, text, attach) in enumerate(TURNS):
        results.append(await run_turn(agent, sid, label, text, pdf, attach))
        if i < len(TURNS) - 1:
            await asyncio.sleep(PAUSE)

    print(f"\n{'='*72}\nSUMMARY\n{'='*72}")
    bad = []
    for r in results:
        flags = [k for k in ("right_specialist", "non_empty", "no_error") if not r[k]]
        print(f"  {'PASS' if not flags else 'FAIL'}  {r['label']:<16}"
              f"{'' if not flags else '  <- ' + ', '.join(flags)}")
        if flags:
            bad.append(r["label"])
    print(f"\n{len(results)-len(bad)}/{len(results)} modules mechanically OK")
    print("Read the outputs above to judge QUALITY -- that is not automatable.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1], sys.argv[2])))
