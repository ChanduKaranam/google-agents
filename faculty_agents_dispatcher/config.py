"""Configuration for the Faculty dispatcher agent.

Values are read from the environment. `adk run` / `adk web` load the sibling
`.env` file automatically; on Agent Engine set these as deployment env vars.
"""

import os

# Sethu API base, including the /api/v1 suffix.
#   dev  https://sethu-dev-api.onrender.com/api/v1
#   prod https://api.sethu.tilicho.in/api/v1
# Never point at prod until Purna explicitly clears it.
SETHU_API_BASE_URL = os.environ.get('SETHU_API_BASE_URL', '').rstrip('/')

# Server-to-server credential for the /auth/agent-tokens/* endpoints.
# Rotates; read from the environment, never from source.
AGENT_AUTH_SECRET = os.environ.get('AGENT_AUTH_SECRET', '')

# The Gemini Enterprise authorization resource attached to this agent. Agent
# Engine writes the caller's OAuth access token into session state under this
# exact id — see vertexai/agent_engines/templates/adk.py, which does
# `session_state[auth_id] = auth.access_token`.
#
# Each authorization resource can be attached to only one agent, so this agent
# has its own (`sethu-faculty`) rather than sharing the Campus Ambassador's.
# Same OAuth client, so the same consent screen and scopes.
GE_AUTHORIZATION_ID = os.environ.get('GE_AUTHORIZATION_ID', 'sethu-faculty')

# True when running on Cloud Run / Agent Engine rather than a developer machine.
IS_DEPLOYED = bool(os.environ.get('K_SERVICE') or os.environ.get('K_REVISION'))

# Local-development escape hatches, for running outside Gemini Enterprise where
# no caller identity is forwarded.
#   ..._GOOGLE_ACCESS_TOKEN — a Google OAuth access token, exchanged normally.
#   ..._AGENT_TOKEN         — a Sethu agent token, used as-is, no exchange.
#
# Both need FACULTY_AGENT_ALLOW_DEV_AUTH=1 *and* a non-deployed runtime. A
# pre-minted token on a deployed instance is a data leak: every professor would
# act as one test account and see one person's students.
ALLOW_DEV_AUTH = (
    os.environ.get('FACULTY_AGENT_ALLOW_DEV_AUTH', '') == '1' and not IS_DEPLOYED
)

DEV_GOOGLE_ACCESS_TOKEN = (
    os.environ.get('FACULTY_AGENT_DEV_GOOGLE_ACCESS_TOKEN', '')
    if ALLOW_DEV_AUTH
    else ''
)
DEV_AGENT_TOKEN = (
    os.environ.get('SETHU_DEV_AGENT_TOKEN', '') if ALLOW_DEV_AUTH else ''
)

# Sethu's dev API sleeps on Render's free tier; the request that wakes it has
# been measured at ~45s. Hence the generous timeout, plus one retry on
# transport failure only — never on a real API answer.
REQUEST_TIMEOUT_SECONDS = float(os.environ.get('SETHU_API_TIMEOUT', '60'))

# Re-exchange a Sethu token once it is within this many days of expiring,
# rather than letting a long conversation fail mid-flight.
TOKEN_REFRESH_MARGIN_DAYS = 1
