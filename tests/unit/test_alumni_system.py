"""The alumni intelligence system: registry, gate, resolution, analysis."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import ValidationError

from app.alumni.analysis import analyze_group, categorize_company, similarity
from app.alumni.entity_resolution import (
    identity_key,
    normalize_name,
    resolve_alumni_identity,
)
from app.alumni.models import ALUMNI_FIELDS, AlumniClaim, AlumniRecord
from app.alumni.source_registry import (
    ALLOWED_SOURCES,
    ALUMNI_SOURCES,
    DynamicDomains,
    api_status,
    identify_source,
    is_allowed,
    tier_of,
)
from app.config.settings import STATE_ALUMNI, STATE_EVIDENCE, STATE_PROFILE
from app.models.student import StudentProfile
from app.tools.alumni_tools import get_alumni_signals, save_alumni_findings

# --- The 26-source registry -------------------------------------------------


def test_the_registry_holds_exactly_the_26_sources() -> None:
    assert len(ALUMNI_SOURCES) == 26
    assert len(ALLOWED_SOURCES) == 26


def test_every_source_has_a_tier_and_purpose() -> None:
    for source in ALUMNI_SOURCES:
        assert source.tier in (1, 2, 3), source.key
        assert source.purpose, source.key


def test_static_domains_resolve_to_their_source() -> None:
    assert identify_source("linkedin.com") == "linkedin"
    assert identify_source("www.linkedin.com/in/someone") == "linkedin"
    assert identify_source("scholar.google.com") == "google_scholar"
    assert identify_source("statcan.gc.ca") == "statistics_canada"
    assert identify_source("crunchbase.com") == "crunchbase"


def test_unknown_domains_are_rejected_outright() -> None:
    assert identify_source("randomblog.com") is None
    assert identify_source("wikipedia.org") is None
    assert identify_source("medium.com") is None
    assert identify_source("quora.com") is None
    assert not is_allowed("someseosite.io")


def test_university_domains_are_dynamic() -> None:
    dynamic = DynamicDomains(university_domains=("utoronto.ca",))
    assert identify_source("utoronto.ca", dynamic) == "university_official"
    assert identify_source("web.cs.utoronto.ca", dynamic) == "university_official"
    assert identify_source("utoronto.ca") is None  # without the hint: rejected


def test_tiers_follow_the_hierarchy() -> None:
    assert tier_of("university_official") == 1
    assert tier_of("statistics_canada") == 1
    assert tier_of("google_scholar") == 2
    assert tier_of("qs") == 2
    assert tier_of("linkedin") == 3
    assert tier_of("reddit") == 3


def test_api_status_reports_presence_never_values() -> None:
    status = api_status({"GITHUB_TOKEN": "secret-token-value"})
    assert status["github"]["credentials_present"] is True
    assert status["reddit"]["credentials_present"] is False
    assert "secret-token-value" not in str(status)


# --- Privacy is structural --------------------------------------------------


def test_contact_details_cannot_exist_in_a_claim() -> None:
    with pytest.raises(ValidationError):
        AlumniClaim(
            field="role",
            value="engineer, reach me at x@y.com",
            source_domain="linkedin.com",
        )


def test_sensitive_fields_do_not_exist_in_the_registry() -> None:
    for banned in ("religion", "ethnicity", "health", "politics", "salary"):
        assert banned not in ALUMNI_FIELDS
    with pytest.raises(ValidationError):
        AlumniClaim(field="religion", value="x", source_domain="linkedin.com")


# --- Entity resolution ------------------------------------------------------


def record(
    name: str,
    year: str | None = None,
    company: str | None = None,
    source: str = "linkedin",
) -> AlumniRecord:
    from app.alumni.models import StoredClaim, StoredEvidence

    claims = {}
    evidence = StoredEvidence(
        source_key=source,
        source_label=source,
        source_domain=f"{source}.com",
        tier=3 if source == "linkedin" else 1,
        retrieved_at="2026-08-10T00:00:00Z",
    )
    if year:
        claims["graduation_year"] = StoredClaim(value=year, evidence=evidence)
    if company:
        claims["company"] = StoredClaim(value=company, evidence=evidence)
    return AlumniRecord(
        name=name,
        university="University of Toronto",
        claims=claims,
        source_keys=[source],
    )


def test_name_normalization_handles_case_and_diacritics() -> None:
    assert normalize_name("  Anna  DE Vries ") == "anna de vries"
    assert normalize_name("José García") == "jose garcia"
    assert identity_key("Anna de Vries", "TU Delft") == "anna de vries::tu delft"


def test_multi_source_appearances_merge_into_one_entity() -> None:
    store: dict[str, Any] = {}
    store, first = resolve_alumni_identity(
        store, record("Priya Sharma", company="Google")
    )
    store, second = resolve_alumni_identity(
        store, record("Priya Sharma", year="2022", source="university_official")
    )
    assert (first, second) == ("new", "merged")
    assert len(store) == 1
    merged = AlumniRecord.model_validate(next(iter(store.values())))
    assert set(merged.source_keys) == {"linkedin", "university_official"}
    assert merged.evidence_strength == "strong"  # two independent sources


def test_conflicting_graduation_years_split_namesakes() -> None:
    store: dict[str, Any] = {}
    store, _ = resolve_alumni_identity(store, record("Bob Smith", year="2019"))
    store, outcome = resolve_alumni_identity(store, record("Bob Smith", year="2022"))
    assert outcome == "namesake_split"
    assert len(store) == 2
    records = [AlumniRecord.model_validate(r) for r in store.values()]
    assert any(r.possible_namesake_of for r in records)


def test_a_changed_company_is_a_reported_conflict_not_a_choice() -> None:
    store: dict[str, Any] = {}
    store, _ = resolve_alumni_identity(store, record("Priya Sharma", company="Google"))
    store, outcome = resolve_alumni_identity(
        store, record("Priya Sharma", company="NVIDIA", source="university_official")
    )
    assert outcome == "merged"
    merged = AlumniRecord.model_validate(next(iter(store.values())))
    company = merged.claims["company"]
    assert company.value == "Google"
    assert company.conflicts[0]["value"] == "NVIDIA"


# --- Analysis: denominators and pattern gating ------------------------------


def test_small_groups_forbid_pattern_language() -> None:
    result = analyze_group(
        [record("A B", company="Google"), record("C D", company="Meta")]
    )
    assert result["profiles_found"] == 2
    assert result["may_use_pattern_language"] is False
    assert result["coverage_note"]


def test_aggregates_carry_denominators() -> None:
    result = analyze_group([record("A B", company="Google")])
    assert result["research_active"] == {"count": 0, "of": 1}
    assert result["phd_transitions"]["of"] == 1


def test_company_categorization() -> None:
    assert categorize_company("Google DeepMind") in ("big_tech", "ai_companies")
    assert categorize_company("NVIDIA Corporation") == "big_tech"
    assert categorize_company("Local Shop Inc") == "other"


def test_similarity_is_anchored_and_never_probabilistic() -> None:
    from app.alumni.models import StoredClaim, StoredEvidence

    profile = StudentProfile.model_validate(
        {
            "technical": {"skills": ["Python", "PyTorch", "NLP"]},
            "education": {"major": "CSE"},
            "target": {"specialization": "AI/ML", "career_goal": "ML Engineer"},
        }
    )
    evidence = StoredEvidence(
        source_key="linkedin",
        source_label="LinkedIn",
        source_domain="linkedin.com",
        tier=3,
    )
    alumnus = AlumniRecord(
        name="R K",
        university="U",
        source_keys=["linkedin"],
        claims={
            "skills": StoredClaim(value="Python, PyTorch", evidence=evidence),
            "role": StoredClaim(value="Machine Learning Engineer", evidence=evidence),
        },
    )
    result = similarity(profile, alumnus)
    assert result["band"] in ("strong", "moderate")
    assert result["anchors"]
    rendered = str(result).lower()
    assert "%" not in rendered
    assert "probability" not in rendered or "never" in rendered


# --- The admission gate -----------------------------------------------------


class StubToolContext:
    def __init__(self) -> None:
        self.state: dict[str, Any] = {}
        self.invocation_id = "test"
        self.session = SimpleNamespace(events=[])


@pytest.fixture
def context() -> StubToolContext:
    ctx = StubToolContext()
    ctx.state[STATE_EVIDENCE] = [
        {
            "domain": "linkedin.com",
            "uris": ["https://x/li"],
            "titles": ["linkedin.com"],
            "segments": [
                "Priya Sharma, University of Toronto MSc Computer Science, "
                "works as an ML Engineer at NVIDIA in Toronto."
            ],
        },
        {
            "domain": "randomblog.com",
            "uris": ["https://x/blog"],
            "titles": ["randomblog.com"],
            "segments": ["Rahul Verma graduated from the University of Toronto."],
        },
    ]
    return ctx


def finding(name: str, field: str, value: str, domain: str) -> dict:
    return {
        "name": name,
        "university": "University of Toronto",
        "claims": [{"field": field, "value": value, "source_domain": domain}],
    }


def test_an_allowlisted_named_person_is_admitted(context: StubToolContext) -> None:
    result = save_alumni_findings(
        "University of Toronto",
        "utoronto.ca",
        [finding("Priya Sharma", "role", "ML Engineer", "linkedin.com")],
        context,
    )
    assert result["status"] == "success"
    assert result["admitted"][0]["evidence_strength"] in ("weak", "moderate", "strong")
    assert result["rejected"] == []


def test_an_unapproved_source_is_discarded_even_when_it_names_the_person(
    context: StubToolContext,
) -> None:
    """randomblog.com genuinely retrieved AND names Rahul — still rejected."""
    result = save_alumni_findings(
        "University of Toronto",
        "utoronto.ca",
        [finding("Rahul Verma", "program", "MSc", "randomblog.com")],
        context,
    )
    assert result["admitted"] == []
    refusal = result["rejected"][0]
    assert refusal["reason"] == "no_supported_claims"
    assert refusal["claim_refusals"][0]["reason"] == "source_not_allowlisted"


def test_a_person_no_source_names_is_never_stored(context: StubToolContext) -> None:
    result = save_alumni_findings(
        "University of Toronto",
        "utoronto.ca",
        [finding("Invented Person", "role", "CTO", "linkedin.com")],
        context,
    )
    assert result["admitted"] == []
    assert result["rejected"][0]["claim_refusals"][0]["reason"] == (
        "name_not_in_retrieved_text"
    )
    assert STATE_ALUMNI in context.state
    assert context.state[STATE_ALUMNI] == {}


def test_nothing_retrieved_means_nothing_recorded(context: StubToolContext) -> None:
    context.state[STATE_EVIDENCE] = []
    result = save_alumni_findings(
        "U",
        "u.ca",
        [finding("Priya Sharma", "role", "ML Engineer", "linkedin.com")],
        context,
    )
    assert result["reason"] == "no_sources_retrieved"


def test_signals_render_with_freshness_and_rules(context: StubToolContext) -> None:
    context.state[STATE_PROFILE] = StudentProfile.model_validate(
        {"target": {"career_goal": "ML Engineer"}}
    ).model_dump()
    save_alumni_findings(
        "University of Toronto",
        "utoronto.ca",
        [finding("Priya Sharma", "role", "ML Engineer", "linkedin.com")],
        context,
    )
    signals = get_alumni_signals(context)
    university = signals["universities"]["University of Toronto"]
    person = university["people"][0]
    assert person["facts"]["role"]["retrieved_at"]
    assert person["facts"]["role"]["source"] == "LinkedIn (public profiles)"
    assert university["analysis"]["may_use_pattern_language"] is False
    assert signals["closest_to_student"]  # ML Engineer goal matches
    assert "denominator" in signals["presentation_rules"].casefold() or (
        "counts" in signals["presentation_rules"].casefold()
    )
