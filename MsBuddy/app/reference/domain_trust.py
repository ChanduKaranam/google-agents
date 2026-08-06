# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Source-domain trust classification — the `app:domain_trust` list (spec §6.1).

Decides whether a retrieved source is *official* (the institution or a
government speaking for itself) or merely *reporting*. That single decision
drives the `VERIFIED` vs `REPORTED` tier split in spec §7.1, so it is kept
here as static, versioned, reviewable data rather than left to the model.

Spec §16.4 recorded "source-trust list is unspecified" as a known gap. This
module closes it with rules rather than an enumeration, because there are
tens of thousands of universities and no list would stay complete.
"""

from __future__ import annotations

from typing import Literal

VERSION = "domain_trust:v1"

SourceClass = Literal["official", "aggregator", "unknown"]

# Academic and government suffixes. A host under one of these is speaking for
# an institution or a state, which is what "official" means here.
OFFICIAL_SUFFIXES: tuple[str, ...] = (
    ".edu",
    ".ac.uk",
    ".edu.au",
    ".ac.nz",
    ".ac.in",
    ".edu.in",
    ".ac.jp",
    ".edu.sg",
    ".edu.my",
    ".ac.za",
    ".gov",
    ".gov.uk",
    ".gc.ca",
    ".gov.au",
    ".gov.in",
    ".gov.sg",
    ".europa.eu",
)

# Country domains where universities commonly sit on the national TLD with no
# academic second level (Continental Europe and Canada especially). Membership
# here is NOT sufficient on its own — an institution keyword is also required,
# otherwise every .ca and .de site would read as official.
ACADEMIC_TLDS_REQUIRING_KEYWORD: tuple[str, ...] = (
    ".ch",
    ".de",
    ".nl",
    ".se",
    ".dk",
    ".no",
    ".fi",
    ".ie",
    ".ca",
    ".at",
    ".be",
    ".it",
    ".es",
    ".fr",
)

INSTITUTION_KEYWORDS: tuple[str, ...] = (
    "uni",
    "univ",
    "eth",
    "epfl",
    "tudelft",
    "kth",
    "dtu",
    "chalmers",
    "aalto",
    "polytech",
    "college",
    "institute",
    "school",
)

# Known aggregators, forums and lead-generation sites. Useful information can
# appear on them, but a claim they carry is `REPORTED`, never `VERIFIED`.
KNOWN_AGGREGATORS: frozenset[str] = frozenset(
    {
        "shiksha.com",
        "collegedunia.com",
        "yocket.com",
        "leverageedu.com",
        "mastersportal.com",
        "studyportals.com",
        "topuniversities.com",
        "timeshighereducation.com",
        "usnews.com",
        "gradcafe.com",
        "thegradcafe.com",
        "reddit.com",
        "quora.com",
        "linkedin.com",
        "wikipedia.org",
        "libertify.com",
        "collegeboard.org",
        "idp.com",
        "hotcoursesabroad.com",
    }
)


def normalize_domain(raw: str) -> str:
    """Reduce a domain-ish string to a bare lower-case host.

    Grounding metadata supplies a bare domain in practice, but URLs and
    `www.`-prefixed hosts are accepted so callers never have to pre-clean.
    """
    host = (raw or "").strip().lower()
    for scheme in ("https://", "http://"):
        if host.startswith(scheme):
            host = host[len(scheme) :]
    host = host.split("/")[0].split("?")[0].split("#")[0]
    if ":" in host:
        host = host.split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    return host.strip(".")


def registrable_suffix_match(host: str, suffix: str) -> bool:
    """True if `host` sits under `suffix` as a real label boundary."""
    return host == suffix.lstrip(".") or host.endswith(suffix)


def classify_domain(raw: str) -> dict:
    """Classify a source domain as official, aggregator, or unknown.

    Returns a dict rather than a bare enum so the reason travels with the
    verdict — spec §7.2 requires source metadata to be preserved end to end,
    and "why did this count as official" is part of that.
    """
    host = normalize_domain(raw)
    if not host:
        return {
            "domain": "",
            "source_class": "unknown",
            "is_official": False,
            "reason": "no domain supplied",
            "ruleset": VERSION,
        }

    if host in KNOWN_AGGREGATORS or any(
        host.endswith("." + a) for a in KNOWN_AGGREGATORS
    ):
        return {
            "domain": host,
            "source_class": "aggregator",
            "is_official": False,
            "reason": "listed aggregator, forum or ranking site",
            "ruleset": VERSION,
        }

    for suffix in OFFICIAL_SUFFIXES:
        if registrable_suffix_match(host, suffix):
            return {
                "domain": host,
                "source_class": "official",
                "is_official": True,
                "reason": f"academic or government suffix '{suffix}'",
                "ruleset": VERSION,
            }

    for tld in ACADEMIC_TLDS_REQUIRING_KEYWORD:
        if host.endswith(tld):
            label = host[: -len(tld)]
            if any(keyword in label for keyword in INSTITUTION_KEYWORDS):
                return {
                    "domain": host,
                    "source_class": "official",
                    "is_official": True,
                    "reason": (f"institution keyword on national domain '{tld}'"),
                    "ruleset": VERSION,
                }
            break

    return {
        "domain": host,
        "source_class": "unknown",
        "is_official": False,
        "reason": "not recognised as an institutional or government domain",
        "ruleset": VERSION,
    }


def is_official(raw: str) -> bool:
    """Convenience predicate over `classify_domain`."""
    return bool(classify_domain(raw)["is_official"])
