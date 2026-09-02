"""Who is asking, on the A2A runtime.

On Agent Engine the caller's OAuth token arrives in session state, written by
the platform template. There is no template here: Gemini Enterprise sends it as
an ordinary `Authorization: Bearer` header, and only once the GE registration
carries `authorizationConfig.agentAuthorization`. Without that field the header
is simply absent and every request looks anonymous.

The trust rules are not negotiable, because getting them wrong does not fail —
it silently serves one person's students to everybody:

  authorization                 accepted. GE sets it per signed-in user, and
                                Cloud Run's own IAM check rides on a different
                                header, so this one is the end user's.
  x-serverless-authorization    REFUSED. That is the Discovery Engine service
                                agent — byte-identical for every user.
                                Accepting it collapses everyone into one
                                identity.
  x-user-email and friends      REFUSED, always. Nothing strips them, so any
                                caller could assert someone else's identity.

The token is published on a ContextVar rather than written into session state:
the interceptor runs outside the agent, and a ContextVar is naturally scoped to
the request that set it even under concurrency.
"""

import contextvars
import logging

logger = logging.getLogger(__name__)

_ACCESS_TOKEN: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    'ge_access_token', default=None
)

# Headers that look like identity and are not. Refused loudly rather than
# ignored, so nobody later "fixes" the agent by trusting one.
_FORGEABLE = ('x-user-email', 'x-goog-authenticated-user-email', 'x-user-id')


def current_access_token() -> str | None:
    """The signed-in professor's Google OAuth token for this request."""
    return _ACCESS_TOKEN.get()


def _bearer(headers: dict) -> str | None:
    value = headers.get('authorization') or headers.get('Authorization')
    if not value:
        return None
    prefix, _, token = value.partition(' ')
    if prefix.lower() != 'bearer' or not token.strip():
        return None
    return token.strip()


def install():
    """An `ExecuteInterceptor.before_agent` hook that publishes the caller."""

    async def before_agent(context):
        headers = {}
        call_context = getattr(context, 'call_context', None)
        if call_context is not None:
            headers = (getattr(call_context, 'state', None) or {}).get(
                'headers'
            ) or {}
        headers = {str(k).lower(): v for k, v in headers.items()}

        for name in _FORGEABLE:
            if name in headers:
                logger.warning(
                    'Ignoring %s — this header is forgeable and is never used '
                    'to identify a caller.',
                    name,
                )

        token = _bearer(headers)
        if token:
            _ACCESS_TOKEN.set(token)
            logger.info(
                'End-user token received (%d chars) — identity available.',
                len(token),
            )
        else:
            _ACCESS_TOKEN.set(None)
            logger.info(
                'No end-user token on this request. Either GE has no '
                'authorizationConfig.agentAuthorization, or the caller is not '
                'signed in. Present headers: %s',
                sorted(headers),
            )
        return context

    return before_agent
