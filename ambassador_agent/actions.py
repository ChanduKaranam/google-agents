"""Parse and route A2UI button clicks.

An inbound A2A DataPart carrying no ADK metadata is converted to an inline_data
blob wrapped in <a2a_datapart_json> tags (`part_converter.py:176-183`), so the
click arrives inside the user turn rather than on a separate channel. Parsing it
here keeps routing deterministic: the model never has to guess which button was
pressed.
"""

import json
import re

_TAGGED = re.compile(r"<a2a_datapart_json>(.*?)</a2a_datapart_json>", re.S)


def parse_user_action(content: str) -> dict | None:
    """Return the userAction payload, or None when this is ordinary text."""
    if not content:
        return None
    for match in _TAGGED.finditer(content):
        try:
            payload = json.loads(match.group(1))
        except ValueError:
            continue
        data = payload.get("data") or payload
        action = data.get("userAction")
        if action and action.get("name"):
            return action
    return None
