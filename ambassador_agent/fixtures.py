"""Sneha's world, verbatim from the GE Chat prototype.

Pure data. Every user-facing string here appears in the prototype; the demo is
judged against it, so paraphrase is a defect.
"""

AMBASSADOR = {"name": "Sneha Reddy", "section": "EEE Sem 3 · Sec B"}
COLLEGE = "SVEC Tirupati"
SECTION_SIZE = 59

# activated count per demo phase
PHASES = {"live": 43, "target": 54, "complete": 59}

STRAGGLERS = [
    {"studentId": "pn", "phone": "919876543210", "name": "Priya Nandakumar",
     "context": "ignored 2 campaigns · 11 days"},
    {"studentId": "sk", "phone": "919876543211", "name": "Suresh Kumar",
     "context": "ignored 2 campaigns · 9 days"},
    {"studentId": "ar", "phone": "919876543212", "name": "Anjali Rao",
     "context": "ignored 2 campaigns · 14 days"},
    {"studentId": "vm", "phone": "919876543213", "name": "Vikram Mehta",
     "context": "never opened a link · 16 days"},
    {"studentId": "dg", "phone": "919876543214", "name": "Deepa Gowda",
     "context": "ignored 2 campaigns · 8 days"},
    {"studentId": "rt", "phone": "919876543215", "name": "Rahul Tiwari",
     "context": "ignored 2 campaigns · 12 days"},
]

ROSTER = [
    ("Aarti Sharma", "activated", "via your link · 4 Jul"),
    ("Bharath Reddy", "activated", "via campaign · 6 Jul"),
    ("Chandana M", "pending", "in campaign cycle"),
    ("Divya Prakash", "activated", "via your link · 2 Jul"),
    ("Eshwar Naidu", "pending", "ignored 2 campaigns"),
    ("Farhan Ali", "activated", "via faculty agent · 8 Jul"),
]
ROSTER_FOOTNOTE = "Showing 6 of 59"

# Other ambassadors on the board. Sneha's row is computed from live state.
PEERS = [
    {"name": "Ananya Nair", "cohortSection": "CSE Sem 5 · A",
     "pct": 96.7, "activated": 58, "size": 60},
    {"name": "Farhan Sheikh", "cohortSection": "ECE Sem 3 · A",
     "pct": 94.9, "activated": 56, "size": 59},
    {"name": "Divya Tripathi", "cohortSection": "IT Sem 3 · A",
     "pct": 89.5, "activated": 51, "size": 57},
]
BOARD_FOOTNOTE = "178 qualifying sections · under-30 pooled"

ANGLES = [
    ("Exam panic", "internals are Tuesday"),
    ("Placement", "final-year framing"),
    ("Plain", "no angle"),
]

DRAFTS = {
    "Exam panic": (
        "Hey {first} — internals Tuesday. The Circuits agent makes practice"
        " papers from ma’am’s actual notes. One tap, college login:"),
    "Placement": (
        "Hey {first} — the placement agent has the companies that actually"
        " recruit here, with real interview questions. Two minutes to set up,"
        " college login:"),
    "Plain": (
        "Hey {first} — your college study agents are ready. One tap, college"
        " login, nothing to install:"),
}

REWARD_TIERS = [
    ("25%", "Starter"),
    ("50%", "Half-way"),
    ("75%", "75% Club — tee + certificate"),
    ("100%", "Full House — the 100% badge"),
]
