"""The 26-source allowlisted research ecosystem for alumni intelligence.

The absolute rule (§2, §46 of the alumni brief): a domain outside this
registry does not exist for alumni research. Google is the discovery
mechanism, never a source — results are validated by domain before any
claim built on them can be stored, and an unknown domain is discarded, not
downgraded.

Three tiers (§5):
  1 AUTHORITATIVE  — university/government/company official pages
  2 STRONG_SECONDARY — rankings and scholarly indexes
  3 PROFESSIONAL_COMMUNITY — public professional/community platforms

Tier decides what a source may establish; the validator only decides
whether it may be used at all. University and company official domains are
dynamic (per §1/§20): they are recognized by the caller passing the known
official domains for the universities/companies under research.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.services.research_service import normalize_domain

TIER_AUTHORITATIVE = 1
TIER_STRONG_SECONDARY = 2
TIER_PROFESSIONAL_COMMUNITY = 3


@dataclass(frozen=True)
class AlumniSource:
    key: str
    label: str
    tier: int
    domains: tuple[str, ...] = ()  # empty → dynamic (university/company)
    api_env: tuple[str, ...] = ()  # optional API credentials, by env var
    purpose: str = ""


# The production registry: exactly the 26 logical source categories.
ALUMNI_SOURCES: tuple[AlumniSource, ...] = (
    # --- University / official (dynamic domains) ---------------------------
    AlumniSource(
        "university_official",
        "University official website",
        1,
        purpose="alumni pages, outcomes, announcements",
    ),
    AlumniSource(
        "university_alumni",
        "University alumni association",
        1,
        purpose="alumni stories, public directories",
    ),
    AlumniSource(
        "university_career_services",
        "University career services",
        1,
        purpose="employment reports, employer lists",
    ),
    AlumniSource(
        "university_department",
        "University department/program pages",
        1,
        purpose="program alumni, research connections",
    ),
    AlumniSource(
        "university_newsroom",
        "University newsroom",
        1,
        purpose="alumni success stories, placements",
    ),
    # --- Professional / community ------------------------------------------
    AlumniSource(
        "linkedin",
        "LinkedIn (public profiles)",
        3,
        ("linkedin.com",),
        purpose="public roles, companies, paths",
    ),
    AlumniSource(
        "github",
        "GitHub (public)",
        3,
        ("github.com", "github.io"),
        ("GITHUB_TOKEN",),
        "public repos, skills, open source",
    ),
    AlumniSource(
        "reddit",
        "Reddit (public)",
        3,
        ("reddit.com",),
        ("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET"),
        "student/alumni experience, qualitative only",
    ),
    AlumniSource(
        "glassdoor",
        "Glassdoor",
        3,
        ("glassdoor.com", "glassdoor.ca"),
        purpose="employee-reported employer signals",
    ),
    AlumniSource(
        "indeed",
        "Indeed",
        3,
        ("indeed.com", "ca.indeed.com"),
        purpose="job-market signals",
    ),
    AlumniSource(
        "wellfound",
        "Wellfound",
        3,
        ("wellfound.com", "angel.co"),
        purpose="startup ecosystem signals",
    ),
    AlumniSource(
        "levels_fyi",
        "Levels.fyi",
        3,
        ("levels.fyi",),
        purpose="compensation signals, never university-specific",
    ),
    AlumniSource(
        "crunchbase",
        "Crunchbase",
        3,
        ("crunchbase.com",),
        purpose="founders, funding, company affiliations",
    ),
    # --- Research / publications -------------------------------------------
    AlumniSource(
        "google_scholar",
        "Google Scholar",
        2,
        ("scholar.google.com",),
        purpose="publications, research areas",
    ),
    AlumniSource(
        "semantic_scholar",
        "Semantic Scholar",
        2,
        ("semanticscholar.org",),
        ("SEMANTIC_SCHOLAR_API_KEY",),
        "publications, citations",
    ),
    AlumniSource(
        "openalex",
        "OpenAlex",
        2,
        ("openalex.org",),
        ("OPENALEX_EMAIL",),
        "authors, institutions",
    ),
    AlumniSource(
        "crossref",
        "Crossref",
        2,
        ("crossref.org",),
        ("CROSSREF_EMAIL",),
        "publication metadata",
    ),
    AlumniSource(
        "orcid",
        "ORCID",
        2,
        ("orcid.org",),
        ("ORCID_CLIENT_ID", "ORCID_CLIENT_SECRET"),
        "public researcher profiles",
    ),
    AlumniSource(
        "researchgate",
        "ResearchGate (public)",
        3,
        ("researchgate.net",),
        purpose="research activity",
    ),
    # --- Company / career (official domains dynamic) -----------------------
    AlumniSource(
        "company_official",
        "Company official websites",
        1,
        purpose="team pages, leadership bios, announcements",
    ),
    AlumniSource(
        "company_careers",
        "Company careers pages",
        1,
        purpose="roles, skills, locations",
    ),
    AlumniSource(
        "government_labour",
        "Government / public labour data",
        1,
        ("canada.ca", "bls.gov", "ec.europa.eu", "ons.gov.uk"),
        purpose="employment statistics",
    ),
    # --- Education / ranking / outcomes ------------------------------------
    AlumniSource(
        "qs",
        "QS",
        2,
        ("topuniversities.com",),
        purpose="rankings, employer reputation signals",
    ),
    AlumniSource(
        "times_higher_education",
        "Times Higher Education",
        2,
        ("timeshighereducation.com",),
        purpose="rankings, indicators",
    ),
    AlumniSource(
        "macleans",
        "Maclean's",
        2,
        ("macleans.ca",),
        purpose="Canadian university context",
    ),
    AlumniSource(
        "statistics_canada",
        "Statistics Canada",
        1,
        ("statcan.gc.ca",),
        purpose="graduate outcomes, labour data",
    ),
)

ALLOWED_SOURCES: frozenset[str] = frozenset(s.key for s in ALUMNI_SOURCES)

_BY_KEY = {s.key: s for s in ALUMNI_SOURCES}

# Static domain → source key, for every fixed-domain source.
_STATIC_DOMAINS: dict[str, str] = {
    domain: source.key for source in ALUMNI_SOURCES for domain in source.domains
}


@dataclass
class DynamicDomains:
    """The per-investigation official domains (§1: identified dynamically).

    University domains map to the university_* categories; company domains
    to company_official. The caller supplies them from what is already
    known (e.g. the program's `program_url` or a prior research round).
    """

    university_domains: tuple[str, ...] = field(default_factory=tuple)
    company_domains: tuple[str, ...] = field(default_factory=tuple)


def identify_source(domain: str, dynamic: DynamicDomains | None = None) -> str | None:
    """Map a domain to its allowlisted source key, or None → NOT allowed."""
    d = normalize_domain(domain)
    if not d:
        return None
    dyn = dynamic or DynamicDomains()
    for site in dyn.university_domains:
        s = normalize_domain(site)
        if s and (d == s or d.endswith("." + s)):
            return "university_official"
    for site in dyn.company_domains:
        s = normalize_domain(site)
        if s and (d == s or d.endswith("." + s)):
            return "company_official"
    for static, key in _STATIC_DOMAINS.items():
        if d == static or d.endswith("." + static):
            return key
    return None


def is_allowed(domain: str, dynamic: DynamicDomains | None = None) -> bool:
    return identify_source(domain, dynamic) is not None


def tier_of(source_key: str) -> int:
    return _BY_KEY[source_key].tier


def source_label(source_key: str) -> str:
    return _BY_KEY[source_key].label


def api_status(env: dict[str, str]) -> dict[str, dict[str, object]]:
    """Which sources have optional API support, and whether credentials are
    present. Reports presence only — never the values (§7)."""
    return {
        s.key: {
            "api_supported": bool(s.api_env),
            "credentials_present": all(bool(env.get(k)) for k in s.api_env)
            if s.api_env
            else False,
            "fallback": "public web via grounded search",
        }
        for s in ALUMNI_SOURCES
        if s.api_env
    }
