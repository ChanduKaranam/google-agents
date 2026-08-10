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

"""Application documents and progress — the planning slice of MS Buddy.

Two tools. `get_application_plan` answers "where am I and what's next":
the document checklist with statuses, profile completeness, how many
programs have been researched, and every deadline research has verified.
`set_document_status` flips one checklist entry.

Deliberately boring: a fixed registry, statuses in a `user:` state key, and
a priority ladder for the next step. **Deadlines are read from the shortlist
only** — the values `save_program_record` admitted with evidence. This
module can render a deadline; it can never originate one.
"""

from __future__ import annotations

from typing import Any

from google.adk.tools import ToolContext

from app.config import STATE_DOCUMENTS, STATE_PROFILE, STATE_SHORTLIST
from app.profile_store import read_profile
from app.program_store import read_shortlist
from app.reference.profile_fields import FIELDS

# The checklist, in the order a student usually tackles it. A registry, not
# state: what documents exist is product knowledge, whether each is done is
# the student's data.
STANDARD_DOCUMENTS: tuple[tuple[str, str], ...] = (
    ("passport", "Passport"),
    ("transcripts", "Academic transcripts"),
    ("degree_certificate", "Degree certificate (or provisional)"),
    ("english_test_score", "English test score (IELTS/TOEFL)"),
    ("gre_score", "GRE score (only where a program asks for it)"),
    ("sop", "Statement of Purpose"),
    ("resume", "Resume / CV"),
    ("lor_1", "Letter of Recommendation 1"),
    ("lor_2", "Letter of Recommendation 2"),
    ("lor_3", "Letter of Recommendation 3"),
)

_DOCUMENT_KEYS = tuple(key for key, _ in STANDARD_DOCUMENTS)
_STATUSES = ("pending", "done")

CORE_FIELDS = tuple(name for name, spec in FIELDS.items() if spec.importance == "core")


def _statuses(state: Any) -> dict[str, str]:
    stored = state.get(STATE_DOCUMENTS)
    return dict(stored) if isinstance(stored, dict) else {}


def get_application_plan(tool_context: ToolContext) -> dict:
    """Show the application plan: documents, progress, and what to do next.

    Reports the document checklist with each item's status, whether the
    profile's core fields are complete, how many programs have been
    researched, every application deadline that research has verified and
    stored, and a single suggested next step.

    Returns:
        A dict with `documents`, `done_count`, `profile` completeness,
        `researched_programs`, `deadlines` (only values research stored,
        each with its evidence tier), and `next_step`.
    """
    statuses = _statuses(tool_context.state)

    documents = [
        {
            "document": key,
            "label": label,
            "state": statuses.get(key, "pending"),
        }
        for key, label in STANDARD_DOCUMENTS
    ]
    done_count = sum(1 for d in documents if d["state"] == "done")

    profile_fields = read_profile(tool_context.state, STATE_PROFILE).get("fields") or {}
    core_missing = [name for name in CORE_FIELDS if name not in profile_fields]

    shortlist = read_shortlist(tool_context.state, STATE_SHORTLIST)
    programs = shortlist.get("programs") or {}

    deadlines = [
        {
            "university": record.get("university"),
            "program": record.get("program"),
            "field": field_name,
            "value": entry.get("value"),
            "tier": entry.get("tier"),
        }
        for record in programs.values()
        for field_name, entry in (record.get("fields") or {}).items()
        if "deadline" in field_name
    ]

    # The priority ladder: profile -> research -> documents -> compare.
    if core_missing:
        next_step = "Complete the profile — still missing: " + ", ".join(core_missing)
    elif not programs:
        next_step = (
            "Research a program next, so recommendations and deadlines rest "
            "on verified facts rather than guesses."
        )
    elif done_count < len(documents):
        pending = [d["label"] for d in documents if d["state"] == "pending"]
        next_step = (
            "Prepare the pending documents: "
            + ", ".join(pending[:3])
            + ("…" if len(pending) > 3 else "")
        )
    else:
        next_step = (
            "Everything tracked is done — compare the researched programs "
            "and review the stored deadlines."
        )

    return {
        "status": "success",
        "documents": documents,
        "done_count": done_count,
        "total_documents": len(documents),
        "profile": {
            "core_complete": not core_missing,
            "core_missing": core_missing,
        },
        "researched_programs": len(programs),
        "deadlines": deadlines,
        "deadline_note": (
            ""
            if deadlines
            else (
                "No deadlines are stored yet. Deadlines come from program "
                "research — research a program to get its verified deadline."
            )
        ),
        "next_step": next_step,
    }


def set_document_status(document: str, status: str, tool_context: ToolContext) -> dict:
    """Mark one application document as done or pending.

    Args:
        document: Which document, by its checklist key — e.g. `sop`,
            `resume`, `lor_1`, `passport`, `transcripts`.
        status: `done` or `pending`.

    Returns:
        A dict confirming the change and the updated done count, or a
        refusal naming the valid documents.
    """
    key = str(document or "").strip().lower()
    if key not in _DOCUMENT_KEYS:
        return {
            "status": "error",
            "reason": "unknown_document",
            "message": f"'{document}' is not a tracked document.",
            "valid_documents": list(_DOCUMENT_KEYS),
        }
    wanted = str(status or "").strip().lower()
    if wanted not in _STATUSES:
        return {
            "status": "error",
            "reason": "unknown_status",
            "message": f"Status must be one of {_STATUSES}, not '{status}'.",
        }

    statuses = _statuses(tool_context.state)
    statuses[key] = wanted
    tool_context.state[STATE_DOCUMENTS] = statuses

    done = sum(1 for value in statuses.values() if value == "done")
    return {
        "status": "success",
        "document": key,
        "state": wanted,
        "done_count": done,
        "total_documents": len(_DOCUMENT_KEYS),
    }
