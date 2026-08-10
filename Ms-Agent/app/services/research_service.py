"""Research service — grounding harvest, source classification, verification.

The evidence-first rule made executable. The search runtime records what it
actually retrieved (grounding metadata: domains, URIs, and the answer spans
it attributed to each domain). This service reads that record and grades
every claim against it:

* ``verified``           — cited domain retrieved AND the value appears in
                           text attributed to it.
* ``partially_verified`` — domain retrieved, value not locatable in its
                           attributed text.
* ``unverified``         — domain never retrieved this session.

The model asserts nothing here; it proposes, and this code grades. That is
what "do NOT hallucinate university requirements" means in practice —
a fabricated deadline grades unverified no matter how fluent it sounded.
"""

from __future__ import annotations

from typing import Any

from app.models.evidence import Evidence, SourceType, VerificationStatus
from app.models.program import ProgramFact

AGGREGATOR_DOMAINS = (
    "topuniversities.com",
    "usnews.com",
    "timeshighereducation.com",
    "mastersportal.com",
    "shiksha.com",
    "yocket.com",
    "collegedunia.com",
    "quora.com",
    "reddit.com",
)


def _flatten(text: str) -> str:
    return " ".join(str(text or "").casefold().split())


def normalize_domain(raw: str) -> str:
    domain = str(raw or "").strip().casefold()
    for prefix in ("https://", "http://"):
        domain = domain.removeprefix(prefix)
    domain = domain.split("/")[0]
    return domain.removeprefix("www.")


def harvest_grounding(session: Any) -> list[dict[str, Any]]:
    """One entry per retrieved domain: uris, titles, attributed segments.

    Reads `grounding_metadata` off session events. `domain` is often None
    in practice with `title` carrying the domain string, so both are tried.
    Failure-tolerant by design: a harvest problem yields an empty ledger,
    which fails closed — claims grade unverified, nothing crashes.
    """
    by_domain: dict[str, dict[str, Any]] = {}
    for event in getattr(session, "events", None) or []:
        metadata = getattr(event, "grounding_metadata", None)
        if metadata is None:
            continue
        chunks = getattr(metadata, "grounding_chunks", None) or []
        index_to_domain: dict[int, str] = {}
        for index, chunk in enumerate(chunks):
            web = getattr(chunk, "web", None)
            if web is None:
                continue
            domain = normalize_domain(
                getattr(web, "domain", None) or getattr(web, "title", "") or ""
            )
            if not domain or "vertexaisearch" in domain:
                continue
            index_to_domain[index] = domain
            entry = by_domain.setdefault(
                domain, {"domain": domain, "uris": [], "titles": [], "segments": []}
            )
            uri = getattr(web, "uri", None)
            if uri and uri not in entry["uris"]:
                entry["uris"].append(str(uri))
            title = getattr(web, "title", None)
            if title and title not in entry["titles"]:
                entry["titles"].append(str(title))
        for support in getattr(metadata, "grounding_supports", None) or []:
            segment = getattr(support, "segment", None)
            text = getattr(segment, "text", "") or ""
            if not text:
                continue
            for index in getattr(support, "grounding_chunk_indices", None) or []:
                domain = index_to_domain.get(index)
                if domain and text not in by_domain[domain]["segments"]:
                    by_domain[domain]["segments"].append(text)
    return list(by_domain.values())


def classify_source(domain: str, university_website: str = "") -> SourceType:
    domain = normalize_domain(domain)
    site = normalize_domain(university_website)
    if site and (domain == site or domain.endswith("." + site)):
        return "official"
    if domain.endswith(".gov") or ".gov." in domain:
        return "government"
    if any(domain == agg or domain.endswith("." + agg) for agg in AGGREGATOR_DOMAINS):
        return "aggregator"
    if domain.endswith(".edu") or ".edu." in domain or ".ac." in domain:
        return "official"
    return "other"


def verify_claim(
    value: str, domain: str, harvest: list[dict[str, Any]]
) -> VerificationStatus:
    wanted = normalize_domain(domain)
    entry = next((e for e in harvest if e["domain"] == wanted), None)
    if entry is None:
        return "unverified"
    flat_value = _flatten(value)
    if flat_value and any(flat_value in _flatten(s) for s in entry["segments"]):
        return "verified"
    return "partially_verified"


def build_fact(
    value: str,
    domain: str,
    harvest: list[dict[str, Any]],
    university_website: str = "",
    quote: str = "",
) -> ProgramFact:
    """Grade one claim and wrap it with its evidence."""
    status = verify_claim(value, domain, harvest)
    wanted = normalize_domain(domain)
    entry = next((e for e in harvest if e["domain"] == wanted), None)
    return ProgramFact(
        value=str(value),
        status=status,
        evidence=Evidence(
            source_domain=wanted,
            source_title=(entry["titles"][0] if entry and entry["titles"] else ""),
            url=(entry["uris"][0] if entry and entry["uris"] else ""),
            source_type=classify_source(wanted, university_website),
            quote=quote,
            retrieved_at=Evidence.now_iso(),
        ),
    )
