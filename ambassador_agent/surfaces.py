"""One builder per surface.

A2UI v0.8 has no ProgressBar, so activation is a text meter. It has no Table, so
the leaderboard, roster and rewards are one Card per entry: the catalog offers
no column widths and no per-cell alignment, and an emulated grid misaligns and
reads as broken. The fairness rule that matters survives either way — % and
count are always shown together, with the ranking basis stated.

Styling is two fields, `font` and `primaryColor`, so no row can be highlighted
by colour. Meaning lives in the text.
"""

from . import data
from .a2ui import (button, button_with_values, card, column, data_model, row,
                   suggestions, surface, text, text_field)

METER_WIDTH = 20


def meter(pct: float) -> str:
    """Draw activation as text. A2UI v0.8 has no ProgressBar.

    Clamped because an out-of-range percentage silently produces a meter of the
    wrong LENGTH rather than an error: `"█" * -1` is empty, while the remainder
    term grows past METER_WIDTH. Unreachable from `data.py` today, but this
    helper is the kind of thing a later caller passes a raw number to.
    """
    filled = round(max(0.0, min(100.0, pct)) / 100 * METER_WIDTH)
    return "█" * filled + "░" * (METER_WIDTH - filled)


def cohort_summary(state) -> list[dict]:
    prefix = "cohort"
    cohort = data.get_cohort(state)
    stats = cohort["stats"]
    pending = len(cohort["stragglers"])
    note = data.milestone_line(state)
    if pending:
        plural = "student needs" if pending == 1 else "students need"
        note += f" {pending} {plural} a personal message from you."

    components = [
        text(f"{prefix}-label", "EEE SEM 3 · SEC B — CERTIFIED", "caption"),
        text(f"{prefix}-value", f"{stats['activated']} / {stats['size']}", "h2"),
        text(f"{prefix}-meter", meter(stats["pct"])),
        text(f"{prefix}-pct", f"{stats['pct']}%"),
        text(f"{prefix}-note", note),
    ]
    components.append(row(f"{prefix}-meter-row",
                          [f"{prefix}-meter", f"{prefix}-pct"]))
    child_ids = [f"{prefix}-label", f"{prefix}-value", f"{prefix}-meter-row",
                 f"{prefix}-note"]

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
    students = data.get_stragglers(state)["data"]
    components: list[dict] = []
    child_ids: list[str] = []

    for entry in students:
        sid = entry["studentId"]
        base = f"{prefix}-{sid}"
        draft = data.draft_for(sid)
        components.extend([
            text(f"{base}-name", entry["name"], "h5"),
            text(f"{base}-meta", entry["context"], "caption"),
            text(f"{base}-msg", draft),
            text(f"{base}-link", entry["waLink"], "caption"),
            text(f"{base}-send-label", "Send from my WhatsApp"),
            button(f"{base}-send", f"{base}-send-label", "send_whatsapp",
                   {"student_id": sid}),
            text(f"{base}-edit-label", "Edit"),
            button(f"{base}-edit", f"{base}-edit-label", "open_edit",
                   {"student_id": sid}),
            row(f"{base}-actions", [f"{base}-send", f"{base}-edit"]),
            column(f"{base}-column", [
                f"{base}-name", f"{base}-meta", f"{base}-msg",
                f"{base}-link", f"{base}-actions",
            ]),
            card(f"{base}-card", f"{base}-column"),
        ])
        child_ids.append(f"{base}-card")

    components.append(text(
        f"{prefix}-foot",
        "You send from your own WhatsApp — I never send as you."
        " Your link carries your credit.",
        "caption"))
    child_ids.append(f"{prefix}-foot")

    components.append(column(f"{prefix}-main-column", child_ids))
    return surface(prefix, components, f"{prefix}-main-column")


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
    for index, entry in enumerate(board["data"]):
        # Her section rides along in the head so her row reads "#19  You —
        # EEE Sem 3 · Sec B" -- the marker is text, never colour, per the
        # fairness rule, so it has to sit next to the name that carries it.
        head = f"#{entry['rank']}  {entry['name']} — {entry['cohortSection']}"
        detail = f"{entry['pct']}% · {entry['activated']} / {entry['size']}"
        made, card_id = _entry_card(prefix, f"r{index}",
                                    [("head", head), ("detail", detail)])
        components.extend(made)
        child_ids.append(card_id)

    components.append(text(f"{prefix}-basis",
                           "Ranked on % of section activated"
                           " · under-30 sections pooled"
                           " · verified activations only", "caption"))
    components.append(text(f"{prefix}-foot", fixtures_board_footnote(),
                           "caption"))
    child_ids.extend([f"{prefix}-basis", f"{prefix}-foot"])
    components.append(column(f"{prefix}-main-column", child_ids))
    return surface(prefix, components, f"{prefix}-main-column")


def rewards(state) -> list[dict]:
    prefix = "rew"
    components, child_ids = [], []
    for index, tier in enumerate(data.get_rewards(state)):
        # Every tier states its threshold. "Starter" and "Half-way" do not
        # carry a percentage in their names, so dropping "at 25%" from earned
        # rows loses the column the prototype's table showed for all four.
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
    components, child_ids = [], []
    for index, entry in enumerate(data.get_roster(state)):
        made, card_id = _entry_card(prefix, f"s{index}", [
            ("head", entry["name"]),
            ("detail", f"{entry['status']} · {entry['how']}"),
        ])
        components.extend(made)
        child_ids.append(card_id)
    components.append(text(f"{prefix}-foot", fixtures_roster_footnote(),
                           "caption"))
    child_ids.append(f"{prefix}-foot")
    components.append(column(f"{prefix}-main-column", child_ids))
    return surface(prefix, components, f"{prefix}-main-column")


def fixtures_board_footnote():
    from . import fixtures
    return fixtures.BOARD_FOOTNOTE


def fixtures_roster_footnote():
    from . import fixtures
    return fixtures.ROSTER_FOOTNOTE


def fixtures_angles():
    # Kept as a function, not a module-level `from . import fixtures`, so
    # surfaces.py never imports fixtures directly -- data.py is the only
    # module allowed to know the backend is fixtures today.
    from . import fixtures
    return fixtures.ANGLES


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
    entry = data.student(student_id)
    if entry is None:
        raise KeyError(student_id)
    first = entry["name"].split(" ")[0]
    sent = data.is_sent(state, student_id)
    angle = (state.get("angles", {}) or {}).get(student_id, "Exam panic")
    draft = (state.get("drafts", {}) or {}).get(student_id) \
        or data.draft_for(student_id, angle)

    title = (f"Sent — {entry['name']}" if sent
             else f"Edit before sending — {entry['name']}")
    cta = f"Sent to {first} ✓" if sent else f"Send to {first}"

    components = [
        text(f"{prefix}-heading", title, "h5"),
        text(f"{prefix}-angle-label", "Angle", "caption"),
    ]
    angle_ids = []
    for index, (name, _hint) in enumerate(fixtures_angles()):
        marker = "● " if name == angle else "○ "
        components.append(text(f"{prefix}-a{index}-label", marker + name))
        components.append(button(f"{prefix}-a{index}", f"{prefix}-a{index}-label",
                                 "set_angle",
                                 {"student_id": student_id, "angle": name}))
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
