"""Contextual reference resolution — short replies are answers, in code.

"The current one", "use the new one", "the second option", "same as
above", "I don't have it" are complete answers when the context is known.
This resolver makes the interpretation deterministic: given the candidate
values in play (most recent / current FIRST), it picks the referent or
says plainly that it cannot — it never guesses. An unresolved reply is a
license for ONE concrete clarification, never for re-asking the original
question the student just answered.
"""

from __future__ import annotations

import re
from typing import Any

_AFFIRM = re.compile(r"^(yes|yeah|yep|sure|correct|right|ok(ay)?|exactly)\b")
_NEGATE = re.compile(r"^(no|nope|nah|neither)\b")
_DECLINED = re.compile(
    r"(don'?t have|do not have|haven'?t|not yet|don'?t know|no idea|not sure yet)"
)
_CURRENT = re.compile(
    r"(current|latest|new(est)? one|use the new|recent one|the new one|what i (just )?said)"
)
_PREVIOUS = re.compile(
    r"(previous|old(er)? one|earlier one|original|keep the (old|previous|first)"
    r"|the one before)"
)
_SAME = re.compile(r"^same( as (above|before))?\b")
_ORDINALS = ("first", "second", "third", "fourth", "fifth")
_NUMBERED = re.compile(r"(?:option|number|no\.?)\s*(\d)|(\d)(?:st|nd|rd|th)\b")


def _selected(option: dict[str, Any], basis: str) -> dict[str, Any]:
    return {
        "resolution": "selected",
        "label": option.get("label", ""),
        "value": option.get("value"),
        "basis": basis,
    }


def resolve_reference(
    reply: str, options: list[dict[str, Any]]
) -> dict[str, Any]:
    """Resolve a short contextual reply against the candidates in play.

    `options` are ordered most-recent/current FIRST — options[0] is what
    the conversation just established, options[1] the older alternative.
    """
    flat = " ".join(str(reply or "").casefold().split()).strip(" .!,")
    options = [o for o in (options or []) if isinstance(o, dict)]

    if _DECLINED.search(flat):
        return {
            "resolution": "declined",
            "basis": "the student says they do not have it — accept and move on",
        }
    if _AFFIRM.match(flat):
        return {"resolution": "affirmed", "basis": "plain agreement"}
    if _NEGATE.match(flat):
        return {"resolution": "negated", "basis": "plain refusal"}

    if options:
        if _CURRENT.search(flat) or _SAME.match(flat):
            return _selected(
                options[0],
                "refers to the current/most recent value in the conversation",
            )
        if _PREVIOUS.search(flat) and len(options) > 1:
            return _selected(options[1], "refers to the earlier/previous value")
        for index, word in enumerate(_ORDINALS):
            if word in flat and index < len(options):
                return _selected(options[index], f"ordinal reference: {word}")
        numbered = _NUMBERED.search(flat)
        if numbered:
            index = int(numbered.group(1) or numbered.group(2)) - 1
            if 0 <= index < len(options):
                return _selected(options[index], "numbered reference")

    return {
        "resolution": "unresolved",
        "basis": (
            "no contextual pattern matched — ask ONE concrete clarification, "
            "never repeat the original question verbatim"
        ),
    }
