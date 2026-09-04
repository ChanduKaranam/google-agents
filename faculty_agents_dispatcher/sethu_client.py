"""HTTP client for the Sethu Faculty API.

Two families of endpoints, with different credentials:

  /auth/agent-tokens/*   header: X-Agent-Secret       (server-to-server)
  /faculty/*             header: Authorization: Bearer (per-person agent token)

Built against sethu_openapi.json ("Sethu Faculty API 1.0.0"), with the token
reuse/revocation endpoints from the Agentic Team Guide, which the OpenAPI
document does not cover.
"""

import logging
from urllib.parse import quote

import requests

from . import config

logger = logging.getLogger(__name__)


class SethuError(RuntimeError):
    """Sethu was unreachable, or returned an error we cannot act on."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        request_id: str | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        # Sethu returns meta.requestId on every response; their team can trace
        # it, so it is worth carrying on every failure.
        self.request_id = request_id


class NoIdentityError(SethuError):
    """We could not establish who is asking. Retrying cannot change that."""


class NotRegisteredError(SethuError):
    """The caller is authenticated but is not faculty Sethu will act for."""


def _unwrap(payload):
    """Sethu wraps successful responses in {"data": ...}."""
    if isinstance(payload, dict) and 'data' in payload:
        return payload['data']
    return payload


def _request_id(response) -> str | None:
    try:
        return (response.json().get('meta') or {}).get('requestId')
    except (ValueError, AttributeError):
        return None


def _request(method: str, path: str, *, headers: dict, timeout=None, **kwargs):
    if not config.SETHU_API_BASE_URL:
        raise SethuError('SETHU_API_BASE_URL is not set.')

    url = f'{config.SETHU_API_BASE_URL}{path}'

    # One retry on a transport failure — the dev API sleeps on Render and the
    # waking request times out. A real answer (401/403/404) is never retried;
    # retrying cannot change it.
    #
    # But a read timeout is NOT proof the request was not processed, so a retry
    # is only safe when repeating the call is harmless: a GET, or a write
    # carrying an Idempotency-Key for Sethu to deduplicate on. Without that
    # rule this retried `POST /notify` — messaging a section twice — and
    # `POST /faculty/agents`, which would create a second permanent agent
    # record that Sethu has no way to delete.
    safe_to_repeat = (
        method.upper() == 'GET'
        or any(k.lower() == 'idempotency-key' for k in headers)
    )
    attempts = 2 if safe_to_repeat else 1

    last_exc = None
    for _ in range(attempts):
        try:
            response = requests.request(
                method,
                url,
                headers=headers,
                timeout=timeout or config.REQUEST_TIMEOUT_SECONDS,
                **kwargs,
            )
            break
        except requests.RequestException as exc:
            last_exc = exc
    else:
        raise SethuError(
            f'Could not reach Sethu: {last_exc}'
        ) from last_exc

    if response.status_code >= 400:
        raise _classify_error(path, response)

    if not response.content:
        return None
    try:
        return _unwrap(response.json())
    except ValueError as exc:
        raise SethuError('Sethu returned a non-JSON response.') from exc


def _classify_error(path: str, response) -> SethuError:
    """Turn a Sethu error into the right class, because the answer differs.

    The distinction that matters to a professor: we do not know who you are
    (nothing they can do), versus we know you but Sethu will not act for you
    (someone must register them), versus Sethu is down (try again).
    """
    code = response.status_code
    request_id = _request_id(response)

    if path.startswith('/auth/agent-tokens/exchange'):
        if code == 401:
            return NoIdentityError(
                'Sethu rejected the sign-in — the access token has expired, or '
                'the agent secret is missing or wrong.',
                code,
                request_id,
            )
        if code == 404:
            return NotRegisteredError(
                'This Google account has no Sethu record, so it is not '
                'registered as faculty.',
                code,
                request_id,
            )
        if code == 400:
            return NotRegisteredError(
                'This Sethu account exists but is not active yet.',
                code,
                request_id,
            )
    elif code in (401, 403):
        return NotRegisteredError(
            f'Sethu refused this account access to {path}. The account may not '
            'have the role that endpoint requires.',
            code,
            request_id,
        )

    if code == 404:
        return SethuError('Sethu could not find that record.', code, request_id)
    return SethuError(
        f'Sethu returned {code}: {response.text[:300]}', code, request_id
    )


# --- Agent-token endpoints (X-Agent-Secret) --------------------------------


def _secret_headers() -> dict:
    headers = {'Content-Type': 'application/json'}
    if config.AGENT_AUTH_SECRET:
        headers['X-Agent-Secret'] = config.AGENT_AUTH_SECRET
    return headers


def exchange_google_access_token(google_access_token: str) -> dict:
    """Trade the caller's Google OAuth access token for a Sethu agent token.

    An access token, not an ID token: Gemini Enterprise forwards an opaque
    OAuth token and never a signed OIDC one, so the ID-token path Sethu's
    original guide describes is unreachable from a GE agent.

    Returns {token, tokenId, expiresAt, userId, role, tenantId}.
    """
    return _request(
        'POST',
        '/auth/agent-tokens/exchange',
        headers=_secret_headers(),
        json={'googleAccessToken': google_access_token},
    )


def list_agent_tokens(user_id: str) -> list:
    """List a user's agent token records, newest first.

    Metadata only — measured 2026-08-03, entries carry `id`, `userId`, `role`,
    `tenantId`, `label`, `createdAt`, `expiresAt` and `revoked`, and never the
    token string itself. So this cannot be used to reuse a live token; it is
    good for auditing and for finding an `id` to revoke.

    The payload nests one level deeper than the rest of the API:
    `{"data": {"tokens": [...]}}`.

    Documented in the team guide; absent from the OpenAPI document.
    """
    payload = _request(
        'GET',
        f'/auth/agent-tokens?userId={user_id}',
        headers=_secret_headers(),
    )
    if isinstance(payload, dict):
        payload = payload.get('tokens')
    return payload or []


def revoke_agent_token(token_id: str) -> None:
    """Revoke a token immediately."""
    _request(
        'POST',
        f'/auth/agent-tokens/{token_id}/revoke',
        headers=_secret_headers(),
    )


# --- Faculty endpoints (Bearer agent token) --------------------------------


def _bearer_headers(token: str) -> dict:
    return {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}


def get_me(token: str) -> dict:
    """Who Sethu thinks this token belongs to. The best smoke test there is."""
    return _request('GET', '/auth/me', headers=_bearer_headers(token)) or {}


def list_faculty_sections(token: str) -> list:
    """List the sections that exist in this college.

    Not the caller's own sections — professors are not assigned sections, and
    any of them can send an agent college-wide. Measured 2026-08-03: 55
    sections across 7 departments, while the caller's own department is CSE.
    This is the roster to validate a professor's stated section against.

    Like `/auth/agent-tokens`, the payload nests one level deeper than the rest
    of the API: `{"data": {"department": "CSE", "sections": [...]}}`. The
    caller's department is dropped here; only the roster is returned.

    Each entry is an object, not a string:

        {"department": "CSE", "year": 1, "section": "A",
         "label": "CSE · Year 1 · Sec A", "students": 1}

    `section` alone ("A") is ambiguous — it repeats across every department and
    year — so `label` is the only field that identifies a section on its own.

    Requires a token carrying an `email` claim. A token without one gets 403,
    which is what blocked this endpoint all morning.
    """
    return list_faculty_scope(token)[1]


def list_faculty_scope(token: str) -> tuple[str, list]:
    """The roster, plus the department Sethu resolved the caller to.

    Same call as `list_faculty_sections`; this one keeps the `department` the
    payload carries alongside the roster instead of dropping it. It is the only
    place the caller's own department is available — the progress and
    ambassador endpoints return it too, but return "" for an admin or
    non-roster email, which is exactly the case that needs telling apart.

    Returns ("", roster) when Sethu does not name a department.
    """
    payload = _request('GET', '/faculty/sections', headers=_bearer_headers(token))
    if isinstance(payload, dict):
        return (payload.get('department') or ''), (payload.get('sections') or [])
    return '', (payload or [])


def get_department_progress(token: str, department: str | None = None) -> dict:
    """Activation figures for the caller's department, plus every section.

    One call serves both the department dashboard and the leaderboard, which is
    the point of it: they are two readings of one dataset, and splitting them
    would let the two screens disagree about who is doing well.

    Returns `{"department", "activated", "total", "syncedAt", "sections": [...]}`
    where each section carries `label`, `ambassador` (None when it has none),
    `activated`, `total`, `rank` (1 = best) and `pooled`.

    `rank` and `pooled` are computed server-side and used as given. Ranking here
    as well would mean two implementations of the pooling rule, and the moment
    they drifted the two cards would contradict each other.

    Scoped to the caller's own department; an admin or non-roster email gets the
    whole college with `department: ""`. Needs a token with an `email` claim,
    like `/faculty/sections`, or it is a 403.

    `department` asks for a different one. Sethu decides the scope from the
    caller's email and is not documented as taking this parameter, so it may be
    ignored — which is why the caller must compare the `department` on the
    response against what it asked for rather than assuming it was honoured.
    An unknown query parameter is ignored, not rejected, so this is safe to
    send speculatively.
    """
    path = '/faculty/department-progress'
    if department:
        path += f'?department={quote(str(department))}'
    return _request('GET', path, headers=_bearer_headers(token)) or {}


def get_ambassadors(token: str) -> dict:
    """The department's ambassadors, worst-first, and the sections with none.

    Returns `{"department", "syncedAt", "ambassadors": [...],
    "sectionsWithoutAmbassador": [...]}`.

    `lastActivityAt` and `idleDays` are a PROXY: they describe the most recent
    student activation in that ambassador's cohort, not anything the ambassador
    did. Sethu has no per-ambassador action log. Anything built on these must
    say "no activation in their section", never "the ambassador did nothing" —
    the second is a claim about a named colleague that the data cannot support.

    The sections with no ambassador cannot be derived from the ambassador list,
    which is why they are returned alongside it.
    """
    return _request(
        'GET', '/faculty/ambassadors', headers=_bearer_headers(token)
    ) or {}


def trigger_agent_sync(token: str) -> dict:
    """Ask Sethu to re-read Gemini Enterprise now.

    Fire and forget. The sync enumerates every agent under the engine and can
    take minutes, so this returns as soon as Sethu accepts the request — the
    caller must not wait for the result or promise the professor a fresh list.

    Given a short timeout of its own: this runs on a greeting, and a professor
    saying hello should not sit watching a spinner because a background job is
    slow.
    """
    return _request(
        'POST',
        '/faculty/agents/sync',
        headers=_bearer_headers(token),
        timeout=config.SYNC_TRIGGER_TIMEOUT_SECONDS,
    ) or {}


def list_faculty_agents(token: str) -> list:
    """List the GE agents this faculty member owns."""
    return _request('GET', '/faculty/agents', headers=_bearer_headers(token)) or []


def publish_faculty_agent(
    token: str,
    ge_url: str,
    name: str,
    sections: list,
    semester: str = '',
    ge_agent_id: str = '',
) -> dict:
    """Publish a GE agent to sections. The only write path Sethu implements.

    Measured against the running API on 2026-08-03. Both the OpenAPI document
    and the team guide describe `{name, description, whoCanUse}` plus separate
    `claim` and `PUT .../sections` calls; none of that exists. One POST carries
    the share link and the sections together, and comes back `status: "live"`.

    `sections` is a list of section *names* as plain strings — a list of
    objects is rejected with "Expected string, received object".

    `semester` is REQUIRED by the API but carries no meaning: Sethu stores it as
    free text, nothing validates or reads it, live records hold "1", "2nd",
    "Sem 1" and null for the same concept, and the section roster has no
    semester dimension at all.

    Do not "clean this up" by omitting the field when empty — that was tried on
    2026-08-04 and Sethu rejects it with "semester is a required field", which
    surfaces to the professor as a failed publish. Send the placeholder.

    The placeholder is deliberately "NA" and not "1": a fabricated semester
    number would be indistinguishable from a real one on the record.

    Publishing does not message anyone. Only `notify_agent_sections` does.

    `ge_agent_id` is the Gemini Enterprise agent id, sent as `geAgentId`
    alongside the link. The id is already inside `geUrl`, but only as a path
    segment Sethu would have to parse, and the same GE agent published twice
    gives two records with no field tying them together. Sending it explicitly
    means Sethu can group sends of one agent without string-splitting a URL
    whose shape is Google's to change.

    Sethu does not store it yet — records read back on 2026-08-14 carry no such
    field — so today this is a field their API can start reading whenever they
    add it, not one that does anything. If their validator rejects the unknown
    key, the call is retried without it: publishing is the professor's whole
    task, and it must not fail over a field nobody consumes.
    """
    payload = {
        'geUrl': ge_url,
        'name': name,
        'sections': sections,
        'semester': semester or 'NA',
    }
    if not ge_agent_id:
        return _request(
            'POST', '/faculty/agents',
            headers=_bearer_headers(token), json=payload,
        )

    try:
        record = _request(
            'POST', '/faculty/agents',
            headers=_bearer_headers(token),
            json={**payload, 'geAgentId': ge_agent_id},
        )
    except SethuError as exc:
        # 400 is the only status a rejected field produces, and it is raised
        # before any record exists, so repeating the call is safe. Any other
        # failure is about the publish itself and must surface unchanged.
        if exc.status_code != 400:
            raise
        logger.warning(
            'Sethu rejected geAgentId (%s); publishing without it: %s',
            exc.status_code, exc,
        )
        return _request(
            'POST', '/faculty/agents',
            headers=_bearer_headers(token), json=payload,
        )

    logger.info(
        'published with geAgentId=%s; Sethu %s it back',
        ge_agent_id,
        'echoed' if (record or {}).get('geAgentId') else 'did not echo',
    )
    return record


def get_faculty_agent(token: str, agent_id: str) -> dict:
    """Fetch one agent record. There is no GET-by-id, so filter the list."""
    for agent in list_faculty_agents(token):
        if agent.get('id') == agent_id:
            return agent
    raise SethuError('Sethu no longer lists that agent.')


def notify_agent_sections(
    token: str, agent_id: str, idempotency_key: str = ''
) -> dict:
    """Fire the notification to the agent's assigned sections.

    `idempotency_key` is what makes this call safe to repeat. Sethu deduplicates
    on it, so a network retry, a re-click, or a professor trying again after a
    timeout reaches the same students once rather than twice. The caller must
    reuse the same key for what is conceptually one send — a fresh key each
    attempt would defeat the whole mechanism.

    Given a longer timeout than the rest of the API because it fans out real
    WhatsApp messages before answering.
    """
    headers = _bearer_headers(token)
    if idempotency_key:
        headers['Idempotency-Key'] = idempotency_key
    return _request(
        'POST',
        f'/faculty/agents/{agent_id}/notify',
        headers=headers,
        timeout=config.NOTIFY_TIMEOUT_SECONDS,
    )


def get_section_recipient(token: str, section: str) -> dict:
    """Recipient lookup for a section. Query param is `section`.

    Not used for counting: against dev this returns a single arbitrary name for
    any input, including sections that do not exist, so it cannot be trusted to
    size a send. Kept for when the real endpoint lands.
    """
    return _request(
        'GET',
        f'/faculty/section-recipient?section={quote(str(section))}',
        headers=_bearer_headers(token),
    ) or {}
