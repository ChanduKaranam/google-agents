"""Build search links the student opens themselves.

Public web search cannot answer "who from college X works at company Y" --
measured across Stripe, Google and Microsoft, it returns nothing verifiable.
That data lives on LinkedIn, and LinkedIn is closed to us: no people-search API
at any tier, and robots.txt is `User-agent: * / Disallow: /`.

But the student is a logged-in LinkedIn member, and LinkedIn's own alumni view
answers this question well. So when our own search comes up empty, we hand the
student a link instead of nothing.

This module builds URL strings. It fetches nothing, stores nothing, and
processes no personal data -- the student opens the link under their own
account, which is ordinary use of a feature built for exactly this.
"""

from urllib.parse import quote_plus


def alumni_search_links(college: str, company: str, role: str = "") -> dict:
    """Build links the student can open to find alumni themselves.

    Use this whenever alumni_agent finds no verifiable contacts, so the
    student leaves with a route forward rather than a dead end.

    Args:
      college: The student's college, e.g. "National Institute of Technology
        Warangal" or "BITS Pilani". Pass it as written on their resume.
      company: The target company, e.g. "Zerodha", "Swiggy" or "Google".
      role: Optional role to narrow by, e.g. "Machine Learning Engineer".

    Returns:
      Links plus a short note on what the student will see.
    """
    college = (college or "").strip()
    company = (company or "").strip()
    if not college or not company:
        return {"error": "Both college and company are needed to build a search link."}

    # People search with both terms as keywords. Deliberately NOT the
    # /school/<slug>/people URL: that needs LinkedIn's own school slug, which
    # we cannot reliably derive from a college name and which 404s when wrong.
    # Keyword search needs no slug and works for any institution.
    people = ("https://www.linkedin.com/search/results/people/?keywords="
              + quote_plus(f"{college} {company}"))
    if role:
        people_role = ("https://www.linkedin.com/search/results/people/?keywords="
                       + quote_plus(f"{college} {company} {role}"))
    else:
        people_role = None

    # The alumni view proper, reached via the school page. The student picks
    # their school from this search, then uses the "Where they work" filter.
    school = ("https://www.linkedin.com/search/results/schools/?keywords="
              + quote_plus(college))

    return {
        "people_search": people,
        "people_search_with_role": people_role,
        "school_page_search": school,
        "how_to_use": (
            "Open the people search to see alumni of the college who mention"
            " the company. For a fuller list, open the school page search,"
            " click the college, open its People tab, and use the 'Where they"
            " work' filter -- that view is built from current profiles and is"
            " more complete than any public web search."
        ),
        "note_for_agent": (
            "Give these to the student as clickable links. Do NOT attempt to"
            " fetch them yourself -- automated access to LinkedIn is"
            " prohibited. Ask the student to tell you a few facts about anyone"
            " they find (name, role, batch, what you share) and continue from"
            " there; they do not need to paste a whole profile."
        ),
    }


if __name__ == "__main__":
    out = alumni_search_links("National Institute of Technology Warangal", "Stripe")
    assert out["people_search"].startswith("https://www.linkedin.com/search/results/people/")
    assert "Warangal" in out["people_search"] and "Stripe" in out["people_search"]
    assert "%2F" not in out["people_search"], "college/company must not be path-escaped"
    assert alumni_search_links("", "Stripe").get("error")
    assert alumni_search_links("NITW", "").get("error")
    print(out["people_search"])
    print(out["school_page_search"])
    print("\nok")
