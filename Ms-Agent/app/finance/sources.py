"""The finance source registry — metadata and strategies, never values.

Financial information is unusually sensitive to source quality (§8 of the
Phase 7 brief), so every source category carries its authority level and
the claim types it is allowed to make. What the registry deliberately does
NOT carry is any number: a tuition figure or living cost in this file
would be a static finance database, which the architecture forbids (§3) —
a structural test asserts the registry is digit-free.
"""

from __future__ import annotations

from typing import Any

from app.services.research_service import classify_source, normalize_domain

# Government portals that carry no .gov marker in the domain itself.
_GOVERNMENT_SUFFIXES = ("gc.ca", "canada.ca", "europa.eu", "gov.uk", "gov.in")

# Established cost-of-living datasets: useful benchmarks, never verifiers —
# a market survey cannot confirm what a student will actually pay.
COST_OF_LIVING_DOMAINS = ("numbeo.com", "expatistan.com", "livingcost.org")

# Source categories, their standing, and how to search them. Authority
# levels: primary (official / government), institutional (official arms of
# an institution), secondary (established datasets and publications),
# community (context only).
FINANCE_SOURCE_REGISTRY: tuple[dict[str, Any], ...] = (
    {
        "source_name": "University fee and funding pages",
        "source_type": "university",
        "authority_level": "primary",
        "allowed_claim_types": (
            "tuition",
            "mandatory_fees",
            "billing_structure",
            "living_cost_estimate",
            "housing_cost",
            "health_insurance_cost",
            "application_fee",
            "deposit",
            "scholarships",
            "assistantship_evidence",
            "funding_evidence",
        ),
        "search_strategy": (
            "site:<university domain> graduate tuition fees / graduate "
            "funding / student housing / cost of attendance"
        ),
    },
    {
        "source_name": "Government immigration authorities",
        "source_type": "government",
        "authority_level": "primary",
        "allowed_claim_types": (
            "visa_financial_requirement",
            "part_time_work_rules",
        ),
        "search_strategy": (
            "the target country's official immigration site (study permit "
            "proof of funds, off-campus work rules)"
        ),
    },
    {
        "source_name": "Government statistics and labour agencies",
        "source_type": "government",
        "authority_level": "primary",
        "allowed_claim_types": ("living_cost", "salary_evidence"),
        "search_strategy": "the national statistics agency's cost and wage data",
    },
    {
        "source_name": "Official scholarship providers",
        "source_type": "scholarship_provider",
        "authority_level": "primary",
        "allowed_claim_types": ("external_scholarships",),
        "search_strategy": (
            "the provider's own eligibility and award pages, never a "
            "listicle's summary of them"
        ),
    },
    {
        "source_name": "Loan providers' official documentation",
        "source_type": "loan_provider",
        "authority_level": "primary",
        "allowed_claim_types": ("loan_terms", "interest_rate"),
        "search_strategy": (
            "the lender's own education-loan pages: eligibility, "
            "collateral, moratorium, current rates"
        ),
    },
    {
        "source_name": "Official insurance providers",
        "source_type": "insurance_provider",
        "authority_level": "primary",
        "allowed_claim_types": ("health_insurance",),
        "search_strategy": (
            "the university's mandated plan first, then the provider's "
            "own premium pages"
        ),
    },
    {
        "source_name": "University and official housing providers",
        "source_type": "housing_provider",
        "authority_level": "institutional",
        "allowed_claim_types": ("housing",),
        "search_strategy": (
            "the university housing office and official residence "
            "providers; never assume availability or guarantee placement"
        ),
    },
    {
        "source_name": "Established cost-of-living datasets",
        "source_type": "cost_of_living",
        "authority_level": "secondary",
        "allowed_claim_types": (
            "living_cost",
            "housing",
            "food",
            "transport",
            "utilities",
        ),
        "search_strategy": (
            "recognized cost-of-living datasets for the specific city — "
            "they report market figures, they never verify them"
        ),
    },
    {
        "source_name": "Established education publications",
        "source_type": "education_publication",
        "authority_level": "secondary",
        "allowed_claim_types": ("external_scholarships", "funding_evidence"),
        "search_strategy": "recognized education press for funding round-ups",
    },
    {
        "source_name": "Community experience (forums, blogs, video)",
        "source_type": "community",
        "authority_level": "community",
        "allowed_claim_types": ("lived_experience_context",),
        "search_strategy": (
            "context on real student experience only — never overrides an "
            "official figure, never establishes a rule or a fee"
        ),
    },
)


def classify_finance_source(
    domain: str, university_website: str = ""
) -> dict[str, Any]:
    """Which finance authority tier does this domain sit in?"""
    flat = normalize_domain(domain)
    if any(flat == g or flat.endswith("." + g) for g in _GOVERNMENT_SUFFIXES):
        return {"source_type": "government", "authority_level": 1}
    if any(flat == d or flat.endswith("." + d) for d in COST_OF_LIVING_DOMAINS):
        return {"source_type": "cost_of_living", "authority_level": 3}
    base = classify_source(flat, university_website)
    level = {"official": 1, "government": 1, "aggregator": 3, "community": 4}.get(
        base, 3
    )
    return {"source_type": base, "authority_level": level}
