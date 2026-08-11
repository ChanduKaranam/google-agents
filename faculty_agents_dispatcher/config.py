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

# Draw A2UI cards instead of listing sections as prose.
#
# Off by default, and deliberately so: A2UI renders only for an agent
# registered in Gemini Enterprise as `a2aAgentDefinition`. The Agent Engine
# registration (`adkAgentDefinition`) cannot render it whatever we emit —
# measured 2026-08-05, the payload arrives as a wall of JSON in the chat. So
# this is set only in the A2A container's image, never on Agent Engine.
A2UI_ENABLED = os.environ.get('FACULTY_AGENT_A2UI', '') == '1'

# Show faculty the named-ambassador roster.
#
# The data flows — `GET /faculty/ambassadors` returns it — but whether a
# professor should see named colleagues ranked by their section's activation is
# a product decision, not a technical one (A2UI-VIEWS.md, "The larger
# question"). On by default because the view was asked for; this switch turns
# it off without a code change if product decides otherwise. The department
# dashboard and leaderboard are unaffected either way.
AMBASSADOR_VIEW_ENABLED = (
    os.environ.get('FACULTY_AMBASSADOR_VIEW', '1') == '1'
)

# Offer buttons to view another department's activation figures.
#
# Off, because Sethu does not support it: `GET /faculty/department-progress`
# resolves the scope from the caller's email and ignores a `department` query
# parameter — measured 2026-08-10, asked 'CSE' and got 'EEE' back. The buttons
# and the request already work; only Sethu's side is missing. Turn this on when
# that endpoint honours the parameter, and the switcher appears with no code
# change. Leaving it on meanwhile hands every professor a button that silently
# does nothing the first time they press it.
DEPARTMENT_SWITCH_ENABLED = (
    os.environ.get('FACULTY_DEPARTMENT_SWITCH', '') == '1'
)

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

# The notify call fans out WhatsApp messages to a whole section before it
# answers, so it is slower than every other endpoint — and a timeout there is
# the one failure where we cannot tell a professor whether their students were
# messaged. Given a longer rope for that reason.
NOTIFY_TIMEOUT_SECONDS = float(os.environ.get('SETHU_NOTIFY_TIMEOUT', '120'))

# Re-exchange a Sethu token once it is within this many days of expiring,
# rather than letting a long conversation fail mid-flight.
TOKEN_REFRESH_MARGIN_DAYS = 1
