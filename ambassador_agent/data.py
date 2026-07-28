"""Accessors returning the ambassador API's documented response shapes.

This module is the backend seam. Today every function reads `fixtures`; when the
API lands, each body becomes an HTTP call and nothing else in the agent moves.
Shapes follow `ambassador-flow.pdf` (2026-07-28).

Mutations write to ADK session state so progress is real inside a conversation:
the sent count climbs as she works through the list.
"""

import math

from . import fixtures


def _get(state, key, default=None):
    # ADK's State has no keys(); dict(state) raises KeyError: 0.
    return state.get(key, default) if state is not None else default


def _phase(state) -> str:
    return _get(state, "phase", "live")


def _activated(state) -> int:
    return fixtures.PHASES[_phase(state)]


def _pct(activated: int) -> float:
    return round(activated / fixtures.SECTION_SIZE * 100, 1)


def set_phase(state, phase: str) -> None:
    if phase not in fixtures.PHASES:
        raise ValueError(f"unknown phase {phase!r}")
    state["phase"] = phase


def mark_sent(state, student_id: str) -> None:
    sent = list(_get(state, "sent", []))
    if student_id not in sent:
        sent.append(student_id)
    state["sent"] = sent


def is_sent(state, student_id: str) -> bool:
    return student_id in (_get(state, "sent", []) or [])


def get_stragglers(state) -> dict:
    """GET /api/v1/cohorts/mine/stragglers"""
    phase = _phase(state)
    if phase == "complete":
        pool = []
    elif phase == "target":
        pool = fixtures.STRAGGLERS[4:]
    else:
        pool = fixtures.STRAGGLERS
    pending = [s for s in pool if not is_sent(state, s["studentId"])]
    data = [
        {**s, "waLink": f"sethu.app/go/{s['studentId']}8x2"}
        for s in pending
    ]
    return {"data": data, "total": len(data), "page": 1, "limit": 20}


def get_cohort(state) -> dict:
    """GET /api/v1/cohorts/mine"""
    activated = _activated(state)
    return {
        "ambassador": dict(fixtures.AMBASSADOR),
        "stats": {"activated": activated, "size": fixtures.SECTION_SIZE,
                  "pct": _pct(activated)},
        "nextMilestone": _next_milestone(state),
        "stragglers": get_stragglers(state)["data"],
        "fullRoster": get_roster(state),
    }


def get_roster(state) -> list[dict]:
    return [
        {"name": name, "status": status, "how": how}
        for name, status, how in fixtures.ROSTER
    ]


def get_leaderboard(state) -> dict:
    """GET /api/v1/tenants/:id/leaderboard"""
    activated = _activated(state)
    mine = {"name": "You", "cohortSection": fixtures.AMBASSADOR["section"],
            "pct": _pct(activated), "activated": activated,
            "size": fixtures.SECTION_SIZE}
    rows = sorted([*fixtures.PEERS, mine], key=lambda r: -r["pct"])
    # Live, she sits at #19 of 178; once she climbs, the visible slot is her
    # sorted position. The prototype shows the same four rows either way.
    slots = [1, 2, 3, 19] if _phase(state) == "live" else [1, 2, 3, 4]
    for slot, row in zip(slots, rows):
        row["rank"] = slot
    my_rank = [r["rank"] for r in rows if r["name"] == "You"][0]
    return {"data": rows, "myRank": my_rank}


def _needed_for_75(state) -> int:
    target = math.ceil(fixtures.SECTION_SIZE * 0.75)
    return max(target - _activated(state), 0)


def _next_milestone(state) -> dict:
    if _phase(state) == "complete":
        return {"target": 100, "reward": "Full House — the 100% badge"}
    if _phase(state) == "target":
        return {"target": 100, "reward": "Full House — the 100% badge"}
    return {"target": 75, "reward": "75% Club — tee + certificate"}


def milestone_line(state) -> str:
    phase = _phase(state)
    if phase == "complete":
        return "Every student in Sec B is activated — nothing left to unlock."
    remaining = fixtures.SECTION_SIZE - _activated(state)
    if phase == "target":
        return (f"Your 75% milestone is earned. {remaining} more makes Full"
                " House, the 100% badge.")
    need = _needed_for_75(state)
    verb = "activation clears" if need == 1 else "activations clear"
    return f"{need} more {verb} your 75% milestone."


def get_rewards(state) -> list[dict]:
    activated = _activated(state)
    phase = _phase(state)
    remaining = fixtures.SECTION_SIZE - activated
    statuses = {
        "25%": "earned",
        "50%": "earned",
        "75%": f"{_needed_for_75(state)} more" if phase == "live" else "earned",
        "100%": "earned" if phase == "complete" else f"{remaining} more",
    }
    return [
        {"at": at, "reward": reward, "status": statuses[at]}
        for at, reward in fixtures.REWARD_TIERS
    ]


def student(student_id: str) -> dict | None:
    for entry in fixtures.STRAGGLERS:
        if entry["studentId"] == student_id:
            return entry
    return None


def draft_for(student_id: str, angle: str = "Exam panic") -> str:
    entry = student(student_id)
    if entry is None:
        raise KeyError(student_id)
    first = entry["name"].split(" ")[0]
    return fixtures.DRAFTS[angle].format(first=first)


def wa_link(student_id: str) -> str:
    return f"sethu.app/go/{student_id}8x2"
