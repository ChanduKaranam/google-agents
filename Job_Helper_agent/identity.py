"""Lift the end user's identity out of the A2A request headers.

Without this, every turn is refused. `to_a2a()` builds a bare `Starlette` with
no `AuthenticationMiddleware` (`agent_to_a2a.py:231`), so `request.user` raises,
`DefaultCallContextBuilder.build` suppresses that
(`a2a/server/apps/jsonrpc/jsonrpc_app.py:148-151`), and the caller becomes an
`UnauthenticatedUser` whose `user_name` is `''` (`a2a/auth/user.py:29-31`).
That empty string is falsy, so `_get_user_id`
(`google/adk/a2a/converters/request_converter.py:66-76`) always falls through to
`f'A2A_USER_{context_id}'` -- exactly the shape the identity guard in
`callbacks.py` rejects. The agent would refuse turn 1 and every turn after.

The same call context already carries every request header at
`call_context.state['headers']`, so the identity is available; it just is not
where ADK looks. This module bridges the two.

WHICH header Gemini Enterprise actually sends is UNCONFIRMED and must be
verified against a live GE call (inspect `call_context.state['headers']` on a
real request). Until then the lookup is deliberately tolerant of several
plausible names -- and when none of them match it returns None, leaving the
`A2A_USER_*` sentinel in place so the guard still refuses. It never invents an
identity and never falls back to the service account.
"""

from __future__ import annotations

import logging

from google.adk.a2a.converters.part_converter import convert_a2a_part_to_genai_part
from google.adk.a2a.converters.request_converter import (
    convert_a2a_request_to_agent_run_request,
)

logger = logging.getLogger(__name__)

IDENTITY_HEADERS = (
    "x-goog-authenticated-user-email",
    "x-goog-iap-jwt-assertion-email",
    "x-user-email",
)

# Google identity headers carry the issuer as a prefix, e.g.
# "accounts.google.com:student@example.edu".
_ISSUER_PREFIX = "accounts.google.com:"


def extract_user_id(headers: dict) -> str | None:
    """Return the end user's identity from request headers, or None."""
    lowered = {
        str(name).lower(): value for name, value in (headers or {}).items()
    }
    for candidate in IDENTITY_HEADERS:
        value = (lowered.get(candidate) or "").strip()
        if value.startswith(_ISSUER_PREFIX):
            value = value[len(_ISSUER_PREFIX) :].strip()
        if value:
            return value
    return None


def build_request_converter():
    """Build an `A2ARequestToAgentRunRequestConverter` that honours headers."""

    def convert(request, part_converter=convert_a2a_part_to_genai_part):
        run_request = convert_a2a_request_to_agent_run_request(
            request, part_converter
        )
        call_context = getattr(request, "call_context", None)
        headers = (getattr(call_context, "state", None) or {}).get("headers", {})
        user_id = extract_user_id(headers)
        # Names only, never values: these headers carry the student's email and
        # bearer tokens. The names alone are what tells us which one Gemini
        # Enterprise actually sends, which is the open question this logging
        # exists to close. Drop it to DEBUG once IDENTITY_HEADERS is narrowed.
        # WARNING, not INFO: nothing configures logging for this package, so the
        # root level stays at WARNING and an info() call is silently dropped --
        # which is exactly what happened on the first real Gemini Enterprise
        # call, costing a deploy cycle. Drop this line once the header is known.
        # Also log where else an identity could be hiding, so one real call
        # answers the question even if GE sends no identity header at all.
        # Keys and shapes only -- never values.
        message = getattr(request, "message", None)
        logger.warning(
            "a2a request headers=%s state_keys=%s msg_meta_keys=%s"
            " ctx_user=%r resolved_user_id=%r identity_found=%s",
            sorted(str(name).lower() for name in (headers or {})),
            sorted(str(k) for k in (getattr(call_context, "state", None) or {})),
            sorted(str(k) for k in (getattr(message, "metadata", None) or {})),
            getattr(getattr(call_context, "user", None), "user_name", None),
            run_request.user_id,
            bool(user_id),
        )
        # Only override on a real find. No match means the A2A_USER_* sentinel
        # survives and `require_real_user` refuses the turn -- refusing beats
        # guessing who the student is.
        if user_id:
            run_request.user_id = user_id
        return run_request

    return convert
