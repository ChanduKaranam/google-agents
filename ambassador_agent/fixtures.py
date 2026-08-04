"""Recorded Sethu API responses, verbatim from the shapes Sethu documented.

These are SAMPLE RESPONSE BODIES, not our own invented data -- one per endpoint,
in exactly the shape `sethu.py` receives over the wire. `data.py` maps them into
what the surfaces render, so the mapping is exercised by every offline test and
the live path differs only in where the dict came from.

Source: Sethu's API usage pack (2026-08-03). Ambassador is Akhil Reddy, CSE Yr 3
Sec A. The prototype's Sneha/EEE numbers are gone deliberately -- the demo now
speaks whatever the backend says.
"""

# GET /tenants/{tenantId}/cohorts/mine
COHORT = {
    "ambassadorName": "Akhil Reddy",
    "label": "CSE · Yr 3 · Sec A",
    "stats": {"total": 59, "activated": 14, "pct": 23.7, "daysLeft": 45,
              "isPooled": False},
    "nextMilestone": {"pct": 25, "activationsAway": 1, "label": "25% Club",
                      "reward": "₹500 Amazon voucher"},
    "myRank": 4,
    "totalAmbassadors": 12,
    "lastSyncedAt": "2026-08-03T04:30:00.000Z",
    "students": [
        {"id": "stu-001", "name": "Ravi Kumar", "rollNo": "21CS001",
         "phone": "+919876543210", "activationStatus": "ACTIVATED"},
        {"id": "stu-002", "name": "Kavya S", "rollNo": "21CS002",
         "phone": "+919876543211", "activationStatus": "DORMANT"},
        {"id": "stu-003", "name": "Arjun Nair", "rollNo": "21CS003",
         "phone": "+919876543212", "activationStatus": "PENDING"},
        {"id": "stu-004", "name": "Meera Joshi", "rollNo": "21CS004",
         "phone": "+919876543213", "activationStatus": "DORMANT"},
        {"id": "stu-005", "name": "Sanjay Patel", "rollNo": "21CS005",
         "phone": "+919876543214", "activationStatus": "ACTIVATED"},
        {"id": "stu-006", "name": "Nisha Verma", "rollNo": "21CS006",
         "phone": "+919876543215", "activationStatus": "DORMANT"},
    ],
}

# GET /cohorts/mine/stragglers?page=1&limit=10
# Note: no `phone` here -- the number lives on cohorts/mine.students[], so
# `data.py` joins the two by student id to build the WhatsApp deeplink.
STRAGGLERS = {
    "items": [
        {"id": "stu-002", "name": "Kavya S", "rollNo": "21CS002",
         "pendingDays": 12, "linkStatus": "not_sent",
         "goLink": "https://sethu.app/go/abc123",
         "draftMessage": "Hi Kavya, have you tried Gemini yet?",
         "contextNote": "Day 12 — first nudge window",
         "angles": {
             "examPanic": "Hi Kavya — internals are close. The Circuits agent"
                          " builds practice papers from ma'am's actual notes."
                          " One tap, college login:",
             "placement": "Hi Kavya — the placement agent has the companies"
                          " that actually recruit here, with real interview"
                          " questions. Two minutes to set up:",
             "friendlyRoast": "Hi Kavya — everyone in Sec A is using this"
                              " except you. Don't make me send a third"
                              " message. One tap:",
         }},
        {"id": "stu-004", "name": "Meera Joshi", "rollNo": "21CS004",
         "pendingDays": 8, "linkStatus": "sent",
         "goLink": "https://sethu.app/go/def456",
         "draftMessage": "Hi Meera, have you tried Gemini yet?",
         "contextNote": "Day 8 — link sent, not opened",
         "angles": {
             "examPanic": "Hi Meera — internals are close. The Circuits agent"
                          " builds practice papers from ma'am's actual notes."
                          " One tap, college login:",
             "placement": "Hi Meera — the placement agent has the companies"
                          " that actually recruit here, with real interview"
                          " questions. Two minutes to set up:",
             "friendlyRoast": "Hi Meera — everyone in Sec A is using this"
                              " except you. Don't make me send a third"
                              " message. One tap:",
         }},
        {"id": "stu-006", "name": "Nisha Verma", "rollNo": "21CS006",
         "pendingDays": 15, "linkStatus": "opened",
         "goLink": "https://sethu.app/go/ghi789",
         "draftMessage": "Hi Nisha, have you tried Gemini yet?",
         "contextNote": "Day 15 — opened the link, no sign-in",
         "angles": {
             "examPanic": "Hi Nisha — internals are close. The Circuits agent"
                          " builds practice papers from ma'am's actual notes."
                          " One tap, college login:",
             "placement": "Hi Nisha — the placement agent has the companies"
                          " that actually recruit here, with real interview"
                          " questions. Two minutes to set up:",
             "friendlyRoast": "Hi Nisha — everyone in Sec A is using this"
                              " except you. Don't make me send a third"
                              " message. One tap:",
         }},
    ],
    "total": 3, "page": 1, "limit": 10,
}

# GET /tenants/{tenantId}/leaderboard?page=1&limit=10
LEADERBOARD = {
    "entries": [
        {"rank": 1, "ambassadorId": "amb-1", "name": "Sneha Priya",
         "section": "CSE · Yr 2 · Sec B", "activated": 22, "total": 55,
         "pct": 40.0, "isPooled": False, "isMe": False},
        {"rank": 2, "ambassadorId": "amb-2", "name": "Farhan Sheikh",
         "section": "ECE · Yr 3 · Sec A", "activated": 19, "total": 58,
         "pct": 32.8, "isPooled": False, "isMe": False},
        {"rank": 3, "ambassadorId": "amb-3", "name": "Divya Tripathi",
         "section": "IT · Yr 3 · Sec A", "activated": 16, "total": 57,
         "pct": 28.1, "isPooled": False, "isMe": False},
        {"rank": 4, "ambassadorId": "amb-4", "name": "Akhil Reddy",
         "section": "CSE · Yr 3 · Sec A", "activated": 14, "total": 59,
         "pct": 23.7, "isPooled": False, "isMe": True},
    ],
    "myRank": 4, "page": 1, "limit": 10, "total": 12,
    "basisNote": "Ranked by % activation within cohort",
}

# GET /cohorts/mine/students/{studentId} -- newest first
STUDENT_DETAIL = {
    "stu-002": {
        "id": "stu-002", "name": "Kavya S", "rollNo": "21CS002",
        "pendingDays": 12,
        "statusReason": "Same cohort — CSE Yr3 Sec A",
        "waLink": "https://sethu.app/go/abc123",
        "touchHistory": [
            {"id": "attr:abc", "kind": "activation_touch",
             "label": "Activation touch · WA_ME", "detail": "WA_ME",
             "occurredAt": "2026-08-02T09:00:00Z"},
            {"id": "gt-xyz:opened", "kind": "link_visited",
             "label": "Student opened link", "detail": None,
             "occurredAt": "2026-08-01T11:23:00Z"},
            {"id": "gt-xyz:created", "kind": "link_shared",
             "label": "Link shared by Akhil Reddy", "detail": "Akhil Reddy",
             "occurredAt": "2026-08-01T10:00:00Z"},
        ],
    },
    "stu-004": {
        "id": "stu-004", "name": "Meera Joshi", "rollNo": "21CS004",
        "pendingDays": 8,
        "statusReason": "Same cohort — CSE Yr3 Sec A",
        "waLink": "https://sethu.app/go/def456",
        "touchHistory": [
            {"id": "gt-def:created", "kind": "link_shared",
             "label": "Link shared by Akhil Reddy", "detail": "Akhil Reddy",
             "occurredAt": "2026-07-29T08:15:00Z"},
        ],
    },
    # No touches yet -- exercises the empty-history path.
    "stu-006": {
        "id": "stu-006", "name": "Nisha Verma", "rollNo": "21CS006",
        "pendingDays": 15,
        "statusReason": "Same cohort — CSE Yr3 Sec A",
        "waLink": "https://sethu.app/go/ghi789",
        "touchHistory": [],
    },
}

# The reward ladder is NOT served by the API -- `cohorts/mine.nextMilestone`
# carries only the next rung. Until Sethu exposes the full ladder, the
# thresholds live here and the reward text for the CURRENT rung is overlaid
# from nextMilestone, so at least the tier she is chasing is always live.
# ponytail: hardcoded ladder, replace when Sethu ships a tiers endpoint.
REWARD_TIERS = [25, 50, 75, 100]

# Angle keys as the API names them, paired with the label we show her.
#
# "custom" is not one of Sethu's -- it is written by `data.custom_draft`, a
# plain message for when none of the three fit the student.
# Custom leads, and is what a student gets unless she picks another tone: it is
# the plainest of the four, and the one that reads as a request rather than a
# nudge. It is also the shortest, which is what lets the drafted message fit
# back onto the list cards without pushing the surface past what GE will draw.
ANGLES = [
    ("custom", "Custom template"),
    ("examPanic", "Exam panic"),
    ("placement", "Placement"),
    ("friendlyRoast", "Friendly roast"),
]
