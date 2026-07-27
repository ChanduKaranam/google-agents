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

LOCAL_HOST_DEFAULT = "localhost:8080"


def require_public_host(public_host_env: str | None, k_service_env: str | None) -> str:
    """Resolve PUBLIC_HOST, refusing the localhost default on Cloud Run.

    A deploy that forgets PUBLIC_HOST boots green and serves a card advertising
    `https://localhost:8080/` -- a dead agent that looks healthy, because
    nothing on this side ever calls that url. Cloud Run always sets K_SERVICE,
    so its presence is the signal that a real host was required.
    """
    if public_host_env:
        return public_host_env
    if k_service_env:
        raise RuntimeError(
            "Refusing to serve an agent card pointing at localhost."
            " Set PUBLIC_HOST to this service's public hostname"
            " (e.g. job-helper-a2a-xyz.a.run.app)."
        )
    return LOCAL_HOST_DEFAULT


def load_agent_card(public_host: str, protocol: str) -> AgentCard:
    """Load the static card and resolve its url for this deployment."""
    raw = json.loads(CARD_PATH.read_text())
    raw["url"] = f"{protocol}://{public_host}/"
    return AgentCard(**raw)
