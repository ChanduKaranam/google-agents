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

"""Audit hook for profile writes.

Implements the two Phase-1-relevant observability requirements:

* Spec §10.2 — "Profile write source distribution: any non-`user_stated`
  profile write is an alarm." Emitted as `tier_counts`, with an explicit
  `alarm` flag when a student fact is stored at an unexpected tier.
* Spec §10.3 / §9 — redaction before the sink is mandatory. This plugin logs
  field *names*, tiers, and outcomes. It never logs a value or an evidence
  span, both of which are the student's personal data.

Failures here are swallowed: observability must not be able to break a turn.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from typing import Any

from google.adk.plugins.base_plugin import BasePlugin
from google.adk.tools import BaseTool, ToolContext

from app.schemas import ClaimTier

logger = logging.getLogger("msbuddy.profile_audit")

# Tools whose results touch the profile and therefore warrant an audit line.
AUDITED_TOOLS = frozenset(
    {
        "save_profile_fields",
        "clear_profile_fields",
    }
)

# Anything a student-stated field may legitimately be recorded as.
EXPECTED_WRITE_TIERS = frozenset({ClaimTier.USER_STATED.value})


class ProfileAuditPlugin(BasePlugin):
    """Emits a redacted, structured audit line for every profile mutation."""

    def __init__(self, name: str = "profile_audit") -> None:
        super().__init__(name=name)

    async def after_tool_callback(
        self,
        *,
        tool: BaseTool,
        tool_args: dict[str, Any],
        tool_context: ToolContext,
        result: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Log the outcome of a profile-mutating tool call. Never alters it."""
        try:
            if tool.name in AUDITED_TOOLS and isinstance(result, dict):
                logger.info(json.dumps(self._build_record(tool, tool_context, result)))
        # Broad by intent: observability must never be able to break a turn.
        except Exception:
            logger.exception("profile audit record could not be emitted")
        return None

    @staticmethod
    def _build_record(
        tool: BaseTool,
        tool_context: ToolContext,
        result: dict[str, Any],
    ) -> dict[str, Any]:
        """Build the redacted audit record. Names and tiers only — no values."""
        saved = [e for e in result.get("saved", []) if isinstance(e, dict)]
        rejected = [e for e in result.get("rejected", []) if isinstance(e, dict)]
        derived = [d for d in result.get("derived", []) if isinstance(d, dict)]

        tier_counts = Counter(str(entry.get("tier")) for entry in saved)
        unexpected = sorted(
            {
                str(entry.get("tier"))
                for entry in saved
                if str(entry.get("tier")) not in EXPECTED_WRITE_TIERS
            }
        )

        return {
            "event": "profile_write",
            "tool": tool.name,
            "invocation_id": getattr(tool_context, "invocation_id", None),
            "status": result.get("status"),
            # Field NAMES only. Values and evidence spans are PII (§9).
            "saved_fields": [str(entry.get("field")) for entry in saved],
            "rejected_fields": [str(entry.get("field")) for entry in rejected],
            "rejection_reasons": sorted(
                {str(entry.get("reason")) for entry in rejected}
            ),
            "removed_fields": [str(name) for name in result.get("removed", [])],
            "cleared_all": bool(result.get("cleared_all", False)),
            "derived_rule_ids": [str(d.get("rule_id")) for d in derived],
            "tier_counts": dict(tier_counts),
            "unexpected_tiers": unexpected,
            "alarm": bool(unexpected),
        }
