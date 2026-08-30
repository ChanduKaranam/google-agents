"""Configuration for Lodestar, the lead qualification orchestrator.

Values are read from the environment. `adk run` / `adk web` load the sibling
`.env` file automatically; on Agent Engine set these as deployment env vars.
"""

import os

# The model every agent in this package runs on. Kept in one place so the
# orchestrator and its specialists move together.
MODEL = os.environ.get('LODESTAR_MODEL', 'gemini-2.5-flash')

# True when running on Cloud Run / Agent Engine rather than a developer machine.
IS_DEPLOYED = bool(os.environ.get('K_SERVICE') or os.environ.get('K_REVISION'))

# --- outbound calling --------------------------------------------------------

# Ask the human to confirm before the first call of a batch goes out.
#
# On by default. A batch is a fan-out of real voice calls to real people and
# nothing recalls one once Hello.ai has dialled; a mis-parsed spreadsheet with a
# phone column shifted by one dials a hundred strangers. The confirmation costs
# one turn and is the only point in the pipeline where a mistake is still free.
#
# No longer read by the orchestrator, and kept only so an existing .env does
# not break. The gate is now unconditional and stronger: the batch stops after
# analysis and nothing is dialled until the human asks for outreach in their
# own words. There is no setting that turns that off.
CONFIRM_BEFORE_CALLS = os.environ.get('LODESTAR_CONFIRM_BEFORE_CALLS', '1') == '1'

# How many times a single lead may be dialled in total, first attempt included.
#
# The retry rule — "retry anything unattempted" — has no natural end: a number
# that is never picked up is unattempted after every attempt, so without a cap
# the orchestrator schedules retries until the conversation is abandoned. Past
# this count a lead is flagged for a human instead.
MAX_CALL_ATTEMPTS = int(os.environ.get('LODESTAR_MAX_CALL_ATTEMPTS', '3'))

# Leads handed to the analysis specialist in one call. Batches arrive as whole
# spreadsheets; a hundred rows in a single prompt is where recommendations start
# being dropped silently rather than returned.
#
# Small, and deliberately so. The binding limit is not the analysis — it is
# `record_analysis` on the way back, which carries the full profile, reasoning
# and pitch notes for every lead in the chunk as a single function call. Eight
# leads was already enough to make Gemini emit a MALFORMED_FUNCTION_CALL, so
# the chunk that produced them has to stay well under that. Raise it only with
# a batch in front of you to prove it still records.
ANALYSIS_CHUNK_SIZE = int(os.environ.get('LODESTAR_ANALYSIS_CHUNK_SIZE', '3'))

# Output-token ceiling for every agent in the package.
#
# The analysis reply and the `record_analysis` call that follows it are both
# long — a full profile, reasoning and three pitch notes per lead — and a
# function call truncated by the ceiling does not arrive as a short answer, it
# arrives as MALFORMED_FUNCTION_CALL and the chunk is lost. Generous on
# purpose; unused tokens cost nothing.
MAX_OUTPUT_TOKENS = int(os.environ.get('LODESTAR_MAX_OUTPUT_TOKENS', '32768'))

# --- Hello.ai ---------------------------------------------------------------
#
# The voice platform the Outreach Agent dials through. With no base URL and key
# set, `trigger_hello_ai_call` refuses and reports every lead unattempted — it
# never simulates a call. That is deliberate: a stub that invents outcomes
# would have the ledger, and then the agency, believing people were spoken to.
HELLO_AI_BASE_URL = os.environ.get('HELLO_AI_BASE_URL', '').rstrip('/')
HELLO_AI_API_KEY = os.environ.get('HELLO_AI_API_KEY', '')

# The Hello.ai voice bot that places these calls, if the account has more than
# one. Left out of the payload when empty.
HELLO_AI_AGENT_ID = os.environ.get('HELLO_AI_AGENT_ID', '')

HELLO_AI_TIMEOUT_SECONDS = float(os.environ.get('HELLO_AI_TIMEOUT', '30'))

# Simulate the calls instead of placing them.
#
#   '1'   always mock, even with credentials set
#   '0'   never mock — unconfigured means refuse, nothing is invented
#   ''    (default) mock only while Hello.ai is unconfigured
#
# The default is what makes the pipeline demonstrable before Hello.ai hand over
# their API, and it stops being a mock by itself the moment real credentials
# land — there is no flag to remember to turn off. Every simulated result is
# marked `mock: true` and its detail is prefixed [MOCK] all the way through to
# the ledger, so a demo run can never be read as people having been called.
HELLO_AI_MOCK = os.environ.get('HELLO_AI_MOCK', '')


def mock_calls() -> bool:
    """Whether calls are simulated on this run."""
    if HELLO_AI_MOCK == '1':
        return True
    if HELLO_AI_MOCK == '0':
        return False
    return not (HELLO_AI_BASE_URL and HELLO_AI_API_KEY)


# --- underwriting thresholds -------------------------------------------------
#
# Every number the recommendation rules turn on, in one place. They come from
# `singapore_policy_guidelines.md`, which is the catalogue the Policy Analysis
# Agent is written against; change a threshold here and the agent's prompt
# moves with it, because the prompt interpolates these values rather than
# repeating them.
#
# If the agency moves a line, move it here — not in the prompt.

# Existing cover at or below which a lead is treated as having a protection
# gap. MediShield Life alone leaves B2/C ward coverage only, so this is what
# makes Integrated Shield the baseline recommendation.
LOW_EXISTING_COVER_SGD = float(
    os.environ.get('LODESTAR_LOW_EXISTING_COVER_SGD', '50000')
)

# Term Life to 65 is the budget protection play: high cover, low premium, for
# people whose liabilities have just jumped but whose income has not.
TERM_LIFE_MAX_INCOME_SGD = float(
    os.environ.get('LODESTAR_TERM_LIFE_MAX_INCOME_SGD', '60000')
)

# Investment-Linked needs both a long horizon and spare cash flow, so it is
# gated on age and income together.
ILP_MAX_AGE = int(os.environ.get('LODESTAR_ILP_MAX_AGE', '35'))
ILP_MIN_INCOME_SGD = float(os.environ.get('LODESTAR_ILP_MIN_INCOME_SGD', '80000'))

# CareShield Life pays ~S$600/month for severe disability, which does not cover
# a helper or a nursing facility here. The supplement is aimed at people close
# enough to needing it to care, with the income to fund it.
CARESHIELD_MIN_AGE = int(os.environ.get('LODESTAR_CARESHIELD_MIN_AGE', '40'))
CARESHIELD_MIN_INCOME_SGD = float(
    os.environ.get('LODESTAR_CARESHIELD_MIN_INCOME_SGD', '50000')
)

# Term Life to 65 is written for people still inside their working and
# mortgage-paying years.
TERM_LIFE_MAX_AGE = int(os.environ.get('LODESTAR_TERM_LIFE_MAX_AGE', '45'))

# Session-state key the batch ledger lives under. Namespaced so it cannot
# collide with anything a sub-agent writes.
BATCH_STATE_KEY = 'lodestar:batch'
