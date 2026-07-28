import os

from google.adk.a2a.utils.agent_to_a2a import to_a2a

from .agent import root_agent
from .card import load_agent_card, require_public_host
from .runtime import build_runner

PUBLIC_HOST = require_public_host(
    os.environ.get("PUBLIC_HOST"), os.environ.get("K_SERVICE")
)
PROTOCOL = os.environ.get("PROTOCOL", "https")

app = to_a2a(
    root_agent,
    agent_card=load_agent_card(PUBLIC_HOST, PROTOCOL),
    runner=build_runner(),
)
