"""Establishing which faculty member is asking, and getting a Sethu token.

How identity actually arrives, measured rather than assumed:

Gemini Enterprise runs Google OAuth once, then forwards the caller's **OAuth
access token** — opaque, not a signed JWT. On the Agent Engine path it arrives
in the request *body*, and `vertexai/agent_engines/templates/adk.py` writes it
into session state keyed by the authorization id:

    session_state[auth_id] = auth.access_token

so it is readable as `tool_context.state[GE_AUTHORIZATION_ID]`.

Two things follow, both of which cost other people real debugging time:

* There is no Google ID token to be had. The ID-token flow Sethu's original
  guide describes is unreachable from a GE agent; the exchange takes
  `googleAccessToken`.
* None of this arrives until the agent's `authorizationConfig` is set in
  Gemini Enterprise. An unconfigured agent receives no identity at all, which
  looks exactly like the platform not supporting it.

Sethu tokens are cached in ADK's `user:`-prefixed state, which persists across
sessions, so a returning professor reuses their token instead of minting a new
row on every conversation.
"""

import base64
import json
from datetime import datetime, timedelta, timezone

from google.adk.tools import ToolContext

from . import config, sethu_client
from .sethu_client import NoIdentityError, NotRegisteredError, SethuError

_NAME_KEY = 'user:sethu_name'
_TOKEN_KEY = 'user:sethu_token'
_TOKEN_ID_KEY = 'user:sethu_token_id'
_EXPIRES_KEY = 'user:sethu_token_expires_at'
_USER_ID_KEY = 'user:sethu_user_id'
_TENANT_KEY = 'user:sethu_tenant_id'
_ROLE_KEY = 'user:sethu_role'

# Google OAuth access tokens are opaque and start with this.
_ACCESS_TOKEN_PREFIX = 'ya29.'

_ACCEPTED_ROLES = ('FACULTY', 'COLLEGE_ADMIN')


def _claims(token: str) -> dict:
    """A JWT's payload, unverified. Only used to label tokens, never to trust."""
    try:
        payload = token.split('.')[1]
        return json.loads(base64.urlsafe_b64decode(payload + '=' * (-len(payload) % 4)))
    except (IndexError, ValueError):
        return {}


def state_items(tool_context: ToolContext) -> dict:
    """Everything in session state, however this ADK version exposes it."""
    state = tool_context.state
    for attr in ('to_dict', 'items'):
        getter = getattr(state, attr, None)
        if callable(getter):
            try:
                return dict(getter())
            except (TypeError, ValueError):
                continue
    return {}


def looks_like_access_token(value) -> bool:
    return isinstance(value, str) and value.startswith(_ACCESS_TOKEN_PREFIX)


def _google_access_token(tool_context: ToolContext) -> str:
    """The caller's Google OAuth access token, as forwarded by GE."""
    token = tool_context.state.get(config.GE_AUTHORIZATION_ID)
    if token:
        return token

    # The authorization id is configurable and easy to get wrong, so fall back
    # to recognising the token by its shape rather than failing on a typo.
    for value in state_items(tool_context).values():
        if looks_like_access_token(value):
            return value

    # On the A2A runtime there is no platform template writing the token into
    # session state; it arrives as an Authorization header and the identity
    # interceptor publishes it for the duration of the request.
    from . import identity

    token = identity.current_access_token()
    if token:
        return token

    if config.DEV_GOOGLE_ACCESS_TOKEN:
        return config.DEV_GOOGLE_ACCESS_TOKEN

    raise NoIdentityError(
        'Gemini Enterprise did not forward a sign-in for this session, so '
        'Sethu cannot tell who is asking.'
    )


def has_email_claim(token: str | None) -> bool:
    """Whether a Sethu token carries the `email` claim.

    `/faculty/sections` requires it and 403s without it, while every other
    `/faculty/*` route accepts a token that lacks it (measured 2026-08-03). A
    token minted before Sethu started including the claim stays cached for its
    full 30 days and keeps failing, because a 403 does not invalidate anything
    — only a 401 does. So this is checked before reusing a cached token.
    """
    return bool(token) and bool(_claims(token).get('email'))


def _is_usable(expires_at) -> bool:
    """Whether a token is worth trying.

    A missing expiry is not treated as expired — a dead token surfaces as a
    401, which `invalidate` then clears.
    """
    if not expires_at:
        return True
    try:
        expiry = datetime.fromisoformat(str(expires_at).replace('Z', '+00:00'))
    except ValueError:
        return True
    margin = timedelta(days=config.TOKEN_REFRESH_MARGIN_DAYS)
    return expiry - margin > datetime.now(timezone.utc)


def _store(tool_context: ToolContext, data: dict) -> dict:
    state = tool_context.state
    state[_TOKEN_KEY] = data['token']
    state[_TOKEN_ID_KEY] = data.get('tokenId')
    state[_EXPIRES_KEY] = data.get('expiresAt')
    state[_USER_ID_KEY] = data.get('userId')
    state[_TENANT_KEY] = data.get('tenantId')
    state[_ROLE_KEY] = data.get('role')
    return data


def invalidate(tool_context: ToolContext) -> None:
    """Drop the cached token so the next call re-exchanges."""
    tool_context.state[_TOKEN_KEY] = None
    tool_context.state[_EXPIRES_KEY] = None


def _dev_session():
    """A session from a hand-supplied Sethu token. Never on a deployment."""
    token = config.DEV_AGENT_TOKEN
    if not token:
        return None
    claims = _claims(token)
    return {
        'token': token,
        'userId': claims.get('sub'),
        'tenantId': claims.get('tenantId'),
        'role': claims.get('role'),
    }


def display_name(ctx) -> str | None:
    """The signed-in professor's name, if it has been resolved. No network."""
    return ctx.state.get(_NAME_KEY)


def first_name(name: str | None) -> str | None:
    return name.split()[0] if name else None


def resolve_identity(ctx) -> str | None:
    """Cache the caller's name from Sethu. Best effort — never raises.

    Runs before each turn, so it must stay cheap: once the name is cached it
    does nothing, and with no forwarded token it fails locally without a
    network call.
    """
    cached = ctx.state.get(_NAME_KEY)
    if cached:
        return cached
    try:
        session = get_session(ctx)
        me = sethu_client.get_me(session['token'])
    except SethuError:
        return None
    name = (me or {}).get('name')
    if name:
        ctx.state[_NAME_KEY] = name
    return name


def get_session(tool_context: ToolContext) -> dict:
    """Return {token, userId, tenantId, role} for the signed-in faculty member.

    Uses the token cached in `user:` state while it is still good; otherwise
    exchanges the caller's Google access token for a fresh one.

    There is deliberately no "reuse a token Sethu already minted" step.
    `GET /auth/agent-tokens` returns metadata only and never the token string
    (measured 2026-08-03), so a previously minted token cannot be recovered —
    only re-minted. The cost is a new token row whenever the cache is cold.
    """
    dev = _dev_session()
    if dev:
        return dev

    state = tool_context.state

    cached = state.get(_TOKEN_KEY)
    if cached and _is_usable(state.get(_EXPIRES_KEY)) and has_email_claim(cached):
        return {
            'token': cached,
            'userId': state.get(_USER_ID_KEY),
            'tenantId': state.get(_TENANT_KEY),
            'role': state.get(_ROLE_KEY),
        }

    data = sethu_client.exchange_google_access_token(
        _google_access_token(tool_context)
    )
    if not data or not data.get('token'):
        raise SethuError('Sethu did not return an agent token.')

    role = data.get('role')
    if role and role not in _ACCEPTED_ROLES:
        raise NotRegisteredError(
            f'This Sethu account has the {role} role, not FACULTY, so it '
            'cannot send agents to sections.'
        )

    return _store(tool_context, data)
