"""Whether a Gemini Enterprise agent is actually openable by a student.

An agent the professor can see is not necessarily an agent a student can open.
Two independent fields decide it, and the console sets them at different times:

    state  = ENABLED      published, rather than a private draft
    scope  = ALL_USERS    shared, rather than restricted to its creator

Publishing in the console sets ENABLED and, in the same write, resets scope
back to RESTRICTED — so an agent is routinely one of the two and not the
other. A link to an agent that fails either check renders for the student as
"this conversation is read-only as the agent used is no longer available".

We read this with the service account's own credentials, not the professor's:
their token carries `openid email profile` and cannot see Discovery Engine at
all. The runtime service account holds roles/editor, which includes
discoveryengine.agents.get, so no extra grant is needed.

Reads only. Nothing here writes to a professor's agent — see readiness().
"""

import logging
import threading
import time

import requests

from . import config

logger = logging.getLogger(__name__)

_API_ROOT = 'https://discoveryengine.googleapis.com/v1alpha'
_SCOPE = 'https://www.googleapis.com/auth/cloud-platform'

# Only ready agents are cached, and only briefly. A professor who is told
# "not shared yet" will go and fix it within the minute, and caching that
# answer would tell them it is still broken after they have fixed it. So a
# failure is always re-read, and success is cached just long enough to spare
# the second lookup between publishing and sending.
_CACHE_TTL_SECONDS = 45
_cache: dict = {}
_cache_lock = threading.Lock()

_credentials = None
_credentials_lock = threading.Lock()


def _token() -> str:
    """A service-account access token, refreshed when it has expired."""
    global _credentials
    with _credentials_lock:
        if _credentials is None:
            import google.auth
            _credentials, _ = google.auth.default(scopes=[_SCOPE])
        if not _credentials.valid:
            from google.auth.transport.requests import Request
            _credentials.refresh(Request())
        return _credentials.token


def _agent_url(agent_id: str) -> str:
    return (
        f'{_API_ROOT}/projects/{config.GE_PROJECT_ID}/locations/global'
        f'/collections/default_collection/engines/{config.GE_ENGINE_ID}'
        f'/assistants/default_assistant/agents/{agent_id}'
    )


def _fetch(agent_id: str) -> dict:
    response = requests.get(
        _agent_url(agent_id),
        headers={
            'Authorization': f'Bearer {_token()}',
            'X-Goog-User-Project': config.GE_PROJECT_ID,
        },
        timeout=config.GE_READINESS_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json() or {}


def readiness(agent_id: str) -> dict:
    """Report whether students could open this agent.

    Args:
        agent_id: The GE agent id — the trailing segment of a share link.

    Returns:
        A dict with:
          known    False when the check could not be run at all.
          ok       True when a student could open it. True when not known:
                   an unreachable Discovery Engine must not stop a professor
                   from teaching, so this fails open by design.
          pending  True when a share request is waiting for an administrator.
          state    'ENABLED' | 'PRIVATE' | ... , or '' when not known.
          scope    'ALL_USERS' | 'RESTRICTED' | ... , or '' when not known.
          name     The agent's display name, when the API returned one.
    """
    unknown = {'known': False, 'ok': True, 'state': '', 'scope': '',
               'pending': False, 'name': ''}

    if not config.GE_READINESS_CHECK:
        return unknown
    if not agent_id:
        # Not a Gemini Enterprise link. Nothing to check, and not our business
        # to reject it — Sethu takes arbitrary URLs.
        return unknown

    now = time.monotonic()
    with _cache_lock:
        hit = _cache.get(agent_id)
        if hit and hit[0] > now:
            return dict(hit[1])

    try:
        agent = _fetch(agent_id)
    except Exception as exc:  # noqa: BLE001 - never block a send on our check
        logger.warning('readiness check failed for agent %s: %s', agent_id, exc)
        return unknown

    state = agent.get('state') or ''
    scope = (agent.get('sharingConfig') or {}).get('scope') or ''
    # A share is not always applied when it is made. On an organisation that
    # requires approval it becomes an IAM proposal instead, the console shows
    # the agent as "In review", and nobody gains access until an administrator
    # approves it. Telling a professor to share it again would be wrong twice
    # over: they already did, and doing it again changes nothing.
    pending = bool(agent.get('hasActiveIamProposals'))
    result = {
        'known': True,
        # Both fields, again. Sharing in the console publishes the agent but
        # leaves scope RESTRICTED, and RESTRICTED does restrict: measured
        # 2026-08-25, mohanaravali holds a licence, was shared the agent, and
        # still got "no longer available" because no binding named her.
        #
        # Accepting ENABLED alone was a mistake in the other direction — it
        # let a professor send a link no student could open. What makes an
        # agent reachable is ALL_USERS, and since no professor can set that
        # from the UI, `make_available` sets it for them.
        'ok': state == 'ENABLED' and not pending and scope == 'ALL_USERS',
        'state': state,
        'scope': scope,
        'pending': pending,
        'name': agent.get('displayName') or '',
    }
    logger.info(
        'readiness: agent %s state=%s scope=%s pending=%s ok=%s',
        agent_id, state or '-', scope or '(unset)', pending, result['ok'],
    )

    if result['ok']:
        with _cache_lock:
            _cache[agent_id] = (now + _CACHE_TTL_SECONDS, dict(result))
    return result


# The ids of every agent in the current Gemini Enterprise app. Cached for a
# few minutes: it changes only when someone builds an agent, and it is read on
# every listing.
_IDS_TTL_SECONDS = 300
_ids_cache: tuple = (0.0, None)


def known_agent_ids() -> set | None:
    """Every agent id the current app holds, or None if we could not ask.

    None and an empty set mean different things, and the caller must not
    confuse them: None is "the question could not be answered", empty is "this
    app has no agents". Filtering a professor's list against None would hide
    all of it.
    """
    global _ids_cache
    if not config.GE_READINESS_CHECK:
        return None

    now = time.monotonic()
    expires, cached = _ids_cache
    if cached is not None and expires > now:
        return set(cached)

    url = (
        f'{_API_ROOT}/projects/{config.GE_PROJECT_ID}/locations/global'
        f'/collections/default_collection/engines/{config.GE_ENGINE_ID}'
        f'/assistants/default_assistant/agents'
    )
    ids: set = set()
    page = ''
    try:
        while True:
            response = requests.get(
                url,
                params={'pageSize': 100, 'pageToken': page} if page
                else {'pageSize': 100},
                headers={
                    'Authorization': f'Bearer {_token()}',
                    'X-Goog-User-Project': config.GE_PROJECT_ID,
                },
                timeout=config.GE_READINESS_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            body = response.json() or {}
            for agent in body.get('agents') or []:
                name = agent.get('name') or ''
                if name:
                    ids.add(name.rsplit('/', 1)[-1])
            page = body.get('nextPageToken') or ''
            if not page:
                break
    except Exception as exc:  # noqa: BLE001 - a listing must not fail on this
        logger.warning('could not list agents in the app: %s', exc)
        return None

    logger.info('app holds %d agents', len(ids))
    _ids_cache = (now + _IDS_TTL_SECONDS, set(ids))
    return ids


def make_available(agent_id: str) -> bool:
    """Open an already-published agent to everyone. True if it now is.

    The Share dialog in Gemini Enterprise offers "Add people" and nothing
    else — there is no organisation-wide option — so a professor cannot make
    an agent reachable by a class however carefully they follow instructions.
    Sharing names individuals; students are not individuals we can name.

    `sharingConfig.scope` is the field that does it, and unlike `state` it is
    writable. So the professor publishes the agent by sharing it once, and
    this widens it the moment they send it to their students.

    Only ever called on an ENABLED agent. On a private one the scope would
    change while the agent stayed unreachable, which would leave a professor
    with an agent that looks configured and is not.
    """
    url = _agent_url(agent_id)
    try:
        response = requests.patch(
            url,
            params={'updateMask': 'sharingConfig'},
            json={'sharingConfig': {'scope': 'ALL_USERS'}},
            headers={
                'Authorization': f'Bearer {_token()}',
                'X-Goog-User-Project': config.GE_PROJECT_ID,
                'Content-Type': 'application/json',
            },
            timeout=config.GE_READINESS_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except Exception as exc:  # noqa: BLE001 - the caller refuses the send
        logger.warning('could not open agent %s to all users: %s', agent_id, exc)
        return False

    scope = ((response.json() or {}).get('sharingConfig') or {}).get('scope')
    logger.info('opened agent %s to all users (scope=%s)', agent_id, scope)
    with _cache_lock:
        _cache.pop(agent_id, None)
    return scope == 'ALL_USERS'
