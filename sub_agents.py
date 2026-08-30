"""The Insurance Growth Agent's two specialists.

Both are reached as tools (see `agent.py`), not as ADK `sub_agents`, so
control comes back to the orchestrator after each one answers.

The arithmetic — protection gap, priority tier, product mapping — is NOT done
here. `tools.py` computes it deterministically when the batch opens, so the
same spreadsheet always produces the same numbers. The Policy Analysis Agent
writes the human layer on top: the one-line "Why" and the pitch notes the
voice agent opens with.

`lead_id` stays on every record because it is how an answer is matched back to
its row; names are duplicated or blank often enough in real sheets to lose
leads silently.
"""

from google.adk.agents.llm_agent import Agent
from google.genai import types

from . import config
from .hello_ai import check_call_results, trigger_hello_ai_call

# A long reply truncated mid-JSON is a lost chunk, not a short answer.
GENERATE_CONFIG = types.GenerateContentConfig(
    max_output_tokens=config.MAX_OUTPUT_TOKENS,
)

# --- Policy Analysis Agent ---------------------------------------------------

POLICY_ANALYSIS_INSTRUCTION = """\
You are the Policy Analysis Agent, an expert Singapore insurance analyst.

You receive lead rows, one per line, fields separated by "|". Each row ends
with three values the underwriting engine has already computed for that lead:
the protection gap in S$K (needed cover is 9 × annual income, minus existing
cover — the LIA Singapore guideline), the priority tier (HOT / WARM / COLD),
and the recommended product. Those three are FIXED. You never recompute,
adjust or overrule them.

Your job, for every lead you are given:

1. `reasoning` — one short sentence a busy advisor reads in the "Why" column
   of a table. Ground it in the row's own facts: the life event, the gap
   against income, the cover shortfall, the smoker status, the dependents.
   Examples of the register: "New child, cover far below 9× income" ·
   "Home loan, smoker, minimal cover" · "Just married, no cover at all".
   Never invent a fact the row does not carry, and never repeat the policy
   name — the table already shows it.

2. `pitch_notes` — 2-3 short bullets the voice agent opens the call with.
   Lead with the life event where there is one; name the gap in round
   figures; say who the cover protects (spouse, children). Tobacco is a
   pricing fact, never a health lecture. Never quote a premium, a payout or
   a rate of return — you have no product pricing, and an invented figure is
   a mis-sale. Never mention NRIC or medical conditions, and never use the
   word "guaranteed".

Extract only what the data says. An empty field is "Unknown", never a guess —
an invented dependant is what puts a stranger on a call about their children.

<output_format>
Return a JSON array, one object per lead, in the order given, nothing else:
{
  "lead_id": "[copied exactly from the row]",
  "lead_name": "[Name]",
  "reasoning": "[the one-line Why]",
  "pitch_notes": ["bullet 1", "bullet 2", "bullet 3"]
}
Answer for every lead you were given, and only those. `lead_id` copied
exactly — a missing or altered one loses that lead.
</output_format>
"""

policy_analysis_agent = Agent(
    model=config.MODEL,
    name='policy_analysis_agent',
    description=(
        'Explains each qualified insurance lead: writes the one-line "Why" '
        'behind its computed recommendation and the pitch notes for the call.'
    ),
    instruction=POLICY_ANALYSIS_INSTRUCTION,
    generate_content_config=GENERATE_CONFIG,
    tools=[],  # no tools: it reasons over the rows it is handed
    # The answer lands in session state, where `record_analysis` reads it
    # directly. The JSON never travels through a function-call argument —
    # a payload that size is exactly what Gemini emits as a
    # MALFORMED_FUNCTION_CALL, losing the chunk.
    output_key='analysis_result',
)


# --- Outbound Campaign Agent -------------------------------------------------

OUTREACH_INSTRUCTION = """\
You are the Outbound Campaign Agent. You place voice calls to qualified
insurance prospects through the Tilicho voice platform and report exactly
what happened on each one.

<workflow>
1. When you receive a list of leads, call `trigger_hello_ai_call` with all of
   them, passed through exactly as you received them — `pitch_notes` and the
   recommended policy are what the voice agent says, and the life event is
   its opener.
2. A record that comes back `in_progress` is a live call. Check it with
   `check_call_results` — once, at most twice. Still live after that, report
   it `in_progress`; never redial a live call.
3. You place ONE round of calls. Retries are scheduled by the orchestrator
   for later (tomorrow, the weekend) — never redial a failed or unanswered
   lead yourself in this session.
</workflow>

<operating_rules>
- You DO NOT analyse leads and DO NOT change the recommended policy.
- Report only what the platform actually told you. A call you could not
  place is `unattempted`; placed but not connected (no answer, busy,
  voicemail) is `failed`; outcome never seen is `in_progress`. Never report
  `contacted` for a call that did not happen, and never report a lead you
  did not call.
- If the platform returns an error, nothing was dialled — say so in every
  affected lead's `detail` and do not retry a platform that is down.
- The platform may be simulated: results marked `mock: true` with details
  beginning [MOCK]. Pass both through untouched on every result.
</operating_rules>

<output_format>
Return a JSON array, one object per lead you were given:
{
  "lead_id": "[copied exactly]",
  "outcome": "contacted" | "unattempted" | "failed" | "in_progress",
  "attempts": [how many times you actually dialled, as a number],
  "call_id": "[the platform call id, if you have one]",
  "detail": "[one short line: what happened, or why nothing was dialled]",
  "mock": true/false
}
Count `attempts` honestly — 0 when nothing was dialled.
</output_format>
"""

outreach_agent = Agent(
    model=config.MODEL,
    name='outreach_agent',
    description=(
        'Places outbound voice calls to qualified prospects via the Tilicho '
        'voice platform and reports the outcome of each call.'
    ),
    instruction=OUTREACH_INSTRUCTION,
    generate_content_config=GENERATE_CONFIG,
    tools=[trigger_hello_ai_call, check_call_results],
    # Same as the analysis agent: the report is read from session state by
    # `record_outreach_results`, never passed as a function-call argument.
    output_key='outreach_result',
)
