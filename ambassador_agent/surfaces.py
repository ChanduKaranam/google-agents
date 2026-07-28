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
from .a2ui import button, card, column, row, surface, text

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
