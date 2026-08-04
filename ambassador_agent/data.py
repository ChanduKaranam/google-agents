"""Maps Sethu API responses into what the surfaces render.

This module is the backend seam. `_payload()` is the only place that decides
where a response comes from: the live Sethu API when the agent is configured for
it, otherwise the recorded samples in `fixtures`. Every mapping below runs
identically either way, so the offline tests exercise the real mapping.

Shapes follow Sethu's API usage pack (2026-08-03). Field names on the left of
each mapping are theirs; the names we hand to `surfaces` are ours.

Mutations (which students she has messaged) write to ADK session state: Sethu
exposes no write endpoint for recording a nudge, so a send is conversation-local
until the /go/ link is clicked and their sync picks it up.
"""

import math
import urllib.parse

from . import fixtures, sethu


def _payload(kind: str, student_id: str | None = None) -> dict:
    """The one place that chooses live API vs recorded sample.

    Deployed, there is no third option: either we know who is asking and read
    their section, or we refuse. Falling back to the samples in production
    would put invented students, with invented phone numbers, in front of a
    real ambassador as though they were her class.
    """
    if sethu.enabled():
        return sethu.get(kind, student_id)
    if sethu.deployed():
        raise sethu.NoIdentity(
            "No end-user identity, so there is no section to show")
    if kind == "student":
        detail = fixtures.STUDENT_DETAIL.get(student_id)
        if detail is None:
            raise KeyError(student_id)
        return detail
    return {"cohort": fixtures.COHORT, "stragglers": fixtures.STRAGGLERS,
            "leaderboard": fixtures.LEADERBOARD}[kind]


def plural(count: int, singular: str, plural_form: str = "") -> str:
    """"1 student", not "1 students".

    Real cohorts are any size -- dev seeds one of exactly 1 -- so every count
    the agent speaks has to survive n == 1.
    """
    word = singular if count == 1 else (plural_form or singular + "s")
    return f"{count} {word}"


def _get(state, key, default=None):
    # ADK's State has no keys(); dict(state) raises KeyError: 0.
    return state.get(key, default) if state is not None else default


# --- demo phase -------------------------------------------------------------
# The simulator can no longer swap in a different fixture: the numbers are
# Sethu's now. It overrides the activated COUNT instead, so "simulate 75%"
# still moves the meter and the milestone copy without touching the backend.
PHASES = ("live", "target", "complete")


def set_phase(state, phase: str) -> None:
    if phase not in PHASES:
        raise ValueError(f"unknown phase {phase!r}")
    state["phase"] = phase


def _phase(state) -> str:
    return _get(state, "phase", "live")


def _activated(state, raw: dict) -> int:
    total = raw["stats"]["total"]
    phase = _phase(state)
    if phase == "complete":
        return total
    if phase == "target":
        return math.ceil(total * 0.75)
    return raw["stats"]["activated"]


def mark_sent(state, student_id: str) -> None:
    sent = list(_get(state, "sent", []))
    if student_id not in sent:
        sent.append(student_id)
    state["sent"] = sent


def is_sent(state, student_id: str) -> bool:
    return student_id in (_get(state, "sent", []) or [])


# --- cohort -----------------------------------------------------------------

def get_cohort(state) -> dict:
    """GET /tenants/{tenantId}/cohorts/mine"""
    raw = _payload("cohort")
    total = raw["stats"]["total"]
    activated = _activated(state, raw)
    pct = round(activated / total * 100, 1) if total else 0.0
    return {
        "name": raw["ambassadorName"],
        "label": raw["label"],
        "stats": {"activated": activated, "total": total, "pct": pct,
                  "daysLeft": raw["stats"].get("daysLeft"),
                  "isPooled": raw["stats"].get("isPooled", False)},
        "nextMilestone": raw.get("nextMilestone"),
        "myRank": raw.get("myRank"),
        "totalAmbassadors": raw.get("totalAmbassadors"),
        "lastSyncedAt": raw.get("lastSyncedAt"),
        "students": raw.get("students", []),
    }


# Their status vocabulary, in her words. DORMANT is the one that matters -- it
# is what makes a student a straggler -- so it must not read as jargon.
_STATUS_WORDS = {
    "ACTIVATED": "activated",
    "PENDING": "pending",
    "DORMANT": "gone quiet",
}


def get_roster(state) -> list[dict]:
    """The full cohort, from `cohorts/mine.students[]` -- never paginated."""
    return [
        {"name": s["name"],
         "status": _STATUS_WORDS.get(s["activationStatus"], s["activationStatus"].lower()),
         "how": s.get("rollNo", "")}
        for s in get_cohort(state)["students"]
    ]


def _phone_by_id(state) -> dict:
    """Straggler items carry no phone; `cohorts/mine.students[]` does."""
    return {s["id"]: s.get("phone", "")
            for s in get_cohort(state)["students"]}


def get_stragglers(state) -> list[dict]:
    """GET /cohorts/mine/stragglers

    Filtered by what she has already sent this conversation, so the list
    shortens as she works down it.
    """
    phase = _phase(state)
    if phase == "complete":
        return []
    raw = _payload("stragglers")
    phones = _phone_by_id(state)
    return [
        {**item, "phone": phones.get(item["id"], "")}
        for item in raw.get("items", [])
        if not is_sent(state, item["id"])
    ]


def straggler_total(state) -> int:
    """The true count behind a paged first page."""
    if _phase(state) == "complete":
        return 0
    return _payload("stragglers").get("total", 0)


# --- leaderboard ------------------------------------------------------------

def get_leaderboard(state) -> dict:
    """GET /tenants/{tenantId}/leaderboard"""
    raw = _payload("leaderboard")
    return {
        "entries": [dict(e) for e in raw.get("entries", [])],
        "myRank": raw.get("myRank"),
        "total": raw.get("total"),
        "basisNote": raw.get("basisNote", ""),
    }


# --- milestones and rewards -------------------------------------------------

def milestone_line(state) -> str:
    cohort = get_cohort(state)
    stats = cohort["stats"]
    if stats["activated"] >= stats["total"]:
        return (f"Every student in {cohort['label']} is activated —"
                " nothing left to unlock.")
    milestone = cohort["nextMilestone"]
    if not milestone:
        remaining = stats["total"] - stats["activated"]
        return f"{remaining} more to go in {cohort['label']}."
    # activationsAway is theirs, but it is computed against the live count --
    # the demo simulator moves ours, so recompute to stay consistent.
    need = max(math.ceil(stats["total"] * milestone["pct"] / 100)
               - stats["activated"], 0)
    if need == 0:
        remaining = stats["total"] - stats["activated"]
        return (f"Your {milestone['label']} is earned. {remaining} more"
                " activations makes it every student in the section.")
    verb = "activation clears" if need == 1 else "activations clear"
    reward = milestone.get("reward")
    tail = f" — {reward}" if reward else ""
    return f"{need} more {verb} your {milestone['label']}{tail}."


def get_rewards(state) -> list[dict]:
    """The tier ladder.

    Sethu serves only the NEXT rung (`nextMilestone`), so the thresholds come
    from `fixtures.REWARD_TIERS` and the live reward text is overlaid on the
    rung she is currently chasing. Rungs above that read as "not yet named"
    rather than inventing a prize she will not receive.
    """
    cohort = get_cohort(state)
    stats = cohort["stats"]
    milestone = cohort["nextMilestone"] or {}
    rows = []
    for at in fixtures.REWARD_TIERS:
        need = max(math.ceil(stats["total"] * at / 100) - stats["activated"], 0)
        if at == milestone.get("pct"):
            reward = milestone.get("reward") or "reward to be announced"
        elif need == 0:
            reward = "earned"
        else:
            reward = "reward to be announced"
        rows.append({"at": f"{at}%", "reward": reward,
                     "status": "earned" if need == 0 else f"{need} more"})
    return rows


# --- students ---------------------------------------------------------------

def student(state, student_id: str) -> dict | None:
    """Look one student up, sent or not.

    Deliberately NOT filtered by `is_sent`: `get_stragglers` hides someone once
    she has messaged them, but the edit form still has to render for that
    person afterwards -- it is what shows the "Sent ✓" state.
    """
    if _phase(state) == "complete":
        return None
    phones = _phone_by_id(state)
    for item in _payload("stragglers").get("items", []):
        if item["id"] == student_id:
            return {**item, "phone": phones.get(student_id, "")}
    return None


_KIND_WORDS = {
    "link_shared": "link shared",
    "link_visited": "opened the link",
    "campaign_link": "campaign link",
    "activation_touch": "activation",
}

_CHANNEL_WORDS = {"WABA": "WhatsApp broadcast", "WA_ME": "your WhatsApp",
                  "SELF_SERVE": "signed in on their own"}


def _touch_line(touch: dict) -> str:
    """One history row, in her language rather than the API's."""
    when = (touch.get("occurredAt") or "")[:10]
    what = _KIND_WORDS.get(touch.get("kind"), touch.get("kind", ""))
    detail = touch.get("detail")
    if touch.get("kind") == "activation_touch":
        detail = _CHANNEL_WORDS.get(detail, detail)
    return f"{when} · {what}" + (f" · {detail}" if detail else "")


def get_student_detail(state, student_id: str) -> dict:
    """GET /cohorts/mine/students/:studentId

    `touches` merges Sethu's history with anything she has sent in THIS
    conversation: Sethu records a send only once the /go/ link is clicked, so
    without the merge she sends a message, reopens the student, and sees no
    trace of what she just did.
    """
    raw = _payload("student", student_id)
    touches = [_touch_line(t) for t in raw.get("touchHistory", [])]
    if is_sent(state, student_id):
        touches.insert(0, "just now · your WhatsApp · sent by you")
    return {
        "id": raw["id"],
        "name": raw["name"],
        "rollNo": raw.get("rollNo", ""),
        "pendingDays": raw.get("pendingDays"),
        "statusReason": raw.get("statusReason", ""),
        "waLink": raw.get("waLink"),
        "touches": touches,
    }


def draft_for(state, student_id: str, angle_key: str = "examPanic") -> str:
    """The pre-written message, straight from the API's `angles`."""
    entry = student(state, student_id)
    if entry is None:
        raise KeyError(student_id)
    angles = entry.get("angles") or {}
    return angles.get(angle_key) or entry.get("draftMessage", "")


def append_link(message: str, link: str) -> str:
    """Add the /go/ link unless the draft already carries it.

    Sethu's `draftMessage` ends with the link; her own edit may or may not.
    Appending blindly showed the same url twice in the message she sends.
    """
    if not link or link in (message or ""):
        return message
    return f"{message}\n{link}"


_LINK_WORDS = {"not_sent": "no link sent yet",
               "sent": "link sent, not opened",
               "opened": "opened the link, no sign-in"}


def straggler_note(entry: dict) -> str:
    """The one line under a student's name.

    Live `contextNote` is the same sentence for every student in the cohort
    ("Same cohort — EEE Yr4 Sec A"), which tells her nothing about who to chase
    first. `rollNo`, `pendingDays` and `linkStatus` actually differ.
    """
    bits = []
    if entry.get("rollNo"):
        bits.append(entry["rollNo"])
    days = entry.get("pendingDays")
    if days:
        bits.append(f"pending {plural(days, 'day')}")
    status = _LINK_WORDS.get(entry.get("linkStatus"))
    if status:
        bits.append(status)
    if not wa_number(entry):
        bits.append("no phone on file")
    return " · ".join(bits) or entry.get("contextNote", "")


def wa_link(state, student_id: str) -> str:
    """The /go/ attribution link. Her credit rides on this url."""
    entry = student(state, student_id)
    if entry is None:
        raise KeyError(student_id)
    return entry.get("goLink", "")


# Sethu's dev rows carry bare 10-digit numbers ("9876501041") while the guide's
# sample showed "+91…". wa.me needs a country code or it opens an empty chat, so
# a bare Indian mobile is normalised rather than trusted either way.
_INDIA = "91"


def wa_number(entry: dict) -> str:
    """The dialable number for a student, or "" when none is on file."""
    return _wa_number((entry or {}).get("phone"))


def _wa_number(phone: str) -> str:
    digits = "".join(c for c in (phone or "") if c.isdigit())
    if len(digits) == 10:
        return _INDIA + digits
    return digits


def whatsapp_deeplink(state, student_id: str, message: str) -> str:
    """A tappable wa.me url that opens WhatsApp with the message pre-filled.

    A2UI v0.8 cannot put a link on a card -- Button dispatches an action and
    Text excludes links -- so this goes in the agent's prose reply, where the
    chat surface renders it as a normal link. Without it the product promise
    ("Sethu never sends from your number -- it pre-fills, you send") is not
    kept: she would have to retype the message into WhatsApp herself.
    """
    entry = student(state, student_id) or {}
    return (f"https://wa.me/{_wa_number(entry.get('phone'))}"
            f"?text={urllib.parse.quote(message, safe='')}")


def freshness_line(state) -> str:
    """Sethu's activation numbers lag Google by 15 min to ~6h, so the card
    always says when they were last certified rather than implying live."""
    synced = get_cohort(state).get("lastSyncedAt")
    if not synced:
        return "Not synced with Google yet."
    return f"Certified by Google, last synced {synced[:16].replace('T', ' ')} UTC."


def greeting_line(state) -> str:
    """The opening message, from live numbers.

    Gemini Enterprise gives an agent no "conversation opened" event, so this
    fires on her first turn instead -- the closest the platform allows.
    """
    cohort = get_cohort(state)
    stats = cohort["stats"]
    first = cohort["name"].split(" ")[0]
    pending = straggler_total(state)
    classmates = plural(stats["total"], "classmate")
    line = (f"Hi {first} — I look after {cohort['label']} with you."
            f"\n\nRight now {stats['activated']} of your {classmates}"
            f" are activated ({stats['pct']}%),"
            f" from Google's certified reporting. {milestone_line(state)}")
    if pending:
        needs = "student needs" if pending == 1 else "students need"
        line += f" {pending} {needs} a personal message from you."
    return line
