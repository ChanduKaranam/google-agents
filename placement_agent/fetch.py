"""Fetch a job description from a URL, refusing sites we must not automate.

Replaces the `url_context` Gemini built-in. Two reasons:

1. `url_context` fetches whatever URL it is given. If a student pastes a
   LinkedIn job link, our agent performs automated access to LinkedIn --
   robots.txt is `User-agent: * / Disallow: /`, and the User Agreement
   prohibits it. That is a compliance breach originating from our production
   agent, triggered by an ordinary student action.
2. We have twice found that instructing a model not to do something does not
   hold (it invented a profile URL after being told not to). A blocklist in
   code cannot be talked around.

Being a normal function tool rather than a Gemini built-in also frees
resume_gap_agent from the "one built-in, nothing else" constraint.
"""

import re
from urllib.parse import urlparse

import httpx

# Sites whose terms prohibit automated access, or that sit behind an auth wall
# where a fetch returns a login page rather than content. Suffix-matched, so
# subdomains are covered.
BLOCKED = (
    "linkedin.com",
    "facebook.com",
    "instagram.com",
    "x.com",
    "twitter.com",
    "glassdoor.com",
    "indeed.com",
    "naukri.com",
)

_TIMEOUT = 20.0
_MAX_CHARS = 20000
_UA = "Mozilla/5.0 (compatible; PlacementIntelligenceAgent/1.0)"


def _host_blocked(host: str) -> str | None:
    host = host.lower().removeprefix("www.")
    for b in BLOCKED:
        if host == b or host.endswith("." + b):
            return b
    return None


async def fetch_job_description(url: str) -> dict:
    """Fetch the text of a job posting so it can be compared to a resume.

    Args:
      url: Link to the job description.

    Returns:
      Either the page text, or a refusal explaining what to do instead.
    """
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return {"ok": False, "reason": f"{url!r} is not a usable web address."}

    blocked = _host_blocked(parsed.netloc)
    if blocked:
        return {
            "ok": False,
            "blocked_domain": blocked,
            "reason": (
                f"I can't open {blocked} automatically -- their terms prohibit"
                " it, so I won't do it even though the page may be visible to"
                " you when logged in."
            ),
            "what_to_do": (
                "Open the link yourself and paste the job description text"
                " here. I'll work from that."
            ),
        }

    try:
        async with httpx.AsyncClient(headers={"User-Agent": _UA}) as client:
            r = await client.get(url, timeout=_TIMEOUT, follow_redirects=True)
    except Exception as e:  # noqa: BLE001 - report any failure the same way
        return {"ok": False, "reason": f"Could not load the page ({type(e).__name__})."
                                       " Paste the job description text instead."}

    # A redirect can land somewhere blocked even when the original host was fine.
    final_blocked = _host_blocked(urlparse(str(r.url)).netloc)
    if final_blocked:
        return {"ok": False, "blocked_domain": final_blocked,
                "reason": f"That link redirects to {final_blocked}, which I can't open"
                          " automatically.",
                "what_to_do": "Please paste the job description text instead."}

    if r.status_code >= 400:
        return {"ok": False, "reason": f"The page returned HTTP {r.status_code}."
                                       " Paste the job description text instead."}

    text = re.sub(r"(?is)<(script|style|noscript).*?</\1>", " ", r.text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) < 200:
        return {"ok": False, "reason": "That page had almost no readable text -- it may"
                                       " need JavaScript. Paste the text instead."}

    return {"ok": True, "final_url": str(r.url), "text": text[:_MAX_CHARS]}


if __name__ == "__main__":
    import asyncio

    async def _demo():
        for u in ("https://www.linkedin.com/jobs/view/123456",
                  "https://in.linkedin.com/jobs/view/123",
                  "http://LinkedIn.com/in/someone"):
            out = await fetch_job_description(u)
            assert not out["ok"] and out.get("blocked_domain") == "linkedin.com", out
        assert not (await fetch_job_description("not-a-url"))["ok"]
        ok = await fetch_job_description("https://stripe.com/jobs")
        print("linkedin blocked (incl. subdomain + case + /in/ path): yes")
        print("stripe.com/jobs fetched:", ok["ok"], "| chars:", len(ok.get("text", "")))
        print("\nok")

    asyncio.run(_demo())
