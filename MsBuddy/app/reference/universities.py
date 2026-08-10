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

"""A small curated university reference dataset.

Reference data in the same spirit as `gpa_scales.py`: a starting point for
*discovery* — "which well-known universities teach my subject in my target
country, and roughly how competitive are they" — not a source of facts.

What it deliberately does NOT contain, enforced by
`tests/unit/test_universities_reference.py`:

* **No deadlines, no fees, no dates.** Those rot, and a rotted value served
  confidently is the exact failure C2 exists to prevent. Anything current is
  researched and verified through `save_program_record`.
* **No people.** Alumni claims go through C4's verification gate, always.
* **No rankings.** A number implies a source and a year; we have neither.

The `typical_*` fields are approximate historical norms for competitive
applicants, kept only so the deterministic fit assessment in `app/fit.py`
has something transparent to compare a profile against. Every consumer must
carry `TYPICAL_DISCLAIMER` alongside them.
"""

from __future__ import annotations

from typing import Any

COMPETITIVENESS_LEVELS = frozenset(
    {"highly_competitive", "competitive", "moderately_competitive"}
)

TYPICAL_DISCLAIMER = (
    "These are typical historical norms for competitive applicants, not "
    "current or official admission requirements. Requirements change; the "
    "current figures for any program must come from research with sources."
)

# name, country, city, popular MS programs, competitiveness tier, typical
# successful-applicant GPA on a US 4.0 scale, typical IELTS overall, GRE
# policy, intakes, official website. Nothing else — see the module docstring.
UNIVERSITIES: list[dict[str, Any]] = [
    {
        "name": "Massachusetts Institute of Technology",
        "country": "USA",
        "city": "Cambridge",
        "programs": [
            "Computer Science",
            "Electrical Engineering",
            "Mechanical Engineering",
        ],
        "competitiveness": "highly_competitive",
        "typical_gpa_4pt": 3.8,
        "typical_ielts": 7.0,
        "gre_policy": "varies_by_program",
        "intakes": ["fall"],
        "website": "https://www.mit.edu",
    },
    {
        "name": "Stanford University",
        "country": "USA",
        "city": "Stanford",
        "programs": [
            "Computer Science",
            "Electrical Engineering",
            "Management Science",
        ],
        "competitiveness": "highly_competitive",
        "typical_gpa_4pt": 3.8,
        "typical_ielts": 7.0,
        "gre_policy": "varies_by_program",
        "intakes": ["fall"],
        "website": "https://www.stanford.edu",
    },
    {
        "name": "Carnegie Mellon University",
        "country": "USA",
        "city": "Pittsburgh",
        "programs": [
            "Computer Science",
            "Software Engineering",
            "Robotics",
            "Data Science",
        ],
        "competitiveness": "highly_competitive",
        "typical_gpa_4pt": 3.7,
        "typical_ielts": 7.0,
        "gre_policy": "varies_by_program",
        "intakes": ["fall", "spring"],
        "website": "https://www.cmu.edu",
    },
    {
        "name": "University of California, Berkeley",
        "country": "USA",
        "city": "Berkeley",
        "programs": ["Computer Science", "Electrical Engineering", "Data Science"],
        "competitiveness": "highly_competitive",
        "typical_gpa_4pt": 3.7,
        "typical_ielts": 7.0,
        "gre_policy": "varies_by_program",
        "intakes": ["fall"],
        "website": "https://www.berkeley.edu",
    },
    {
        "name": "Georgia Institute of Technology",
        "country": "USA",
        "city": "Atlanta",
        "programs": [
            "Computer Science",
            "Cybersecurity",
            "Analytics",
            "Aerospace Engineering",
        ],
        "competitiveness": "competitive",
        "typical_gpa_4pt": 3.5,
        "typical_ielts": 7.0,
        "gre_policy": "varies_by_program",
        "intakes": ["fall", "spring"],
        "website": "https://www.gatech.edu",
    },
    {
        "name": "University of Illinois Urbana-Champaign",
        "country": "USA",
        "city": "Urbana",
        "programs": ["Computer Science", "Electrical Engineering", "Civil Engineering"],
        "competitiveness": "competitive",
        "typical_gpa_4pt": 3.5,
        "typical_ielts": 6.5,
        "gre_policy": "varies_by_program",
        "intakes": ["fall", "spring"],
        "website": "https://illinois.edu",
    },
    {
        "name": "University of Texas at Austin",
        "country": "USA",
        "city": "Austin",
        "programs": ["Computer Science", "Data Science", "Petroleum Engineering"],
        "competitiveness": "competitive",
        "typical_gpa_4pt": 3.5,
        "typical_ielts": 6.5,
        "gre_policy": "varies_by_program",
        "intakes": ["fall"],
        "website": "https://www.utexas.edu",
    },
    {
        "name": "Northeastern University",
        "country": "USA",
        "city": "Boston",
        "programs": ["Computer Science", "Information Systems", "Data Analytics"],
        "competitiveness": "moderately_competitive",
        "typical_gpa_4pt": 3.2,
        "typical_ielts": 6.5,
        "gre_policy": "often_optional",
        "intakes": ["fall", "spring"],
        "website": "https://www.northeastern.edu",
    },
    {
        "name": "Arizona State University",
        "country": "USA",
        "city": "Tempe",
        "programs": [
            "Computer Science",
            "Software Engineering",
            "Industrial Engineering",
        ],
        "competitiveness": "moderately_competitive",
        "typical_gpa_4pt": 3.0,
        "typical_ielts": 6.5,
        "gre_policy": "often_optional",
        "intakes": ["fall", "spring"],
        "website": "https://www.asu.edu",
    },
    {
        "name": "University of Toronto",
        "country": "Canada",
        "city": "Toronto",
        "programs": ["Computer Science", "Applied Computing", "Electrical Engineering"],
        "competitiveness": "highly_competitive",
        "typical_gpa_4pt": 3.6,
        "typical_ielts": 7.0,
        "gre_policy": "often_optional",
        "intakes": ["fall"],
        "website": "https://www.utoronto.ca",
    },
    {
        "name": "University of British Columbia",
        "country": "Canada",
        "city": "Vancouver",
        "programs": ["Computer Science", "Data Science", "Electrical Engineering"],
        "competitiveness": "competitive",
        "typical_gpa_4pt": 3.5,
        "typical_ielts": 6.5,
        "gre_policy": "often_optional",
        "intakes": ["fall"],
        "website": "https://www.ubc.ca",
    },
    {
        "name": "University of Waterloo",
        "country": "Canada",
        "city": "Waterloo",
        "programs": [
            "Computer Science",
            "Electrical and Computer Engineering",
            "Data Science",
        ],
        "competitiveness": "competitive",
        "typical_gpa_4pt": 3.6,
        "typical_ielts": 7.0,
        "gre_policy": "often_optional",
        "intakes": ["fall", "winter"],
        "website": "https://uwaterloo.ca",
    },
    {
        "name": "University of Oxford",
        "country": "UK",
        "city": "Oxford",
        "programs": ["Computer Science", "Advanced Computer Science", "Statistics"],
        "competitiveness": "highly_competitive",
        "typical_gpa_4pt": 3.7,
        "typical_ielts": 7.5,
        "gre_policy": "often_optional",
        "intakes": ["fall"],
        "website": "https://www.ox.ac.uk",
    },
    {
        "name": "University of Cambridge",
        "country": "UK",
        "city": "Cambridge",
        "programs": ["Advanced Computer Science", "Machine Learning", "Engineering"],
        "competitiveness": "highly_competitive",
        "typical_gpa_4pt": 3.7,
        "typical_ielts": 7.5,
        "gre_policy": "often_optional",
        "intakes": ["fall"],
        "website": "https://www.cam.ac.uk",
    },
    {
        "name": "Imperial College London",
        "country": "UK",
        "city": "London",
        "programs": ["Computing", "Artificial Intelligence", "Bioengineering"],
        "competitiveness": "highly_competitive",
        "typical_gpa_4pt": 3.6,
        "typical_ielts": 7.0,
        "gre_policy": "often_optional",
        "intakes": ["fall"],
        "website": "https://www.imperial.ac.uk",
    },
    {
        "name": "University of Edinburgh",
        "country": "UK",
        "city": "Edinburgh",
        "programs": ["Computer Science", "Artificial Intelligence", "Data Science"],
        "competitiveness": "competitive",
        "typical_gpa_4pt": 3.4,
        "typical_ielts": 7.0,
        "gre_policy": "often_optional",
        "intakes": ["fall"],
        "website": "https://www.ed.ac.uk",
    },
    {
        "name": "Technical University of Munich",
        "country": "Germany",
        "city": "Munich",
        "programs": ["Informatics", "Data Engineering and Analytics", "Robotics"],
        "competitiveness": "competitive",
        "typical_gpa_4pt": 3.3,
        "typical_ielts": 6.5,
        "gre_policy": "varies_by_program",
        "intakes": ["fall", "spring"],
        "website": "https://www.tum.de",
    },
    {
        "name": "RWTH Aachen University",
        "country": "Germany",
        "city": "Aachen",
        "programs": ["Computer Science", "Data Science", "Automation Engineering"],
        "competitiveness": "competitive",
        "typical_gpa_4pt": 3.3,
        "typical_ielts": 6.5,
        "gre_policy": "often_optional",
        "intakes": ["fall", "spring"],
        "website": "https://www.rwth-aachen.de",
    },
    {
        "name": "University of Melbourne",
        "country": "Australia",
        "city": "Melbourne",
        "programs": ["Computer Science", "Information Technology", "Data Science"],
        "competitiveness": "competitive",
        "typical_gpa_4pt": 3.2,
        "typical_ielts": 6.5,
        "gre_policy": "often_optional",
        "intakes": ["fall", "spring"],
        "website": "https://www.unimelb.edu.au",
    },
    {
        "name": "Delft University of Technology",
        "country": "Netherlands",
        "city": "Delft",
        "programs": ["Computer Science", "Embedded Systems", "Aerospace Engineering"],
        "competitiveness": "competitive",
        "typical_gpa_4pt": 3.5,
        "typical_ielts": 6.5,
        "gre_policy": "varies_by_program",
        "intakes": ["fall"],
        "website": "https://www.tudelft.nl",
    },
]
