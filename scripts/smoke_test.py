"""Deployment smoke test (design spec section 8.3).

Calls the deployed agent the way Gemini Enterprise does -- via
`streaming_agent_run_with_events`, with the resume delivered as an *artifact*
plus the empty `start_of_user_uploaded_file` text markers GE actually sends.
Local `adk web` does not exercise this path, so passing there proves nothing.

Usage:
    python scripts/smoke_test.py <reasoning_engine_resource> <resume.pdf>
"""

import asyncio
import base64
import json
import sys

import vertexai
from vertexai import agent_engines

USER = "smoke-test-student@tilicho.in"


def build_request(text, session_id, filename=None, pdf_bytes=None):
    parts = [{"text": text}]
    req = {"message": {"role": "user", "parts": parts},
           "user_id": USER, "session_id": session_id}
    if filename:
        # Exactly how Gemini Enterprise presents an upload: markers naming the
        # file, with NO content between them. Bytes travel as an artifact.
        parts.append({"text": f"\n<start_of_user_uploaded_file: {filename}>"})
        parts.append({"text": f"<end_of_user_uploaded_file: {filename}>\n"})
        req["artifacts"] = [{
            "file_name": filename,
            "versions": [{"version": "0", "data": {"inline_data": {
                "mime_type": "application/pdf",
                "data": base64.b64encode(pdf_bytes).decode()}}}],
        }]
    return req


async def turn(agent, label, req):
    print(f"\n{'='*70}\n{label}\n{'='*70}")
    reply, calls = [], []
    async for ev in agent.streaming_agent_run_with_events(request_json=json.dumps(req)):
        for e in (ev.get("events") or [ev]):
            for p in ((e.get("content") or {}).get("parts") or []):
                fc = p.get("functionCall") or p.get("function_call")
                if fc:
                    calls.append(fc.get("name"))
                if p.get("text"):
                    reply.append(p["text"])
    print("tools called:", calls or "(none)")
    text = "".join(reply).strip()
    print("reply:", (text[:1500] + "...") if len(text) > 1500 else text or "(EMPTY)")
    return text, calls


async def main(resource, pdf_path):
    vertexai.init(project="supadha-dev", location="us-central1")
    agent = agent_engines.get(resource)
    pdf = open(pdf_path, "rb").read()

    s = agent.create_session(user_id=USER)
    sid = s["id"] if isinstance(s, dict) else s.id
    print("session:", sid)

    t1, c1 = await turn(agent, "TURN 1 - upload resume, build profile",
        build_request("Here is my resume. Build my profile.", sid,
                      "asha_rangan_resume.pdf", pdf))
    t2, c2 = await turn(agent, "TURN 2 - no upload; needs profile from state + search",
        build_request("Which companies should I target? Find current openings.", sid))

    sess = agent.get_session(user_id=USER, session_id=sid)
    state_keys = sorted((sess.get("state") or {}).keys())
    print(f"\n{'='*70}\nRESULTS\n{'='*70}")
    print("state keys after both turns:", state_keys)

    checks = {
        "(a) load_artifacts called": "load_artifacts" in c1,
        "(a) resume actually read": any(
            k in t1.lower() for k in ("asha", "warangal", "pytorch", "semanticshelf")),
        "(b) profile persisted to state": "profile" in state_keys,
        "(c) company search ran": "company_agent" in c2,
        "(d) turn 1 reply non-empty": bool(t1),
        "(d) turn 2 reply non-empty": bool(t2),
        "(e) identity guard did not fire": "user identity" not in t1.lower(),
    }
    print()
    for name, ok in checks.items():
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    failed = [n for n, ok in checks.items() if not ok]
    print("\n" + ("ALL PASSED" if not failed else f"FAILED: {len(failed)}"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1], sys.argv[2])))
