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

# Gemini Enterprise agents that are ours, not a professor's.
#
# Sethu's sync ingests every GE agent with a creator in the audit log, so this
# agent and its siblings arrive as claimable "faculty agents" — measured
# 2026-08-13, a freshly created faculty agent and our own dispatcher are
# byte-identical in the API response apart from their ids. Until Sethu filters
# them out, or exposes a creator so we can, the ids are listed here.
#
# Comma-separated GE agent ids, as they appear at the end of an openUrl.
HIDDEN_GE_AGENT_IDS = frozenset(
    part.strip() for part in os.environ.get(
        'FACULTY_HIDDEN_GE_AGENTS',
        # Our own dispatchers in the ge-standard-trail GE app: Champion
        # Faculty and Campus Ambassador. Sethu's sync ingests them like any
        # other agent, so without this a professor is offered the very agent
        # they are talking to. Ids are per-app, so this list is rebuilt
        # whenever the project moves.
        '18101167715781202478,6010108904994977742',
    ).split(',') if part.strip()
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

# How long to wait for Sethu to accept a sync request. Short on purpose: this
# fires while a professor is being greeted, and the answer is not needed — the
# sync runs in the background either way.
SYNC_TRIGGER_TIMEOUT_SECONDS = float(
    os.environ.get('SETHU_SYNC_TRIGGER_TIMEOUT', '10')
)

# Re-exchange a Sethu token once it is within this many days of expiring,
# rather than letting a long conversation fail mid-flight.
TOKEN_REFRESH_MARGIN_DAYS = 1


# --- Gemini Enterprise agent readiness -------------------------------------
#
# A professor can publish an agent through us while that agent is still
# PRIVATE, or ENABLED but shared with nobody. Sethu accepts it, we message the
# students, and every one of them opens a link that says "this conversation is
# read-only as the agent used is no longer available" — measured 2026-08-19 on
# Hackashop v2. Nothing in our own flow can prevent that, because publishing
# here writes to Sethu and never touches Discovery Engine.
#
# So we read the agent's own state before publishing and before sending, and
# refuse rather than send a dead link. Two fields have to be right:
#   state = ENABLED      the agent has been published in the console
#   scope = ALL_USERS    it is shared, not restricted to its creator
#
# Publishing in the console sets ENABLED *and resets scope to RESTRICTED*, so
# the two are genuinely independent and both need checking.
GE_READINESS_CHECK = os.environ.get('FACULTY_GE_READINESS_CHECK', '1') == '1'

# The Gemini Enterprise app the professors' agents live in. Ids are per-app, so
# these move with the project — the same rebuild as HIDDEN_GE_AGENT_IDS.
GE_PROJECT_ID = os.environ.get('GE_PROJECT_ID', 'ge-standard-trail')
GE_ENGINE_ID = os.environ.get(
    'GE_ENGINE_ID', 'tl-ge-standard-aug-2026_1786977983132'
)

# Seconds to wait on the Discovery Engine read. Kept short: this sits in front
# of a professor waiting for a reply, and an unanswered check fails open.
GE_READINESS_TIMEOUT_SECONDS = float(
    os.environ.get('FACULTY_GE_READINESS_TIMEOUT', '6')
)


# --- how timestamps are shown ----------------------------------------------
#
# Sethu sends UTC ("2026-08-20T05:38:28.289Z") and the cards used to print the
# characters straight out of that string, so a sync at 11:08 in the morning
# read as "05:38" to the professor who had just watched it happen.
#
# A fixed offset rather than a named zone: the container has no tzdata, so
# zoneinfo('Asia/Kolkata') raises there while working fine on a laptop. India
# has no daylight saving, so the offset is the whole truth.
DISPLAY_UTC_OFFSET_MINUTES = int(
    os.environ.get('FACULTY_DISPLAY_UTC_OFFSET_MINUTES', '330')
)
DISPLAY_TZ_LABEL = os.environ.get('FACULTY_DISPLAY_TZ_LABEL', 'IST')


# How long a requested Sethu sync is considered fresh enough. A professor who
# reopens yesterday's conversation should get current figures, but five taps in
# a row should not queue five enumerations of the whole engine.
SYNC_MIN_INTERVAL_SECONDS = float(
    os.environ.get('FACULTY_SYNC_MIN_INTERVAL_SECONDS', '600')
)
