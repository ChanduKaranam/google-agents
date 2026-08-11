"""The agent card GE calls back on.

`to_a2a()` uses a supplied card verbatim and never fills anything in — its
`host`/`port`/`protocol` arguments only feed the builder that runs when no card
is given. So the public URL has to be injected here, before the card is passed.

The card on disk carries a localhost placeholder. Registering that file with GE
produces an agent that looks alive and does nothing, because GE dutifully calls
localhost.
"""

import json
import os
from pathlib import Path

from a2a.types import AgentCard

CARD_PATH = Path(__file__).parent / 'agent_card.json'


def require_public_host(public_host: str | None, k_service: str | None) -> str:
    """Refuse to serve a card advertising localhost from a real deployment.

    A deploy that forgets PUBLIC_HOST would otherwise boot green and serve a
    dead agent. Cloud Run always sets K_SERVICE, so its presence means a real
    host was required.
    """
    if public_host:
        return public_host
    if k_service:
        raise RuntimeError(
            'Refusing to serve a card pointing at localhost. Set PUBLIC_HOST to'
            ' this service\'s hostname and redeploy.'
        )
    return 'localhost:8080'


def load_agent_card(public_host: str, protocol: str = 'https') -> AgentCard:
    raw = json.loads(CARD_PATH.read_text(encoding='utf-8'))
    raw['url'] = f'{protocol}://{public_host}/'
    return AgentCard(**raw)


def card_from_env() -> AgentCard:
    host = require_public_host(
        os.environ.get('PUBLIC_HOST'), os.environ.get('K_SERVICE')
    )
    return load_agent_card(host, os.environ.get('PROTOCOL', 'https'))
