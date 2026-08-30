"""The Hello.ai client, and the two tools the Outreach Agent dials through.

RIGHT NOW THESE ARE MOCKED. Hello.ai have not handed over their API, so by
default — see `config.mock_calls` — the tools simulate the calls and place
none. Every simulated result carries `mock: true` and a `[MOCK]` prefix that
survives into the ledger and the final report, so a demo cannot be mistaken for
outreach that happened. Setting HELLO_AI_BASE_URL and HELLO_AI_API_KEY switches
to the real path on its own; there is no flag to remember to turn off.

Two calls, because placing a voice call is not something an HTTP request waits
for. `trigger_hello_ai_call` hands Hello.ai the leads and gets back a call id
per lead; `check_call_results` asks what became of those ids. A call still
ringing when we look is reported `in_progress` — never `unattempted`, which
would send someone a second call while the first one is live.

UNVERIFIED AGAINST THE REAL API. The request and response shapes below are a
reasonable guess at a voice platform's API and nothing more — no Hello.ai
documentation was available when this was written. `_payload` and `_normalise`
are the only two places any of it is decided; correct them there once the docs
land and the agents above need no changes.

With no base URL and key configured, both tools refuse and say so. They never
invent an outcome.
"""

import hashlib
import logging

from google.adk.tools.tool_context import ToolContext

from . import config

logger = logging.getLogger(__name__)

# What Hello.ai's own statuses mean in the ledger's vocabulary. Anything not
# listed here is passed through untouched, so an unrecognised status reaches
# `record_outreach_results`, gets flagged, and is looked at by a human — rather
# than being guessed into "contacted".
_STATUS_MAP = {
    'success': 'contacted',
    'completed': 'contacted',
    'answered': 'contacted',
    'connected': 'contacted',
    'unattempted': 'unattempted',
    'not_attempted': 'unattempted',
    'skipped': 'unattempted',
    'rejected': 'unattempted',
    'voicemail': 'failed',
    'no_answer': 'failed',
    'busy': 'failed',
    'failed': 'failed',
    'invalid_number': 'failed',
    'queued': 'in_progress',
    'ringing': 'in_progress',
    'in_progress': 'in_progress',
    'dialing': 'in_progress',
}


# --- the mock ---------------------------------------------------------------
#
# Stands in for Hello.ai until they hand over the API. It places no calls and
# says so in every field it returns: `mock` is true and `detail` opens [MOCK].
# The ledger keeps both, so a batch run this way reports as a simulation rather
# than as an afternoon of outreach.
#
# Outcomes are drawn from the lead id, not at random, so the same demo twice
# tells the same story — and they improve with each attempt, so a retry loop
# resolves instead of grinding. Roughly: three in five reached first time,
# rising on retry.
_MOCK_OUTCOMES = [
    ('contacted', 'spoke to the lead, interested in a callback'),
    ('contacted', 'spoke to the lead, asked for a brochure'),
    ('contacted', 'brief call, wants to think it over'),
    ('failed', 'rang out, no answer'),
    ('failed', 'went to voicemail'),
    ('in_progress', 'call placed, still connecting'),
    ('unattempted', 'number rejected by the dialler'),
    ('failed', 'line busy'),
]


def _mock_result(lead: dict, attempt: int) -> dict:
    lead_id = str(lead.get('lead_id') or '')
    seed = hashlib.sha256(f'{lead_id}:{attempt}'.encode()).digest()[0]

    if not str(lead.get('phone') or '').strip():
        # No number on the row. The mock will not pretend to have dialled it —
        # this is the one failure a real run would hit too, and hiding it in a
        # demo is how it reaches production unnoticed.
        return {
            'lead_id': lead_id,
            'outcome': 'unattempted',
            'detail': '[MOCK] no phone number on this lead, nothing to dial',
            'call_id': '',
            'attempts': 0,
            'mock': True,
        }

    # Later attempts land better, so a batch converges.
    index = seed % len(_MOCK_OUTCOMES)
    if attempt >= 2 and index >= 3:
        index = seed % 3
    outcome, detail = _MOCK_OUTCOMES[index]
    return {
        'lead_id': lead_id,
        'outcome': outcome,
        'detail': f'[MOCK] {detail}',
        'call_id': f'mock-{lead_id}-{attempt}',
        'attempts': 1,
        'mock': True,
    }


def _mock_batch(leads: list[dict]) -> dict:
    results = []
    for lead in leads:
        try:
            attempt = int(lead.get('attempts', 0)) + 1
        except (TypeError, ValueError):
            attempt = 1
        results.append(_mock_result(lead or {}, attempt))
    logger.warning('MOCK: simulated %d calls, none were placed', len(results))
    return {
        'status': 'success',
        'mock': True,
        'note': (
            'SIMULATED. No calls were placed and nobody was contacted. '
            'Hello.ai is not wired up on this run.'
        ),
        'results': results,
    }


def _configured() -> bool:
    return bool(config.HELLO_AI_BASE_URL and config.HELLO_AI_API_KEY)


def _not_configured(leads: list[dict]) -> dict:
    """Every lead reported unattempted, with the reason said out loud.

    Nothing was dialled, so `unattempted` is the truth and the leads stay
    retryable once the credentials are in place.
    """
    reason = (
        'Hello.ai is not configured — set HELLO_AI_BASE_URL and '
        'HELLO_AI_API_KEY. No call was placed.'
    )
    logger.error('trigger_hello_ai_call: %s', reason)
    return {
        'status': 'error',
        'error_message': reason,
        'results': [
            {
                'lead_id': str((lead or {}).get('lead_id') or ''),
                'outcome': 'unattempted',
                'detail': reason,
                'attempts': 0,
            }
            for lead in leads or []
        ],
    }


def _payload(lead: dict) -> dict:
    """One lead as Hello.ai wants it. CONFIRM AGAINST THE REAL API."""
    body = {
        'lead_id': str(lead.get('lead_id') or ''),
        'customer_name': lead.get('name') or '',
        'phone_number': str(lead.get('phone') or ''),
        # What the voice bot is calling about, and what to say. Passed through
        # exactly as the Policy Analysis Agent wrote them.
        'recommended_policy': lead.get('policy') or '',
        'pitch_notes': lead.get('pitch_notes') or '',
        'context': lead.get('profile') or {},
    }
    if config.HELLO_AI_AGENT_ID:
        body['agent_id'] = config.HELLO_AI_AGENT_ID
    return body


def _normalise(record: dict) -> dict:
    """One Hello.ai result as the ledger wants it. CONFIRM AGAINST THE REAL API."""
    raw = str(
        record.get('call_status') or record.get('status') or ''
    ).strip().lower()
    return {
        'lead_id': str(record.get('lead_id') or ''),
        'outcome': _STATUS_MAP.get(raw, raw or 'unknown'),
        'detail': str(
            record.get('detail') or record.get('summary')
            or record.get('message') or ''
        ).strip(),
        'call_id': str(record.get('call_id') or record.get('id') or ''),
        'attempts': 1,
        'hello_ai_status': raw,
    }


def _post(path: str, body: dict) -> dict:
    import requests  # imported here so the package loads without it installed

    response = requests.post(
        f'{config.HELLO_AI_BASE_URL}{path}',
        json=body,
        headers={
            'Authorization': f'Bearer {config.HELLO_AI_API_KEY}',
            'Content-Type': 'application/json',
        },
        timeout=config.HELLO_AI_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()


def trigger_hello_ai_call(leads: list[dict], tool_context: ToolContext) -> dict:
    """Place a voice call for each lead through Hello.ai.

    Args:
        leads: The leads to call, as `leads_ready_to_call` gave them — each
            with `lead_id`, `name`, `phone`, `policy`, `pitch_notes` and
            `profile`. Pass them through unchanged; `pitch_notes` is what the
            voice bot says.

    Returns:
        `results`: one record per lead, with `lead_id`, `outcome`, `detail` and
        `call_id`. An outcome of `in_progress` means the call is live and its
        result is not known yet — poll it with `check_call_results`.
    """
    if not leads:
        return {'status': 'error',
                'error_message': 'No leads given, so nothing was called.',
                'results': []}
    if config.mock_calls():
        return _mock_batch(leads)
    if not _configured():
        return _not_configured(leads)

    try:
        answer = _post('/calls/batch', {'calls': [_payload(l) for l in leads]})
    except Exception as exc:
        # The dispatch itself failed, so nothing was placed. `unattempted`
        # keeps every lead retryable, which is what an unsent batch deserves.
        logger.exception('Hello.ai dispatch failed')
        detail = f'Hello.ai dispatch failed: {exc}'
        return {
            'status': 'error',
            'error_message': detail,
            'results': [
                {'lead_id': str(l.get('lead_id') or ''),
                 'outcome': 'unattempted', 'detail': detail, 'attempts': 0}
                for l in leads
            ],
        }

    records = answer.get('calls') or answer.get('results') or []
    results = [_normalise(r) for r in records if isinstance(r, dict)]

    # A lead Hello.ai said nothing about. Silence is not a result: left out of
    # the report it would look reached to nobody and unreached to nobody.
    answered = {r['lead_id'] for r in results}
    for lead in leads:
        lead_id = str(lead.get('lead_id') or '')
        if lead_id not in answered:
            results.append({
                'lead_id': lead_id,
                'outcome': 'unattempted',
                'detail': 'Hello.ai returned no result for this lead.',
                'call_id': '',
                'attempts': 0,
            })

    logger.info('dispatched %d calls, %d results', len(leads), len(results))
    return {'status': 'success', 'results': results}


def check_call_results(call_ids: list[str], tool_context: ToolContext) -> dict:
    """Ask Hello.ai what became of calls that were still live.

    Args:
        call_ids: The `call_id` values from `trigger_hello_ai_call` for leads
            reported `in_progress`.

    Returns:
        `results` in the same shape as `trigger_hello_ai_call`. A call still
        running comes back `in_progress` again — report it as such rather than
        waiting on it.
    """
    if not call_ids:
        return {'status': 'error',
                'error_message': 'No call ids given.', 'results': []}
    if config.mock_calls():
        # A simulated call that was still connecting has now connected. It
        # costs no attempt, exactly as a real poll does.
        return {
            'status': 'success',
            'mock': True,
            'note': 'SIMULATED. No calls were placed and nobody was contacted.',
            'results': [
                {'lead_id': str(c).split('-')[1] if '-' in str(c) else '',
                 'outcome': 'contacted',
                 'detail': '[MOCK] call completed',
                 'call_id': str(c), 'attempts': 0, 'mock': True}
                for c in call_ids
            ],
        }
    if not _configured():
        return {
            'status': 'error',
            'error_message': (
                'Hello.ai is not configured, so no result can be read.'
            ),
            'results': [],
        }
    try:
        answer = _post('/calls/status', {'call_ids': [str(c) for c in call_ids]})
    except Exception as exc:
        logger.exception('Hello.ai status check failed')
        return {'status': 'error',
                'error_message': f'Hello.ai status check failed: {exc}',
                'results': []}

    records = answer.get('calls') or answer.get('results') or []
    results = [_normalise(r) for r in records if isinstance(r, dict)]
    # A poll spends no new attempt — it is the same call being looked at again.
    for result in results:
        result['attempts'] = 0
    return {'status': 'success', 'results': results}
