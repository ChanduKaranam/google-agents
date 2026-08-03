"""The Sethu REST client: token exchange, caching, and the four reads.

DEV ONLY. `BASE_URL` is fixed to Sethu's dev host and there is deliberately no
environment override and no prod fallback -- a config default is exactly how a
prod URL gets called by accident. Pointing this at prod is a decision someone
makes by editing this line, not by setting a variable.

Auth, per Sethu's guide (verified live 2026-08-03):
  1. Gemini Enterprise forwards the end user's Google OAuth ACCESS token.
  2. POST /auth/agent-tokens/exchange trades it for a 30-day Sethu JWT that
     carries the userId, role and tenantId -- nothing is hardcoded.
  3. Every read then sends `Authorization: Bearer <that JWT>`.

The ID-token variant in Sethu's doc is unreachable from a Gemini Enterprise A2A
agent: GE forwards an opaque access token, not a signed OIDC token. Sethu
accepts `googleAccessToken` for exactly this reason.
"""

import base64
import contextvars
import json
import logging
import os
import time
import urllib.error
import urllib.request

BASE_URL = "https://sethu-dev-api.onrender.com/api/v1"

# Server-to-server credential. Injected from Secret Manager on Cloud Run; the
# agent runs on recorded samples when it is absent rather than failing to boot.
AGENT_SECRET_ENV = "SETHU_AGENT_SECRET"

# A pre-minted Sethu agent token, used INSTEAD of the exchange flow.
#
# Gemini Enterprise only forwards an end-user Google token once the
# registration carries `authorizationConfig.agentAuthorization`. Until that
# OAuth client exists, this is the only way to demo against live data -- so it
# is deliberately supported, and deliberately loud about what it costs: every
# session resolves to whichever ambassador the token was minted for.
# ponytail: remove once GE forwards a user token; the exchange path is the real one.
AGENT_TOKEN_ENV = "SETHU_AGENT_TOKEN"

TIMEOUT_SECONDS = 20

logger = logging.getLogger(__name__)


class SethuError(RuntimeError):
    """A Sethu call failed. Carries their requestId so they can trace it."""

    def __init__(self, message: str, code: str = "", request_id: str = ""):
        super().__init__(message)
        self.code = code
        self.request_id = request_id


def enabled() -> bool:
    """True when the agent is configured to call Sethu at all.

    Both halves are required: the server-to-server secret, and an end-user
    Google token to exchange. Without either, `data.py` serves the recorded
    samples -- so a missing secret degrades the demo to sample data instead of
    taking the agent offline.
    """
    if os.environ.get(AGENT_TOKEN_ENV):
        return True
    return bool(os.environ.get(AGENT_SECRET_ENV) and _user_token())


# The end user's Google access token for the turn in flight, set by the A2A
# request hook from the inbound Authorization header.
#
# A ContextVar, NOT a module global: Cloud Run serves requests concurrently in
# one process, and a plain global is shared mutable state across them -- two
# ambassadors overlapping by milliseconds and one reads the other's cohort.
# A ContextVar is bound per asyncio task, so each request sees only its own.
_current_user_token: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "sethu_user_token", default=None)

# userId -> Sethu JWT. Sethu tokens last 30 days, so re-exchanging per turn
# would mint a row per message; their guide asks callers to reuse.
_token_cache: dict[str, dict] = {}


def set_user_token(token: str | None) -> None:
    _current_user_token.set(token)


def _user_token() -> str | None:
    return _current_user_token.get()


def _request(method: str, path: str, headers: dict,
             body: dict | None = None) -> dict:
    payload = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        f"{BASE_URL}{path}", data=payload, method=method,
        headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            parsed = json.loads(response.read())
    except urllib.error.HTTPError as error:
        parsed = _parse_error_body(error)
        detail = (parsed.get("error") or {})
        request_id = (parsed.get("meta") or {}).get("requestId", "")
        logger.warning("Sethu %s %s failed: %s %s (requestId=%s)", method, path,
                       error.code, detail.get("code", ""), request_id)
        raise SethuError(detail.get("message", str(error)),
                         detail.get("code", ""), request_id) from error
    except urllib.error.URLError as error:
        logger.warning("Sethu %s %s unreachable: %s", method, path, error)
        raise SethuError(f"Sethu unreachable: {error.reason}") from error
    # Sethu wraps everything as {data, error, meta}; callers want `data`.
    return parsed.get("data") or {}


def _parse_error_body(error) -> dict:
    try:
        return json.loads(error.read())
    except Exception:  # noqa: BLE001 - a non-JSON error body must not mask the HTTP one
        return {}


def _claims(token: str) -> dict:
    """Read the tenantId out of a Sethu JWT without verifying it.

    Only ever used on a token Sethu itself minted for us, and only to learn
    which tenant path to call -- never to make a trust decision.
    """
    payload = token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(payload))


def _agent_token() -> dict:
    """Exchange the end user's Google access token for a Sethu agent token."""
    preminted = os.environ.get(AGENT_TOKEN_ENV)
    if preminted:
        claims = _claims(preminted)
        return {"token": preminted, "tenantId": claims["tenantId"],
                "role": claims.get("role"), "userId": claims.get("sub")}
    user_token = _user_token()
    if not user_token:
        raise SethuError("No end-user Google token on this request")
    cached = _token_cache.get(user_token)
    if cached:
        return cached
    secret = os.environ.get(AGENT_SECRET_ENV, "")
    minted = _request("POST", "/auth/agent-tokens/exchange",
                      {"X-Agent-Secret": secret},
                      {"googleAccessToken": user_token})
    # Cached against the Google token, so a different signed-in user can never
    # be served another person's Sethu token from this process.
    _token_cache[user_token] = minted
    logger.info("Exchanged a Sethu token: role=%s tenantId=%s",
                minted.get("role"), minted.get("tenantId"))
    return minted


# One card asks for the cohort several times over -- the meter, the milestone
# line, the straggler phone join and the roster total all read it -- so an
# uncached render cost 5 round trips and ~10s against dev. Sethu's own numbers
# lag Google by 15 min to ~6h, so holding a response for seconds cannot show
# her anything staler than the endpoint already does.
CACHE_SECONDS = 30
_response_cache: dict[tuple, tuple[float, dict]] = {}


def clear_cache() -> None:
    _response_cache.clear()


def get(kind: str, student_id: str | None = None) -> dict:
    """Fetch one of the four ambassador reads."""
    key = (kind, student_id)
    hit = _response_cache.get(key)
    now = time.monotonic()
    if hit and hit[0] > now:
        return hit[1]
    fetched = _get_uncached(kind, student_id)
    _response_cache[key] = (now + CACHE_SECONDS, fetched)
    return fetched


def _get_uncached(kind: str, student_id: str | None) -> dict:
    session = _agent_token()
    tenant = session["tenantId"]
    paths = {
        "cohort": f"/tenants/{tenant}/cohorts/mine",
        "stragglers": "/cohorts/mine/stragglers?page=1&limit=50",
        "leaderboard": f"/tenants/{tenant}/leaderboard?page=1&limit=10",
        "student": f"/cohorts/mine/students/{student_id}",
    }
    return _request("GET", paths[kind],
                    {"Authorization": f"Bearer {session['token']}"})
