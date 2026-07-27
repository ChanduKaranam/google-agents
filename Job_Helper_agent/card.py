"""The agent card Gemini Enterprise reads to discover this agent.

Separate from `main_a2a` on purpose. `main_a2a` builds the runner at import
time, so it cannot be imported without GCP configuration -- and the offline
test suite still needs to check the card.

The card is built in code rather than handed to `to_a2a` as a file path. When
`to_a2a` receives a card it uses it verbatim and never fills anything in
(`agent_to_a2a.py:203-205`) -- its `host`/`port`/`protocol` arguments only feed
the builder that runs when no card is supplied. So the `url` that Gemini
Enterprise calls back on has to be injected before the card is passed, or the
agent advertises no endpoint at all.
"""

import json
import pathlib

from a2a.types import AgentCard

CARD_PATH = pathlib.Path(__file__).parent / "agent_card.json"


def load_agent_card(public_host: str, protocol: str) -> AgentCard:
    """Load the static card and resolve its url for this deployment."""
    raw = json.loads(CARD_PATH.read_text())
    raw["url"] = f"{protocol}://{public_host}/"
    return AgentCard(**raw)
