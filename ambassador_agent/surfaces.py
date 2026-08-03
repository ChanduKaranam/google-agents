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

from . import data, fixtures
from .a2ui import (button, button_with_values, card, column, data_model, row,
                   suggestions, surface, text, text_field)

METER_WIDTH = 20

# How many student cards one turn may draw.
#
# Abhishek's 11 stragglers built a 33KB, 145-component surface and Gemini
# Enterprise dropped it silently -- he saw the sentence and no cards, while a
# 5.6KB leaderboard in the same session rendered fine. Four cards keeps a turn
# near 12KB, comfortably inside whatever the limit is, and reads better than a
# wall of eleven.
STRAGGLER_PAGE = 4


def meter(pct: float) -> str:
    """Draw activation as text. A2UI v0.8 has no ProgressBar.

    Clamped because an out-of-range percentage silently produces a meter of the
    wrong LENGTH rather than an error: `"█" * -1` is empty, while the remainder
    term grows past METER_WIDTH.
    """
    filled = round(max(0.0, min(100.0, pct)) / 100 * METER_WIDTH)
    return "█" * filled + "░" * (METER_WIDTH - filled)


def cohort_summary(state) -> list[dict]:
    prefix = "cohort"
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
                           "How is my rank calculated?"))
    components.append(button(f"{prefix}-cta1", f"{prefix}-cta1-label", "ask",
                             {"question": "how is my rank calculated?"}))
    components.append(row(f"{prefix}-ctas",
                          [f"{prefix}-cta0", f"{prefix}-cta1"]))
    child_ids.append(f"{prefix}-ctas")

    components.append(column(f"{prefix}-main-column", child_ids))
    components.append(card(f"{prefix}-card", f"{prefix}-main-column"))
    return surface(prefix, components, f"{prefix}-card")


def straggler_list(state) -> list[dict]:
    prefix = "strag"
    everyone = data.get_stragglers(state)
    offset = max(int(state.get("strag_offset", 0) or 0), 0)
    if offset >= len(everyone):
        offset = 0
    students = everyone[offset:offset + STRAGGLER_PAGE]
    components: list[dict] = []
    child_ids: list[str] = []

    for entry in students:
        sid = entry["id"]
        base = f"{prefix}-{sid}"
        components.extend([
            text(f"{base}-name", entry["name"], "h5"),
            text(f"{base}-meta", data.straggler_note(entry), "caption"),
            text(f"{base}-msg", data.draft_for(state, sid)),
            text(f"{base}-link", entry.get("goLink", ""), "caption"),
            text(f"{base}-send-label", "Send from my WhatsApp"),
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
                f"{base}-name", f"{base}-meta", f"{base}-msg",
                f"{base}-link", f"{base}-actions",
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
        components.append(button(f"{prefix}-more", f"{prefix}-more-label",
                                 "more_stragglers"))
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
    prefix = f"stud-{student_id}"
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
    prefix = "board"
    board = data.get_leaderboard(state)
    components, child_ids = [], []
    for index, entry in enumerate(board["entries"]):
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
    components.append(text(f"{prefix}-foot",
                           f"{board['total']} ambassadors on the board",
                           "caption"))
    child_ids.extend([f"{prefix}-basis", f"{prefix}-foot"])
    components.append(column(f"{prefix}-main-column", child_ids))
    return surface(prefix, components, f"{prefix}-main-column")


def rewards(state) -> list[dict]:
    prefix = "rew"
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
    prefix = "ros"
    entries = data.get_roster(state)
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
                           f"Showing {len(entries)} of {total}", "caption"))
    child_ids.append(f"{prefix}-foot")
    components.append(column(f"{prefix}-main-column", child_ids))
    return surface(prefix, components, f"{prefix}-main-column")


def chips_surface(labels: list[str]) -> list[dict]:
    """Standalone follow-up chip row drawn after every routed reply.

    Not auto-discovered by the structural-invariant harness in
    test_ambassador.py: its first parameter is `labels`, not `state` (there is
    no cohort state to read — the labels are already resolved by the caller).
    Covered instead by an explicit test.
    """
    prefix = "chips"
    components, ids = suggestions(prefix, labels)
    child_ids = list(ids)
    if child_ids:
        components.append(row(f"{prefix}-row", child_ids))
        child_ids = [f"{prefix}-row"]
    components.append(column(f"{prefix}-main-column", child_ids))
    return surface(prefix, components, f"{prefix}-main-column")


def edit_form(state, student_id: str) -> list[dict]:
    prefix = f"edit-{student_id}"
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
