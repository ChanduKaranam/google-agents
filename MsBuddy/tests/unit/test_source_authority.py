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

"""Field-scoped source authority (C4 Stage A).

The safety model for alumni evidence lives in this table, so these tests are
mostly assertions about what a source is *not* allowed to establish.
"""

from __future__ import annotations

import pytest

from app.reference.alumni_fields import ALL_FIELD_NAMES
from app.reference.source_authority import (
    AGGREGATOR,
    COMPANY_OFFICIAL,
    DEGREE,
    EMPLOYER,
    EXCLUDED,
    GRADUATION_YEAR,
    ORIGINATING_CLASSES,
    PROFESSIONAL_ORG,
    PROGRAM,
    PUBLIC_PROFILE,
    REFUSE,
    REPORT,
    REPUTABLE_PUBLICATION,
    ROLE,
    SOURCE_CLASSES,
    UNIVERSITY_AFFILIATION,
    UNIVERSITY_ALUMNI_PAGE,
    UNIVERSITY_OFFICIAL,
    VERIFY,
    authority_for,
    can_corroborate,
    can_originate,
    classify_alumni_source,
    is_excluded,
)

# --- Origination: the strongest control ------------------------------------


def test_only_the_four_strong_classes_can_originate_a_person() -> None:
    """A search snippet must not be able to mint a human being."""
    assert ORIGINATING_CLASSES == {
        UNIVERSITY_OFFICIAL,
        UNIVERSITY_ALUMNI_PAGE,
        COMPANY_OFFICIAL,
        PROFESSIONAL_ORG,
    }


@pytest.mark.parametrize(
    "weak", [REPUTABLE_PUBLICATION, PUBLIC_PROFILE, AGGREGATOR, EXCLUDED]
)
def test_weak_classes_cannot_originate(weak: str) -> None:
    assert can_originate(weak) is False


@pytest.mark.parametrize("weak", [REPUTABLE_PUBLICATION, PUBLIC_PROFILE, AGGREGATOR])
def test_weak_classes_may_still_corroborate(weak: str) -> None:
    """Attribution beats deletion — the Phase 2 audit lesson, reapplied."""
    assert can_corroborate(weak) is True


def test_an_unknown_class_can_do_nothing() -> None:
    assert can_originate("something_new") is False
    assert can_corroborate("something_new") is False
    assert authority_for("something_new", PROGRAM) == REFUSE


# --- Authority is per field, not per source --------------------------------


def test_a_university_verifies_the_academic_record() -> None:
    for field in (UNIVERSITY_AFFILIATION, PROGRAM, DEGREE, GRADUATION_YEAR):
        assert authority_for(UNIVERSITY_OFFICIAL, field) == VERIFY, field


def test_a_university_only_reports_where_someone_works() -> None:
    """Its employer line is historical: true when published, unknown now."""
    assert authority_for(UNIVERSITY_OFFICIAL, EMPLOYER) == REPORT
    assert authority_for(UNIVERSITY_OFFICIAL, ROLE) == REPORT


def test_a_company_verifies_employment_and_not_the_degree() -> None:
    assert authority_for(COMPANY_OFFICIAL, EMPLOYER) == VERIFY
    assert authority_for(COMPANY_OFFICIAL, ROLE) == VERIFY
    assert authority_for(COMPANY_OFFICIAL, PROGRAM) == REPORT
    assert authority_for(COMPANY_OFFICIAL, UNIVERSITY_AFFILIATION) == REPORT


def test_no_source_may_originate_a_graduation_year_it_cannot_know() -> None:
    """Per the approved Stage 0 table."""
    assert authority_for(COMPANY_OFFICIAL, GRADUATION_YEAR) == REFUSE
    assert authority_for(PROFESSIONAL_ORG, GRADUATION_YEAR) == REFUSE


def test_a_conference_verifies_nothing() -> None:
    """An affiliation there is dated by the event, never current."""
    for field in ALL_FIELD_NAMES:
        assert authority_for(PROFESSIONAL_ORG, field) != VERIFY, field


def test_weak_sources_verify_nothing_at_all() -> None:
    for source in (REPUTABLE_PUBLICATION, PUBLIC_PROFILE, AGGREGATOR):
        for field in ALL_FIELD_NAMES:
            assert authority_for(source, field) != VERIFY, (source, field)


def test_the_excluded_class_refuses_every_field() -> None:
    for field in ALL_FIELD_NAMES:
        assert authority_for(EXCLUDED, field) == REFUSE, field


def test_every_class_has_an_authority_verdict_for_every_field() -> None:
    """No field may fall through the table into an accidental default."""
    for source in SOURCE_CLASSES:
        for field in ALL_FIELD_NAMES:
            assert authority_for(source, field) in (VERIFY, REPORT, REFUSE)


def test_the_two_registries_agree_on_field_names() -> None:
    """`source_authority` names fields as literals; drift must not be silent."""
    assert set(ALL_FIELD_NAMES) == {
        UNIVERSITY_AFFILIATION,
        PROGRAM,
        DEGREE,
        GRADUATION_YEAR,
        EMPLOYER,
        ROLE,
        "prior_institution",
        "prior_degree",
    }


# --- LinkedIn is link-only, permanently ------------------------------------


@pytest.mark.parametrize(
    "domain",
    ["linkedin.com", "www.linkedin.com", "uk.linkedin.com", "lnkd.in"],
)
def test_linkedin_is_excluded(domain: str) -> None:
    assert is_excluded(domain) is True
    assert classify_alumni_source(domain)["source_class"] == EXCLUDED


def test_linkedin_cannot_even_corroborate() -> None:
    """Scraping it violates its terms; nothing is taken from the page."""
    assert can_corroborate(EXCLUDED) is False


def test_an_ordinary_domain_is_not_excluded() -> None:
    assert is_excluded("tudelft.nl") is False


# --- Classification --------------------------------------------------------


def test_an_academic_domain_is_a_university_source() -> None:
    assert classify_alumni_source("mit.edu")["source_class"] == UNIVERSITY_OFFICIAL
    assert classify_alumni_source("ethz.ch")["source_class"] == UNIVERSITY_OFFICIAL


def test_an_alumni_story_path_is_recognised() -> None:
    result = classify_alumni_source("mit.edu", url="https://mit.edu/alumni/stories/x")
    assert result["source_class"] == UNIVERSITY_ALUMNI_PAGE


def test_a_known_professional_body_is_classified() -> None:
    assert classify_alumni_source("acm.org")["source_class"] == PROFESSIONAL_ORG
    assert classify_alumni_source("neurips.cc")["source_class"] == PROFESSIONAL_ORG


def test_a_known_publication_is_classified() -> None:
    assert classify_alumni_source("nature.com")["source_class"] == REPUTABLE_PUBLICATION


def test_a_known_aggregator_stays_an_aggregator() -> None:
    assert classify_alumni_source("shiksha.com")["source_class"] == AGGREGATOR


def test_an_unrecognised_domain_defaults_to_something_that_cannot_originate() -> None:
    """The fail-safe: a domain we cannot place cannot create a person."""
    result = classify_alumni_source("some-random-blog.example")
    assert result["source_class"] == PUBLIC_PROFILE
    assert can_originate(str(result["source_class"])) is False


# --- company_official requires the domain to *be* the employer -------------


def test_a_company_domain_matching_the_claimed_employer_is_official() -> None:
    result = classify_alumni_source("booking.com", claimed_employer="Booking.com")
    assert result["source_class"] == COMPANY_OFFICIAL


def test_a_subdomain_of_the_employer_still_counts() -> None:
    result = classify_alumni_source("careers.booking.com", claimed_employer="Booking")
    assert result["source_class"] == COMPANY_OFFICIAL


def test_a_lookalike_domain_does_not_verify_an_employer() -> None:
    """A loose match would let anyone who registers a domain verify anyone."""
    result = classify_alumni_source(
        "booking-reviews.example", claimed_employer="Booking"
    )
    assert result["source_class"] != COMPANY_OFFICIAL


def test_without_a_claimed_employer_no_domain_is_a_company_source() -> None:
    """There is no deterministic way to recognise a company site unaided."""
    assert classify_alumni_source("booking.com")["source_class"] != COMPANY_OFFICIAL


def test_a_very_short_employer_token_cannot_match() -> None:
    assert (
        classify_alumni_source("hp.com", claimed_employer="HP")["source_class"]
        != COMPANY_OFFICIAL
    )


def test_an_academic_domain_is_never_reclassified_as_a_company() -> None:
    result = classify_alumni_source("mit.edu", claimed_employer="MIT")
    assert result["source_class"] == UNIVERSITY_OFFICIAL


def test_classification_is_deterministic() -> None:
    for _ in range(50):
        assert (
            classify_alumni_source("mit.edu", claimed_employer="MIT")["source_class"]
            == UNIVERSITY_OFFICIAL
        )


def test_an_unreadable_domain_is_handled() -> None:
    result = classify_alumni_source("")
    assert result["source_class"] == PUBLIC_PROFILE
    assert result["reason"] == "domain_unreadable"


def test_every_classification_carries_a_reason_and_ruleset() -> None:
    for domain in ("mit.edu", "acm.org", "shiksha.com", "unknown.example", ""):
        result = classify_alumni_source(domain)
        assert result["reason"]
        assert result["ruleset"]
