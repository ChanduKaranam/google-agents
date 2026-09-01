"""Emits the A2A agent card to paste into Gemini Enterprise.

    python -m clinical_simulator.agent_card https://your-service.a.run.app

Two things this does that the auto-generated card does not:

* **Curated skills.** ADK's `to_a2a()` builds one skill per tool, so the card
  ends up advertising `reveal_answer` and `submit_differential` as if they were
  things a user would ask for. Gemini Enterprise uses skills to decide when to
  route to this agent, so it gets the four things a student actually wants.
* **v0.3 field names.** a2a-sdk 1.1.2 serves the A2A v1.0 shape, which carries
  `supportedInterfaces` instead of a top-level `url` and `protocolVersion`.
  Gemini Enterprise's registration form documents the v0.3 fields, so this
  emits those. Pass --v1 for the 1.0 shape if the console rejects it.
"""

from __future__ import annotations

import argparse
import json
import sys

from .agent import root_agent
from .cases import list_cases

SKILLS = [
    {
        "id": "start_clinical_case",
        "name": "Start a clinical case",
        "description": (
            "Begin a simulated patient encounter in Internal Medicine at a "
            "chosen difficulty level, from beginner cases with strong clues to "
            "expert cases with incomplete and evolving information."
        ),
        "tags": ["medical education", "simulation", "clinical reasoning", "MBBS"],
        "examples": [
            "Start a clinical case",
            "Give me a beginner internal medicine case",
            "I want to practise history taking",
            "List the available cases",
        ],
    },
    {
        "id": "interview_virtual_patient",
        "name": "Interview a virtual patient",
        "description": (
            "Take a history from a simulated patient who answers only what is "
            "asked, in lay language, and never reveals the diagnosis. Request "
            "physical examination findings and order investigations."
        ),
        "tags": ["history taking", "virtual patient", "OSCE", "communication"],
        "examples": [
            "What brings you in today?",
            "Does the pain radiate anywhere?",
            "Check the vital signs",
            "Order an ECG and troponin",
        ],
    },
    {
        "id": "practise_clinical_reasoning",
        "name": "Practise clinical reasoning",
        "description": (
            "Build and justify a differential diagnosis, state how you would "
            "discriminate between the possibilities, and commit to a final "
            "diagnosis. The simulator will not confirm or deny the answer "
            "during the case."
        ),
        "tags": ["differential diagnosis", "clinical reasoning", "diagnosis"],
        "examples": [
            "My top three differentials are...",
            "What would you like me to investigate next?",
            "Give me a hint",
        ],
    },
    {
        "id": "clinical_performance_report",
        "name": "Get a clinical performance report",
        "description": (
            "Receive a scored report on history taking, communication, clinical "
            "reasoning, differential diagnosis, investigation selection and case "
            "synthesis, with the specific questions missed and why they mattered."
        ),
        "tags": ["assessment", "feedback", "rubric", "scoring"],
        "examples": [
            "Evaluate my performance",
            "How did I do?",
            "End the case and score me",
        ],
    },
]


def build(url: str, version: str = "1.0.0", v1_shape: bool = False) -> dict:
    url = url.rstrip("/")
    n_cases = len(list_cases())
    description = (
        f"{root_agent.description} Covers {n_cases} Internal Medicine cases "
        f"across four difficulty levels. Educational simulation only — not a "
        f"diagnostic tool and not clinical advice about a real person."
    )

    common = {
        "name": "Clinical Case Simulator",
        "description": description,
        "version": version,
        "defaultInputModes": ["text/plain"],
        "defaultOutputModes": ["text/plain"],
        "capabilities": {"streaming": False, "pushNotifications": False},
        "skills": SKILLS,
    }

    if v1_shape:
        return {
            **common,
            "supportedInterfaces": [
                {"url": url, "protocolBinding": "JSONRPC", "protocolVersion": "1.0"}
            ],
        }
    return {"protocolVersion": "0.3.0", "url": url, **common}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="Public HTTPS URL of the deployed A2A service")
    parser.add_argument("--version", default="1.0.0")
    parser.add_argument(
        "--v1", action="store_true", help="Emit the A2A v1.0 card shape instead of v0.3"
    )
    args = parser.parse_args()

    if not args.url.startswith("https://") and "localhost" not in args.url:
        print("Warning: Gemini Enterprise requires an HTTPS endpoint.", file=sys.stderr)

    print(json.dumps(build(args.url, args.version, args.v1), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
