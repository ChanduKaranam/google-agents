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

"""Root-agent callbacks.

The retrieval budget from spec §8.4 lives here rather than in a plugin: it is
per-agent logic (the root's delegation to research), and ADK's guidance is
plugins for cross-cutting concerns, callbacks for per-agent behaviour.

Returning a dict from `before_tool_callback` skips the tool and hands that
dict back as the result — so exceeding the cap yields partial results *and
says so*, which is what §8.4 requires, rather than failing silently or
looping.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from google.adk.tools import BaseTool, ToolContext

from app.config import (
    MAX_RETRIEVALS_PER_SESSION,
    MAX_RETRIEVALS_PER_TURN,
    STATE_RETRIEVAL_COUNT,
)

logger = logging.getLogger("msbuddy.retrieval_budget")

# Every agent that can reach the network, by the name it is exposed under.
# The budget is about outbound retrieval, not about which capability asked
# for it, so a second search agent has to appear here or alumni discovery
# would search without a ceiling. Kept in step with the agent tree by
# `test_alumni_structure.py`, which asserts this set covers every grounded
# agent the root can reach.
RESEARCH_TOOL_NAMES = frozenset({"program_research_agent", "alumni_discovery_agent"})


async def enforce_retrieval_budget(
    tool: BaseTool, args: dict[str, Any], tool_context: ToolContext
) -> dict[str, Any] | None:
    """Cap how often one turn and one session may reach the network."""
    if tool.name not in RESEARCH_TOOL_NAMES:
        return None

    stored = tool_context.state.get(STATE_RETRIEVAL_COUNT)
    counters: dict[str, Any] = dict(stored) if isinstance(stored, dict) else {}

    invocation_id = getattr(tool_context, "invocation_id", None)
    session_count = int(counters.get("session") or 0)
    turn_count = int(counters.get("turn") or 0)
    if counters.get("turn_id") != invocation_id:
        turn_count = 0

    over_turn = turn_count >= MAX_RETRIEVALS_PER_TURN
    over_session = session_count >= MAX_RETRIEVALS_PER_SESSION

    if over_turn or over_session:
        scope = "turn" if over_turn else "session"
        limit = MAX_RETRIEVALS_PER_TURN if over_turn else MAX_RETRIEVALS_PER_SESSION
        logger.warning(
            json.dumps(
                {
                    "event": "retrieval_budget_exceeded",
                    "scope": scope,
                    "limit": limit,
                    "invocation_id": invocation_id,
                }
            )
        )
        return {
            "status": "error",
            "reason": f"retrieval_budget_exceeded_{scope}",
            "message": (
                f"The {scope} search limit of {limit} has been reached, so no "
                "further searching happened. Work with what has already been "
                "retrieved, and tell the student plainly that the results are "
                "partial and which programs were not looked up."
            ),
        }

    tool_context.state[STATE_RETRIEVAL_COUNT] = {
        "turn_id": invocation_id,
        "turn": turn_count + 1,
        "session": session_count + 1,
    }
    return None
