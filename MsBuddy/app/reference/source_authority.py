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

"""Field-scoped source authority for alumni claims (C4, Stage 0 §5).

C2 needed one bit per source: official, or reporting. That is not enough for
claims about people.

> A university speaks authoritatively about who attended it. Its statement
> about where a graduate works *today* is a claim of unknown age. A
> company's own site is the reverse. Neither is "authoritative" in general.

So authority here is **per (source class, field)**, and it is three-valued:

| | |
|---|---|
| `VERIFY` | this class has standing for this field — tier `VERIFIED` |
| `REPORT` | it may state it, attributed — tier `REPORTED` |
| `REFUSE` | it has no standing at all — the field stays `UNKNOWN` |

`REFUSE` is deliberately narrow. The Phase 2 audit fixed a defect where a
third-party value was *discarded* rather than kept as `REPORTED`, and that
lesson holds here: attribution beats deletion. `REFUSE` is reserved for the
cases in the approved Stage 0 table where a class has no business speaking
to a field at all.

**Origination is the strongest control in C4.** Only classes 1-4 may bring a
person into existence; classes 5-7 may only add to someone already
established on stronger evidence. A search snippet cannot mint a human
being.

Pure data and pure functions: no ADK, no network, no model.
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field as dataclass_field

from app.reference.domain_trust import classify_domain, normalize_domain

VERSION = "source_authority:v1"

# --- Authority verdicts ----------------------------------------------------

VERIFY = "verify"
REPORT = "report"
REFUSE = "refuse"

# --- Alumni claim fields ---------------------------------------------------
# Duplicated deliberately as plain strings rather than imported from
# `alumni_fields`, which imports this module. The test suite asserts the two
# registries agree, so drift is caught rather than merely discouraged.

UNIVERSITY_AFFILIATION = "university_affiliation"
PROGRAM = "program"
DEGREE = "degree"
GRADUATION_YEAR = "graduation_year"
EMPLOYER = "employer"
ROLE = "role"
PRIOR_INSTITUTION = "prior_institution"
PRIOR_DEGREE = "prior_degree"

ACADEMIC_FIELDS = frozenset(
    {
        UNIVERSITY_AFFILIATION,
        PROGRAM,
        DEGREE,
        GRADUATION_YEAR,
        PRIOR_INSTITUTION,
        PRIOR_DEGREE,
    }
)

# --- Source classes --------------------------------------------------------

UNIVERSITY_OFFICIAL = "university_official"
UNIVERSITY_ALUMNI_PAGE = "university_alumni_page"
COMPANY_OFFICIAL = "company_official"
PROFESSIONAL_ORG = "professional_org"
REPUTABLE_PUBLICATION = "reputable_publication"
PUBLIC_PROFILE = "public_profile"
AGGREGATOR = "aggregator"
EXCLUDED = "excluded"


@dataclass(frozen=True)
class SourceClassSpec:
    """What one class of source is allowed to establish."""

    key: str
    label: str
    can_originate: bool
    can_corroborate: bool
    verifies: frozenset[str] = dataclass_field(default_factory=frozenset)
    refuses: frozenset[str] = dataclass_field(default_factory=frozenset)
    note: str = ""


SOURCE_CLASSES: dict[str, SourceClassSpec] = {
    UNIVERSITY_OFFICIAL: SourceClassSpec(
        key=UNIVERSITY_OFFICIAL,
        label="University official page",
        can_originate=True,
        can_corroborate=True,
        verifies=ACADEMIC_FIELDS,
        note=(
            "Authoritative about who attended and what they studied. Its "
            "employer line is historical: true when published, unknown now, "
            "so employer and role are REPORTED and carry the PERSON TTL."
        ),
    ),
    UNIVERSITY_ALUMNI_PAGE: SourceClassSpec(
        key=UNIVERSITY_ALUMNI_PAGE,
        label="University alumni story page",
        can_originate=True,
        can_corroborate=True,
        verifies=ACADEMIC_FIELDS,
        note=(
            "Same standing as the institution itself. The employer it names "
            "is the employer at time of writing."
        ),
    ),
    COMPANY_OFFICIAL: SourceClassSpec(
        key=COMPANY_OFFICIAL,
        label="Employer's own site",
        can_originate=True,
        can_corroborate=True,
        verifies=frozenset({EMPLOYER, ROLE}),
        refuses=frozenset({GRADUATION_YEAR}),
        note=(
            "Authoritative that this person works here, and for what they "
            "do. Per the approved Stage 0 table it has no standing on a "
            "graduation year — see the open question raised at Stage A."
        ),
    ),
    PROFESSIONAL_ORG: SourceClassSpec(
        key=PROFESSIONAL_ORG,
        label="Professional body or conference",
        can_originate=True,
        can_corroborate=True,
        refuses=frozenset({GRADUATION_YEAR}),
        note=(
            "An affiliation here is dated by the event it belongs to. It is "
            "'affiliation at time of publication', never 'current', so "
            "nothing is VERIFIED and a graduation year is out of scope."
        ),
    ),
    REPUTABLE_PUBLICATION: SourceClassSpec(
        key=REPUTABLE_PUBLICATION,
        label="Publication or press",
        can_originate=False,
        can_corroborate=True,
        note="Reports on people; does not speak for them or for an institution.",
    ),
    PUBLIC_PROFILE: SourceClassSpec(
        key=PUBLIC_PROFILE,
        label="Personal or self-published page",
        can_originate=False,
        can_corroborate=True,
        note=(
            "Self-published, and the default for any domain we cannot place. "
            "Defaulting here is what stops an unrecognised domain from "
            "creating a person."
        ),
    ),
    AGGREGATOR: SourceClassSpec(
        key=AGGREGATOR,
        label="Aggregator or search snippet",
        can_originate=False,
        can_corroborate=True,
        note="May agree with a person who already exists. Cannot create one.",
    ),
    EXCLUDED: SourceClassSpec(
        key=EXCLUDED,
        label="Excluded source",
        can_originate=False,
        can_corroborate=False,
        refuses=frozenset(ACADEMIC_FIELDS | {EMPLOYER, ROLE}),
        note=(
            "LinkedIn and anything else we must not read. Link-only: never "
            "fetched, never parsed, never a fact source, and it cannot even "
            "corroborate."
        ),
    ),
}

SOURCE_CLASS_KEYS: tuple[str, ...] = tuple(SOURCE_CLASSES)

ORIGINATING_CLASSES: frozenset[str] = frozenset(
    key for key, spec in SOURCE_CLASSES.items() if spec.can_originate
)

# Domains that must never be read, whatever they contain. Scraping LinkedIn
# violates its terms of service; a URL from it is offered to the student as
# a link and nothing is taken from the page.
EXCLUDED_DOMAINS: frozenset[str] = frozenset(
    {"linkedin.com", "www.linkedin.com", "lnkd.in"}
)

# Seed sets. Neither can ever be complete, which is why an unrecognised
# domain falls back to `public_profile` — a class that cannot originate.
PROFESSIONAL_ORG_DOMAINS: frozenset[str] = frozenset(
    {
        "acm.org", "ieee.org", "usenix.org", "aaai.org", "siggraph.org",
        "neurips.cc", "icml.cc", "iclr.cc", "aclweb.org", "aclanthology.org",
        "informs.org", "asme.org", "aiche.org", "rsc.org", "aps.org",
    }
)  # fmt: skip

REPUTABLE_PUBLICATION_DOMAINS: frozenset[str] = frozenset(
    {
        "nature.com", "science.org", "sciencedirect.com", "springer.com",
        "arxiv.org", "ft.com", "economist.com", "reuters.com", "bbc.co.uk",
        "nytimes.com", "theguardian.com",
    }
)  # fmt: skip

# A path fragment on an official academic domain that marks an alumni story.
ALUMNI_PAGE_MARKERS: tuple[str, ...] = ("alumni", "alumnus", "alumna", "graduates")


def authority_for(source_class: str, field_name: str) -> str:
    """What `source_class` may establish about `field_name`.

    Returns `VERIFY`, `REPORT` or `REFUSE`. An unknown class refuses
    everything — a source we cannot place has no standing.
    """
    spec = SOURCE_CLASSES.get(source_class)
    if spec is None:
        return REFUSE
    if field_name in spec.refuses:
        return REFUSE
    if field_name in spec.verifies:
        return VERIFY
    if spec.can_corroborate:
        return REPORT
    return REFUSE


def can_originate(source_class: str) -> bool:
    """True if this class may bring a person into existence.

    The single most important control in C4: classes 5-7 may only add to
    someone already established by a class 1-4 source.
    """
    spec = SOURCE_CLASSES.get(source_class)
    return bool(spec and spec.can_originate)


def can_corroborate(source_class: str) -> bool:
    """True if this class may add weight to an existing person."""
    spec = SOURCE_CLASSES.get(source_class)
    return bool(spec and spec.can_corroborate)


def is_excluded(domain: str) -> bool:
    """True if this domain must never be used as a fact source."""
    host = normalize_domain(domain)
    if not host:
        return False
    return host in EXCLUDED_DOMAINS or any(
        host.endswith("." + d) for d in EXCLUDED_DOMAINS
    )


def _matches(host: str, domains: frozenset[str]) -> bool:
    return host in domains or any(host.endswith("." + d) for d in domains)


def classify_alumni_source(
    domain: str,
    url: str = "",
    claimed_employer: str = "",
) -> dict[str, object]:
    """Place a retrieved source into an alumni source class.

    `claimed_employer` is what makes `company_official` reachable at all: a
    domain counts as the employer's own site only when it corresponds to the
    employer being claimed. Without that correspondence there is no
    deterministic way to tell a company's site from any other business page,
    and guessing would hand employer-verification to whoever registered a
    domain.

    Anything unrecognised becomes `public_profile`, which cannot originate a
    person. That default is the fail-safe.
    """
    host = normalize_domain(domain)
    if not host:
        return {
            "domain": "",
            "source_class": PUBLIC_PROFILE,
            "reason": "domain_unreadable",
            "ruleset": VERSION,
        }

    if is_excluded(host):
        return {
            "domain": host,
            "source_class": EXCLUDED,
            "reason": "excluded_domain_link_only",
            "ruleset": VERSION,
        }

    base = classify_domain(host)

    if base["source_class"] == "official":
        lowered = f"{url} {host}".lower()
        if any(marker in lowered for marker in ALUMNI_PAGE_MARKERS):
            return {
                "domain": host,
                "source_class": UNIVERSITY_ALUMNI_PAGE,
                "reason": "official_academic_domain_alumni_page",
                "ruleset": VERSION,
            }
        return {
            "domain": host,
            "source_class": UNIVERSITY_OFFICIAL,
            "reason": base.get("reason", "official_academic_domain"),
            "ruleset": VERSION,
        }

    if _matches(host, PROFESSIONAL_ORG_DOMAINS):
        return {
            "domain": host,
            "source_class": PROFESSIONAL_ORG,
            "reason": "known_professional_body",
            "ruleset": VERSION,
        }

    if _matches(host, REPUTABLE_PUBLICATION_DOMAINS):
        return {
            "domain": host,
            "source_class": REPUTABLE_PUBLICATION,
            "reason": "known_publication",
            "ruleset": VERSION,
        }

    if claimed_employer and _employer_matches_domain(claimed_employer, host):
        return {
            "domain": host,
            "source_class": COMPANY_OFFICIAL,
            "reason": "domain_corresponds_to_claimed_employer",
            "ruleset": VERSION,
        }

    if base["source_class"] == "aggregator":
        return {
            "domain": host,
            "source_class": AGGREGATOR,
            "reason": base.get("reason", "known_aggregator"),
            "ruleset": VERSION,
        }

    return {
        "domain": host,
        "source_class": PUBLIC_PROFILE,
        "reason": "unrecognised_domain_defaults_to_self_published",
        "ruleset": VERSION,
    }


def _employer_matches_domain(employer: str, host: str) -> bool:
    """True if `host` plausibly *is* `employer`'s own domain.

    Deliberately strict, and strict in one direction only: the comparison is
    on the registrable label, so `booking.com` matches the employer
    "Booking.com" but `booking-jobs-review.example` does not. A loose match
    here would let any site verify any employer.
    """
    labels = host.split(".")
    if len(labels) < 2:
        return False
    # Registrable label, allowing for two-part suffixes such as .co.uk.
    index = -2
    if len(labels) >= 3 and len(labels[-2]) <= 3 and len(labels[-1]) <= 3:
        index = -3
    registrable = labels[index]

    # Employers are written both ways: "Booking" and "Booking.com". Both
    # should match booking.com, so a trailing TLD on the *employer* is
    # stripped as well. Only whole-string forms are compared — matching on a
    # first word would make "Apple Bank" verify anything on apple.com.
    lowered = employer.strip().lower()
    candidates = {lowered}
    if "." in lowered:
        head, _, tail = lowered.rpartition(".")
        if head and 2 <= len(tail) <= 4 and tail.isalpha():
            candidates.add(head)

    for candidate in candidates:
        token = "".join(ch for ch in candidate if ch.isalnum())
        if len(token) >= 3 and token == registrable:
            return True
    return False
