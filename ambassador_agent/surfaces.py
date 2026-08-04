"""One builder per surface.

A2UI v0.8 has no ProgressBar, so activation is a text meter. It has no Table, so
the leaderboard, roster and rewards are one Card per entry: the catalog offers
no column widths and no per-cell alignment, and an emulated grid misaligns and
reads as broken. The fairness rule that matters survives either way — % and
count are always shown together, with the ranking basis stated.

Styling is two fields, `font` and `primaryColor`, so no row can be highlighted
by colour. Meaning lives in the text.

Every label here is built from Sethu's live response. Nothing is hardcoded to a
section, a name or a number.
"""

import json

from . import data, fixtures
from .a2ui import (button, button_with_values, card, column, data_model, row,
                   suggestions, surface, text, text_field)

METER_WIDTH = 20


def uid(state, base: str) -> str:
    """A surfaceId that has never been used in this conversation.

    A2UI treats a repeated surfaceId as an UPDATE to that surface. So drawing
    the same kind of card twice -- asking "where do I stand?" again, reopening
    a student, returning to the list -- rewrote the earlier card further up the
    transcript and left the new turn blank. Reported three times before the
    pattern was clear; it is a property of every surface, not of paging.
    """
    if state is None:
        return base
    sequence = int(state.get("surface_seq", 0) or 0) + 1
    state["surface_seq"] = sequence
    return f"{base}{sequence}"

# How many student cards one turn may draw.
#
# Gemini Enterprise drops a surface that is too large, silently -- the reply
# arrives as text with no cards at all. Measured against Abhishek's cohort:
# 5.6KB rendered, 12.7KB and 14.2KB did not. The ceiling is somewhere between,
# so the list is built to sit near 6KB.
#
# Getting there meant dropping the drafted message and the /go/ link from the
# list card: at ~270 bytes each they were most of a card's weight, and both are
# one tap away under Edit. What she asked for -- every student, with Send and
# Edit on each -- is what remains.
STRAGGLER_PAGE = 5

# Hard ceiling for one surface's JSON, in bytes.
#
# Gemini Enterprise drops an oversized surface silently: the reply arrives as
# text with no cards, no error anywhere. Measured against Abhishek's cohort --
# 5.6KB rendered, 12.7KB and 14.2KB did not -- so the real limit is unknown and
# somewhere between. The list is trimmed to fit this budget rather than to a
# fixed number of students, because a cohort of long names would blow a fixed
# count right back through the ceiling.
# 5.6KB is the largest surface Gemini Enterprise has been *observed* to render
# (the leaderboard). Until the real limit is known, that is the budget.
# 5453 bytes rendered in Gemini Enterprise (verified from a live session);
# 12725 and 14163 did not. This budget puts two student cards plus the chip row
# at ~5.5KB -- the largest shape we have actually watched render.
MAX_SURFACE_BYTES = 6200

# The straggler list gets its own, larger ceiling -- deliberately a probe.
#
# What we know: 3874-5592 render, 12725 and 14163 do not. Everything between is
# untested. Five cards come to 10461, so this is the experiment that narrows
# the gap; if the list comes back as a sentence with no cards, the ceiling is
# below 10461 and this drops to ~7000 (three cards).
#
# It is separate from MAX_SURFACE_BYTES on purpose: the leaderboard and roster
# stay on the conservative number, so a failed probe cannot take them with it.
STRAGGLER_MAX_BYTES = 11000

# The chip row is appended afterwards by agent._with_chips, into this same
# surface, so its weight has to come out of the budget here or every page ships
# ~1.9KB over the line it was measured against.
CHIP_ALLOWANCE = 1500


def meter(pct: float) -> str:
    """Draw activation as text. A2UI v0.8 has no ProgressBar.

    Clamped because an out-of-range percentage silently produces a meter of the
    wrong LENGTH rather than an error: `"█" * -1` is empty, while the remainder
    term grows past METER_WIDTH.
    """
    filled = round(max(0.0, min(100.0, pct)) / 100 * METER_WIDTH)
    return "█" * filled + "░" * (METER_WIDTH - filled)


def cohort_summary(state) -> list[dict]:
    prefix = uid(state, "cohort")
    cohort = data.get_cohort(state)
    stats = cohort["stats"]
    pending = len(data.get_stragglers(state))
    note = data.milestone_line(state)
    if pending:
        needs = "student needs" if pending == 1 else "students need"
        note += f" {pending} {needs} a personal message from you."

    components = [
        text(f"{prefix}-label", f"{cohort['label'].upper()} — CERTIFIED",
             "caption"),
        text(f"{prefix}-value", f"{stats['activated']} / {stats['total']}", "h2"),
        text(f"{prefix}-meter", meter(stats["pct"])),
        text(f"{prefix}-pct", f"{stats['pct']}%"),
        text(f"{prefix}-note", note),
        text(f"{prefix}-fresh", data.freshness_line(state), "caption"),
    ]
    components.append(row(f"{prefix}-meter-row",
                          [f"{prefix}-meter", f"{prefix}-pct"]))
    child_ids = [f"{prefix}-label", f"{prefix}-value", f"{prefix}-meter-row",
                 f"{prefix}-note", f"{prefix}-fresh"]

    primary_label = (f"Show the {pending} who need me" if pending
                     else "Show my cohort")
    components.append(text(f"{prefix}-cta0-label", primary_label))
    components.append(button(f"{prefix}-cta0", f"{prefix}-cta0-label",
                             "show_stragglers" if pending else "show_roster"))
    components.append(text(f"{prefix}-cta1-label",
                           "Show the leaderboard"))
    components.append(button(f"{prefix}-cta1", f"{prefix}-cta1-label", "ask",
                             {"question": "Show the leaderboard"}))
    components.append(row(f"{prefix}-ctas",
                          [f"{prefix}-cta0", f"{prefix}-cta1"]))
    child_ids.append(f"{prefix}-ctas")

    components.append(column(f"{prefix}-main-column", child_ids))
    components.append(card(f"{prefix}-card", f"{prefix}-main-column"))
    return surface(prefix, components, f"{prefix}-card")


def straggler_list(state) -> list[dict]:
    """Draw as many student cards as will actually render.

    Starts at STRAGGLER_PAGE and shrinks until the surface fits
    MAX_SURFACE_BYTES, so an oversized turn can never be silently dropped.
    """
    everyone = data.get_stragglers(state)
    offset = max(int(state.get("strag_offset", 0) or 0), 0)
    if offset >= len(everyone):
        offset = 0

    # A fresh surfaceId every time the list is drawn, not merely per page.
    # Keying it on the offset alone meant "Back to the list" reused strag0,
    # which was already on screen from earlier in the conversation -- A2UI
    # treats a repeated surfaceId as an update TO that surface, so GE rewrote
    # the old card and left this turn blank.
    prefix = uid(state, "strag")

    budget = STRAGGLER_MAX_BYTES - CHIP_ALLOWANCE
    for count in range(min(STRAGGLER_PAGE, len(everyone) - offset), 0, -1):
        messages = _straggler_page(state, everyone, offset, count, prefix)
        if len(json.dumps(messages)) <= budget or count == 1:
            state["strag_drawn"] = count
            return messages
    state["strag_drawn"] = 0
    return _straggler_page(state, everyone, offset, 0, prefix)


def _straggler_page(state, everyone: list[dict], offset: int, count: int,
                    prefix: str) -> list[dict]:
    students = everyone[offset:offset + count]
    components: list[dict] = []
    child_ids: list[str] = []

    for index, entry in enumerate(students):
        sid = entry["id"]
        # Index the component ids rather than embedding the student's UUID.
        # A uuid appears ~15 times per card once ids, child refs and column
        # lists are counted -- 36 characters each time -- and that, not the
        # drafted message, was most of the surface's weight. The uuid still
        # rides in each button's action context, which is what routing needs.
        base = f"{prefix}-s{index}"
        components.extend([
            text(f"{base}-name", entry["name"], "h5"),
            text(f"{base}-meta", data.straggler_note(entry), "caption"),
            text(f"{base}-send-label", "Send"),
            button(f"{base}-send", f"{base}-send-label", "send_whatsapp",
                   {"student_id": sid}),
            text(f"{base}-edit-label", "Edit"),
            button(f"{base}-edit", f"{base}-edit-label", "open_edit",
                   {"student_id": sid}),
            text(f"{base}-open-label", "History"),
            button(f"{base}-open", f"{base}-open-label", "open_student",
                   {"student_id": sid}),
            row(f"{base}-actions",
                [f"{base}-send", f"{base}-edit", f"{base}-open"]),
            column(f"{base}-column", [
                f"{base}-name", f"{base}-meta", f"{base}-actions",
            ]),
            card(f"{base}-card", f"{base}-column"),
        ])
        child_ids.append(f"{base}-card")

    shown = offset + len(students)
    remaining = len(everyone) - shown
    if remaining > 0:
        nxt = min(STRAGGLER_PAGE, remaining)
        components.append(text(f"{prefix}-more-label",
                               f"Show the next {nxt} of {remaining} left"))
        # The button carries the offset it leads to, so an older page's button
        # still advances from ITS place in the list rather than from wherever
        # she has since moved to.
        components.append(button(f"{prefix}-more", f"{prefix}-more-label",
                                 "more_stragglers", {"offset": str(shown)}))
        child_ids.append(f"{prefix}-more")

    counted = (f"Showing {offset + 1}–{shown} of {len(everyone)}. "
               if len(everyone) > STRAGGLER_PAGE else "")
    components.append(text(
        f"{prefix}-foot",
        f"{counted}You send from your own WhatsApp — I never send as you."
        " Your link carries your credit.",
        "caption"))
    child_ids.append(f"{prefix}-foot")

    components.append(column(f"{prefix}-main-column", child_ids))
    return surface(prefix, components, f"{prefix}-main-column")


def history_lines(touches: list[str]) -> list[str]:
    """One line per touch, or a sentence saying there are none.

    Never returns an empty list: a history section that renders nothing looks
    like a card that failed to load, which is the opposite of the reassurance
    this surface exists to give.
    """
    return touches or ["No one has reached out yet — you'd be the first."]


def student_detail(state, student_id: str) -> list[dict]:
    """One student: where they stand, and everything that already reached them.

    Draws `GET /cohorts/mine/students/{studentId}`. The question it answers is
    "have I -- or Sethu -- already chased this person?", so the history is the
    body of the card, not a footnote.
    """
    detail = data.get_student_detail(state, student_id)
    prefix = uid(state, "stud")
    first = detail["name"].split(" ")[0]
    pending = detail.get("pendingDays")
    status = (f"pending {pending} days" if pending else "pending")
    if detail.get("statusReason"):
        status += f" · {detail['statusReason']}"

    components = [
        text(f"{prefix}-name", detail["name"], "h5"),
        text(f"{prefix}-status", status, "caption"),
        text(f"{prefix}-link", detail.get("waLink") or "", "caption"),
        text(f"{prefix}-history-label", "What has reached them", "caption"),
    ]
    child_ids = [f"{prefix}-name", f"{prefix}-status", f"{prefix}-link",
                 f"{prefix}-history-label"]
    for index, line in enumerate(history_lines(detail["touches"])):
        components.append(text(f"{prefix}-t{index}", line, "caption"))
        child_ids.append(f"{prefix}-t{index}")

    components.extend([
        text(f"{prefix}-msg-label", f"Message {first}"),
        button(f"{prefix}-msg", f"{prefix}-msg-label", "open_edit",
               {"student_id": student_id}),
        text(f"{prefix}-back-label", "Back to the list"),
        button(f"{prefix}-back", f"{prefix}-back-label", "show_stragglers"),
        row(f"{prefix}-actions", [f"{prefix}-msg", f"{prefix}-back"]),
    ])
    child_ids.append(f"{prefix}-actions")

    components.append(column(f"{prefix}-main-column", child_ids))
    components.append(card(f"{prefix}-card", f"{prefix}-main-column"))
    return surface(prefix, components, f"{prefix}-card")


def drawn_count(session) -> int:
    """How many student cards the last straggler_list actually drew.

    Read from state rather than rebuilt: building it again would burn another
    surfaceId and another round of API calls.

    The parameter is `session`, not `state`, on purpose: test_ambassador.py
    discovers surface builders by their first parameter being `state`.
    """
    return int((session or {}).get("strag_drawn", 0) or 0)


def _fits(messages: list[dict]) -> bool:
    return len(json.dumps(messages)) <= MAX_SURFACE_BYTES - CHIP_ALLOWANCE


def _entry_card(prefix: str, key: str, lines: list[tuple[str, str]]) -> tuple[list[dict], str]:
    """One card per row. `lines` is (suffix, content), first line is the head."""
    components, child_ids = [], []
    for index, (suffix, content) in enumerate(lines):
        component_id = f"{prefix}-{key}-{suffix}"
        components.append(text(component_id, content,
                               "h5" if index == 0 else "caption"))
        child_ids.append(component_id)
    components.append(column(f"{prefix}-{key}-column", child_ids))
    components.append(card(f"{prefix}-{key}-card", f"{prefix}-{key}-column"))
    return components, f"{prefix}-{key}-card"


def leaderboard(state) -> list[dict]:
    """The board, trimmed to what will render.

    A 20-ambassador college came to 12KB with the chip row -- well past the
    ceiling, so GE would have dropped the whole card. Rows are dropped from the
    bottom until it fits, and her own row is always kept: it is the row she
    opened the board to find.
    """
    board = data.get_leaderboard(state)
    entries = board["entries"]
    for count in range(len(entries), 0, -1):
        shown = entries[:count]
        if not any(e.get("isMe") for e in shown):
            mine = next((e for e in entries if e.get("isMe")), None)
            if mine is not None:
                shown = shown[:-1] + [mine]
        messages = _leaderboard_page(state, board, shown, len(entries))
        if _fits(messages) or count == 1:
            return messages
    return _leaderboard_page(state, board, [], len(entries))


def _leaderboard_page(state, board: dict, entries: list[dict],
                      total_rows: int) -> list[dict]:
    prefix = uid(state, "board")
    components, child_ids = [], []
    for index, entry in enumerate(entries):
        # Her row is marked in TEXT, never colour -- A2UI exposes no per-row
        # styling, and the fairness rule requires the marker be readable.
        who = "You" if entry.get("isMe") else entry["name"]
        head = f"#{entry['rank']}  {who} — {entry['section']}"
        detail = f"{entry['pct']}% · {entry['activated']} / {entry['total']}"
        if entry.get("isPooled"):
            detail += " · pooled"
        made, card_id = _entry_card(prefix, f"r{index}",
                                    [("head", head), ("detail", detail)])
        components.extend(made)
        child_ids.append(card_id)

    components.append(text(f"{prefix}-basis", board["basisNote"], "caption"))
    seen = len(entries)
    tail = (f"Showing {seen} of {total_rows} · " if seen < total_rows else "")
    components.append(text(f"{prefix}-foot",
                           f"{tail}{board['total']} ambassadors on the board",
                           "caption"))
    child_ids.extend([f"{prefix}-basis", f"{prefix}-foot"])
    components.append(column(f"{prefix}-main-column", child_ids))
    return surface(prefix, components, f"{prefix}-main-column")


def rewards(state) -> list[dict]:
    prefix = uid(state, "rew")
    components, child_ids = [], []
    for index, tier in enumerate(data.get_rewards(state)):
        # Every tier states its threshold, so a row is never ambiguous about
        # what it costs to reach.
        detail = f"at {tier['at']} — {tier['status']}"
        made, card_id = _entry_card(prefix, f"t{index}", [
            ("head", tier["reward"]),
            ("detail", detail),
        ])
        components.extend(made)
        child_ids.append(card_id)
    components.append(text(
        f"{prefix}-foot",
        "Your credential is yours regardless of rank. Rewards are fulfilled at"
        " close-out, and follow section outcomes — never effort.", "caption"))
    child_ids.append(f"{prefix}-foot")
    components.append(column(f"{prefix}-main-column", child_ids))
    return surface(prefix, components, f"{prefix}-main-column")


def roster(state) -> list[dict]:
    """The class list, trimmed to what will render."""
    everyone = data.get_roster(state)
    for count in range(len(everyone), 0, -1):
        messages = _roster_page(state, everyone[:count], len(everyone))
        if _fits(messages) or count == 1:
            return messages
    return _roster_page(state, [], len(everyone))


def _roster_page(state, entries: list[dict], total_rows: int) -> list[dict]:
    prefix = uid(state, "ros")
    components, child_ids = [], []
    for index, entry in enumerate(entries):
        detail = entry["status"]
        if entry["how"]:
            detail += f" · {entry['how']}"
        made, card_id = _entry_card(prefix, f"s{index}", [
            ("head", entry["name"]),
            ("detail", detail),
        ])
        components.extend(made)
        child_ids.append(card_id)
    total = data.get_cohort(state)["stats"]["total"]
    components.append(text(f"{prefix}-foot",
                           f"Showing {len(entries)} of {max(total, total_rows)}",
                           "caption"))
    child_ids.append(f"{prefix}-foot")
    components.append(column(f"{prefix}-main-column", child_ids))
    return surface(prefix, components, f"{prefix}-main-column")


def chips_surface(labels: list[str], state=None) -> list[dict]:
    """Standalone follow-up chip row drawn after every routed reply.

    Not auto-discovered by the structural-invariant harness in
    test_ambassador.py: its first parameter is `labels`, not `state` (there is
    no cohort state to read — the labels are already resolved by the caller).
    Covered instead by an explicit test.
    """
    prefix = uid(state, "chips")
    components, ids = suggestions(prefix, labels)
    child_ids = list(ids)
    if child_ids:
        components.append(row(f"{prefix}-row", child_ids))
        child_ids = [f"{prefix}-row"]
    components.append(column(f"{prefix}-main-column", child_ids))
    return surface(prefix, components, f"{prefix}-main-column")


def edit_form(state, student_id: str) -> list[dict]:
    prefix = uid(state, "edit")
    entry = data.student(state, student_id)
    if entry is None:
        raise KeyError(student_id)
    first = entry["name"].split(" ")[0]
    sent = data.is_sent(state, student_id)
    angle = (state.get("angles", {}) or {}).get(student_id, "examPanic")
    draft = (state.get("drafts", {}) or {}).get(student_id) \
        or data.draft_for(state, student_id, angle)

    title = (f"Sent — {entry['name']}" if sent
             else f"Edit before sending — {entry['name']}")
    cta = f"Sent to {first} ✓" if sent else f"Send to {first}"

    components = [
        text(f"{prefix}-heading", title, "h5"),
        text(f"{prefix}-angle-label", "Angle", "caption"),
    ]
    angle_ids = []
    for index, (key, label) in enumerate(fixtures.ANGLES):
        marker = "● " if key == angle else "○ "
        components.append(text(f"{prefix}-a{index}-label", marker + label))
        components.append(button(f"{prefix}-a{index}", f"{prefix}-a{index}-label",
                                 "set_angle",
                                 {"student_id": student_id, "angle": key}))
        angle_ids.append(f"{prefix}-a{index}")
    components.append(row(f"{prefix}-angles", angle_ids))

    components.append(text_field(f"{prefix}-body", "Message", "/draft/text"))
    components.append(text(f"{prefix}-cta-label", cta))
    components.append(button_with_values(
        f"{prefix}-cta", f"{prefix}-cta-label", "send_whatsapp",
        {"student_id": {"literalString": student_id},
         "message": {"path": "/draft/text"}}))
    components.append(column(f"{prefix}-main-column", [
        f"{prefix}-heading", f"{prefix}-angle-label", f"{prefix}-angles",
        f"{prefix}-body", f"{prefix}-cta",
    ]))
    components.append(card(f"{prefix}-card", f"{prefix}-main-column"))

    messages = surface(prefix, components, f"{prefix}-card")
    # The data model seeds the TextField and is what the send button reads
    # back; kept between surfaceUpdate and beginRendering so the client can
    # paint with the draft already filled in.
    messages.insert(1, data_model(prefix, {"draft": {"text": draft}}))
    return messages
