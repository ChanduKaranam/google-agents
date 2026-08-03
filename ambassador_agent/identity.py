"""Who is asking? Lifts the end user's Google token off the inbound request.

Gemini Enterprise forwards the signed-in ambassador's OAuth access token in the
`Authorization` header — but only once the agent's GE registration carries
`authorizationConfig.agentAuthorization` pointing at an authorization resource.
Without that, the header is simply absent (measured 2026-07-28: GE sent no
end-user identity at all), and the agent falls back to whatever
`sethu.enabled()` allows.

The header reaches us because the A2A server copies every inbound header into
`call_context.state['headers']` (`a2a/server/apps/jsonrpc/jsonrpc_app.py:153`),
and ADK exposes a `before_agent` interceptor that runs with the RequestContext
in hand (`a2a/executor/a2a_agent_executor.py:151`).

SECURITY -- what is and is not trusted here:

  * `authorization` is accepted. Gemini Enterprise sets it, and Cloud Run's
    own IAM check rides on a separate header, so GE is free to use this one for
    the user.
  * `x-serverless-authorization` is REFUSED. It is the Discovery Engine service
    agent and is byte-identical for every student — treating it as identity
    would collapse the whole college into one person's data.
  * A header like `x-user-email` is REFUSED and always will be. No proxy strips
    it, so any caller could assert someone else's identity by sending one.
"""

import logging

logger = logging.getLogger(__name__)

# Never accept these as identity, whatever they contain.
REFUSED_HEADERS = frozenset({"x-serverless-authorization", "x-user-email",
                             "x-goog-authenticated-user-email"})


def bearer_from_headers(headers: dict | None) -> str | None:
    """The end user's token from `Authorization: Bearer <token>`, or None."""
    if not headers:
        return None
    lowered = {str(k).lower(): v for k, v in headers.items()}
    for refused in REFUSED_HEADERS & lowered.keys():
        logger.debug("Ignoring %s: it is not an end-user identity", refused)
    value = lowered.get("authorization") or ""
    if isinstance(value, bytes):
        value = value.decode("latin1")
    scheme, _, token = value.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


def headers_of(context) -> dict:
    """Dig the header dict out of an A2A RequestContext, defensively.

    The path is `context.call_context.state['headers']`, but every hop is
    optional across ADK versions and a missing one must degrade to "no
    identity" rather than take the turn down.
    """
    call_context = getattr(context, "call_context", None)
    state = getattr(call_context, "state", None) or {}
    try:
        return state.get("headers") or {}
    except AttributeError:
        return {}


def install(sethu_module):
    """Build the `before_agent` interceptor that binds the caller's token."""

    async def before_agent(context):
        token = bearer_from_headers(headers_of(context))
        sethu_module.set_user_token(token)
        if token:
            logger.info("Request carried an end-user token (%d chars)",
                        len(token))
        else:
            logger.info("Request carried no end-user identity")
        return context

    return before_agent
