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

"""Source-domain trust — the VERIFIED/REPORTED split (spec §7.1)."""

from __future__ import annotations

import pytest

from app.reference.domain_trust import classify_domain, is_official, normalize_domain


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://www.ethz.ch/en/studies", "ethz.ch"),
        ("WWW.MIT.EDU", "mit.edu"),
        ("ethz.ch:443", "ethz.ch"),
        ("  ox.ac.uk  ", "ox.ac.uk"),
        ("example.com/path?q=1#frag", "example.com"),
    ],
)
def test_domain_normalization(raw: str, expected: str) -> None:
    assert normalize_domain(raw) == expected


@pytest.mark.parametrize(
    "domain",
    [
        "mit.edu",
        "stanford.edu",
        "ox.ac.uk",
        "unimelb.edu.au",
        "iitb.ac.in",
        "canada.gc.ca",
        "uscis.gov",
        "studyinaustralia.gov.au",
    ],
)
def test_academic_and_government_suffixes_are_official(domain: str) -> None:
    verdict = classify_domain(domain)
    assert verdict["is_official"] is True
    assert verdict["source_class"] == "official"
    assert verdict["reason"]


@pytest.mark.parametrize("domain", ["ethz.ch", "epfl.ch", "tudelft.nl", "uni-bonn.de"])
def test_national_domains_need_an_institution_keyword(domain: str) -> None:
    """Continental universities sit on the national TLD with no .ac level."""
    assert is_official(domain) is True


@pytest.mark.parametrize("domain", ["migros.ch", "bahn.de", "bol.com", "shopify.ca"])
def test_national_tld_alone_is_not_enough(domain: str) -> None:
    """Otherwise every .ch and .de site would read as a university."""
    assert is_official(domain) is False


@pytest.mark.parametrize(
    "domain",
    [
        "shiksha.com",
        "collegedunia.com",
        "yocket.com",
        "topuniversities.com",
        "usnews.com",
        "reddit.com",
        "wikipedia.org",
        "linkedin.com",
        "libertify.com",
    ],
)
def test_aggregators_are_never_official(domain: str) -> None:
    verdict = classify_domain(domain)
    assert verdict["source_class"] == "aggregator"
    assert verdict["is_official"] is False


def test_aggregator_subdomains_are_caught() -> None:
    assert classify_domain("en.wikipedia.org")["source_class"] == "aggregator"


def test_unknown_domain_is_not_official() -> None:
    verdict = classify_domain("some-random-blog.xyz")
    assert verdict["source_class"] == "unknown"
    assert verdict["is_official"] is False


def test_empty_domain_is_handled() -> None:
    verdict = classify_domain("")
    assert verdict["is_official"] is False
    assert verdict["source_class"] == "unknown"


def test_verdict_carries_its_ruleset_version() -> None:
    """Spec §7.2 requires source metadata to survive end to end."""
    assert classify_domain("mit.edu")["ruleset"] == "domain_trust:v1"


def test_lookalike_suffix_does_not_pass() -> None:
    """'notreally-edu.com' must not match the '.edu' rule."""
    assert is_official("notreally-edu.com") is False
