"""Mechanical verification of alumni citations.

Instructing a model not to invent URLs does not work: it emitted
`https://noon.ai/people/sumita-bhallamudi/` for a named person, attached the
claim "NIT Warangal alum who worked at Stripe", and the URL was a 404. A
student would have messaged a stranger on the strength of that.

So the check is code, not prompt. A 404 cannot be argued with.

This lives in its own agent because `alumni_agent` holds `google_search`, a
Gemini built-in, which cannot share an agent with custom function tools.
"""

import asyncio
import re

import httpx

# Deliberately generous: we are separating "this page exists and is about the
# right thing" from "this URL was invented", not judging profile quality.
_TIMEOUT = 12.0
_MAX_LINKS = 12
_UA = "Mozilla/5.0 (compatible; PlacementIntelligenceAgent/1.0; +link-verification)"


def _normalise(term: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", term.lower())


async def _check_one(client: httpx.AsyncClient, url: str, terms: list[str]) -> dict:
    try:
        r = await client.get(url, timeout=_TIMEOUT, follow_redirects=True)
    except Exception as e:  # noqa: BLE001 - any failure to load is a failure to verify
        return {"url": url, "reachable": False, "status": None,
                "reason": f"could not load ({type(e).__name__})", "supports": []}

    if r.status_code >= 400:
        return {"url": url, "reachable": False, "status": r.status_code,
                "reason": f"HTTP {r.status_code}", "supports": []}

    body = _normalise(r.text)
    supports = [t for t in terms if t and _normalise(t) in body]
    return {"url": url, "reachable": True, "status": r.status_code,
            "reason": "ok", "supports": supports}


async def verify_links(urls: list[str], must_mention: list[str]) -> dict:
    """Fetch each URL and report whether it exists and supports the claims.

    Use this on every profile link before showing a named person to the
    student. A link that fails here must not be presented.

    Args:
      urls: Profile URLs to check.
      must_mention: Terms the page should contain to back the claim being
        made, e.g. ["Stripe", "NIT Warangal"]. Case and punctuation are
        ignored. Pass an empty list to check only that the page loads.

    Returns:
      `verified`: entries whose page loaded AND mentioned at least one term.
      `unsupported`: page loaded but mentioned none of the terms -- the link
        is real but does not back the claim.
      `dead`: did not load at all. Almost always an invented URL.
    """
    urls = [u for u in dict.fromkeys(urls) if u.startswith(("http://", "https://"))][:_MAX_LINKS]
    if not urls:
        return {"verified": [], "unsupported": [], "dead": [],
                "summary": "No usable URLs were supplied."}

    async with httpx.AsyncClient(headers={"User-Agent": _UA}) as client:
        results = await asyncio.gather(
            *(_check_one(client, u, must_mention) for u in urls)
        )

    verified = [r for r in results if r["reachable"] and (r["supports"] or not must_mention)]
    unsupported = [r for r in results if r["reachable"] and not r["supports"] and must_mention]
    dead = [r for r in results if not r["reachable"]]

    return {
        "verified": verified,
        "unsupported": unsupported,
        "dead": dead,
        "summary": (
            f"{len(verified)} verified, {len(unsupported)} reachable but not"
            f" supporting the claim, {len(dead)} dead. Present ONLY the"
            f" verified ones to the student."
        ),
    }


if __name__ == "__main__":
    async def _demo():
        out = await verify_links(
            ["https://noon.ai/people/sumita-bhallamudi/",  # the invented one
             "https://stripe.com/jobs"],
            ["Stripe"],
        )
        assert any(d["url"].startswith("https://noon.ai") for d in out["dead"]), out
        assert not any(v["url"].startswith("https://noon.ai") for v in out["verified"]), out
        print("dead:", [d["url"] for d in out["dead"]])
        print("verified:", [v["url"] for v in out["verified"]])
        print("\nok - the fabricated URL is rejected")

    asyncio.run(_demo())
