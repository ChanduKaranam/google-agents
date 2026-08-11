"""Section pickers, built from the primitives in `a2ui.py`.

Why a drill-down rather than one long list: Gemini Enterprise drops a surface
over ~6KB silently — the text arrives and the card simply does not. A single
card of all 55 sections measures 6.4KB, so it would vanish for the larger
tenant while working fine for the smaller one, with nothing logged either way.

Two cards, each comfortably small:

    "which sections?"  ->  department card   (one button per department)
    tap "CSE"          ->  section card      (that department's sections)
    tap a section      ->  the agent has an exact roster label

Only Button carries an action in the v0.8 catalog, so every choice is a button.
That is also why the label doubles as the payload: the action context carries
the exact `label` string `publish_agent` needs, so nothing is retyped or
guessed at any point.
"""

import json

from . import a2ui, config, progress_ui

# Action names the click handler dispatches on.
PICK_DEPARTMENT = 'pick_department'
PICK_SECTION = 'pick_section'

# Opening menu.
START_SEND = 'start_send'
SHOW_SECTIONS = 'show_sections'

# How much of the college a send covers. Chosen before any section is picked,
# because it changes what the department buttons then mean.
SCOPE_ALL = 'scope_all_departments'
SCOPE_DEPARTMENT = 'scope_department_all_sections'
SCOPE_MANUAL = 'scope_manual'

# Where the pasted agent link lives in the surface data model. A TextField
# cannot notify the agent on its own — only a Button dispatches — so every
# button on that card carries this path in its action context.
LINK_PATH = '/agent_link'

# Whether the opening menu has already been drawn this conversation. It now
# rides under every reply, and "How can I help you?" on the twentieth card
# reads as though nothing has been said yet.
MENU_SHOWN = 'menu_shown'

# Naming, publishing, and the send confirmation.
PUBLISH = 'publish_agent'
SAVE_NAME = 'save_agent_name'
CONFIRM_SEND = 'confirm_send'
CANCEL_SEND = 'cancel_send'
NAME_PATH = '/agent_name'


if SHOW_SECTIONS != progress_ui.SECTION_LIST:  # pragma: no cover
    # A plain `assert` would vanish under `python -O`, and the failure it
    # guards against is a button that quietly dispatches to nothing.
    raise RuntimeError(
        'SHOW_SECTIONS and progress_ui.SECTION_LIST have diverged; the Section '
        'List button on the department card would dispatch to nothing.'
    )


def name_card(state, already_published: bool = False) -> list:
    """Name the agent, then publish it — or just rename an existing one."""
    prefix = a2ui.uid(state, 'name')
    label = 'Save Agent Name' if already_published else 'Publish'
    action = SAVE_NAME if already_published else PUBLISH

    components = [
        a2ui.text(f'{prefix}-title', 'What should this agent be called?', 'h3'),
        a2ui.text_field(f'{prefix}-field', 'Agent name', NAME_PATH, 'shortText'),
        a2ui.text(f'{prefix}-btn-label', label),
        a2ui.button_with_values(
            f'{prefix}-btn',
            f'{prefix}-btn-label',
            action,
            {'agent_name': {'path': NAME_PATH}},
        ),
        a2ui.column(
            f'{prefix}-main-column',
            [f'{prefix}-title', f'{prefix}-field', f'{prefix}-btn'],
        ),
        a2ui.card(f'{prefix}-card', f'{prefix}-main-column'),
    ]
    messages = a2ui.surface(prefix, components, f'{prefix}-card')
    messages.insert(1, a2ui.data_model(prefix, {'agent_name': ''}))
    return messages


def confirm_send_card(state, sections_text: str, count, agent_id: str) -> list:
    """The last step before real WhatsApp messages go out.

    A Yes button rather than typed text: the professor is confirming something
    that cannot be recalled, and a button carries the exact agent id, so a
    confirmation can never be applied to a different agent than the one quoted.
    """
    prefix = a2ui.uid(state, 'confirm')
    return a2ui.build_card(
        prefix,
        [
            'Send this agent over WhatsApp?',
            f'{sections_text} — {count} student{"s" if count != 1 else ""}',
            'WhatsApp messages cannot be recalled.',
        ],
        [
            ('Yes, send it', CONFIRM_SEND, {'agent_id': agent_id}),
            ('Cancel', CANCEL_SEND, None),
        ],
    )


# A greeting is answered in code, not by the model. Asked to "call the tool and
# then say a short line", the model reliably skips the tool and says the line —
# leaving the professor looking at a question with no buttons under it. There is
# nothing to reason about here, so nothing is left to reason about it.
_GREETINGS = frozenset({
    'hi', 'hii', 'hiii', 'hey', 'heya', 'hello', 'helo', 'hlo', 'yo',
    'good morning', 'good afternoon', 'good evening', 'greetings',
    'hi there', 'hello there', 'start', 'menu', 'help',
    'what can you do', 'what can you do?', 'how does this work',
    'how does this work?',
})


def _normalise(text: str) -> str:
    """Letters, digits and spaces only.

    Punctuation is dropped, question mark included, so "how is my department
    doing" matches whether or not the professor typed the "?". The greeting set
    already lists both forms of each phrase, so nothing there depends on it.
    """
    return ' '.join(
        ''.join(ch for ch in (text or '').lower()
                if ch.isalnum() or ch.isspace()).split()
    )


def is_greeting(text: str) -> bool:
    """Whether an opening message is small talk rather than a request."""
    cleaned = _normalise(text)
    return bool(cleaned) and cleaned in _GREETINGS


# The starter prompts advertised on the agent card (`agent_card.json`,
# skills[].examples). Gemini Enterprise shows them on the opening screen and
# sends the literal text when one is tapped, so each is mapped to the button it
# stands for and answered by that button's handler.
#
# Left to the model, "Send an agent to my students" produces a sentence asking
# for a link while the card that has the link field never appears — a starter
# prompt that does not deliver what it advertises is worse than no starter
# prompt at all.
_STARTERS = {
    'send an agent to my students': START_SEND,
    'show the section list': SHOW_SECTIONS,
    'how is my department doing': progress_ui.MENU_DEPARTMENT,
    'show the leaderboard': progress_ui.MENU_LEADERBOARD,
    'who are my ambassadors': progress_ui.MENU_AMBASSADORS,
    'show ambassadors': progress_ui.MENU_AMBASSADORS,
    'show my ambassadors': progress_ui.MENU_AMBASSADORS,
    'how are my agents used': progress_ui.MENU_AGENT_USAGE,
}


def starter_action(text: str) -> str | None:
    """The button action a starter prompt stands for, if it is one."""
    return _STARTERS.get(_normalise(text))


def main_menu(state) -> list:
    """The opening card: what the professor can do.

    The read-only views are questions the model will answer on request, but a
    professor who does not know to ask never learns they exist — so the
    greeting is where the inventory is shown.

    Only the top of that inventory. The ranking and the section roster are both
    readings of the department card, and hang off it instead; six buttons here
    made the opening card a wall of blue.
    """
    # The greeting asks the open question; after that the same card is just
    # the way back, so it says so instead of starting the conversation over.
    heading = 'How can I help you?'
    if state is not None:
        if state.get(MENU_SHOWN):
            heading = 'Anything else?'
        state[MENU_SHOWN] = True

    buttons = [('Send Agent', START_SEND, None)]
    for action, (label, _view, _line) in progress_ui.MENU_VIEWS.items():
        if (action == progress_ui.MENU_AMBASSADORS
                and not config.AMBASSADOR_VIEW_ENABLED):
            continue
        # The ranking and the section roster live on the department card, one
        # tap further in. Six buttons here made the opening card a wall.
        if action == progress_ui.MENU_LEADERBOARD:
            continue
        buttons.append((label, action, None))
    # One straight row. These four labels total 43 characters, comfortably
    # inside the ~63 measured before Gemini Enterprise clipped a button, so
    # this card gets a wider budget than the conservative default.
    return a2ui.build_card(
        a2ui.uid(state, 'menu'), [heading], buttons,
        row_budget=60, row_cap=4,
    )


def send_agent_card(state) -> list:
    """Paste-the-link field, plus how widely to send it.

    Built by hand rather than with `build_card` because that helper only does
    text lines and buttons, and this card needs an input bound to the data
    model.
    """
    prefix = a2ui.uid(state, 'send')
    scopes = [
        ('All Departments', SCOPE_ALL),
        ('Department – All Sections', SCOPE_DEPARTMENT),
        ('Manual Selection', SCOPE_MANUAL),
    ]

    components = [
        a2ui.text(f'{prefix}-title', 'Paste the agent link', 'h3'),
        a2ui.text_field(f'{prefix}-link', 'Agent link', LINK_PATH, 'shortText'),
        a2ui.text(f'{prefix}-hint', 'Then choose who it goes to:'),
    ]
    button_ids = []
    for index, (label, action) in enumerate(scopes):
        label_id = f'{prefix}-scope{index}-label'
        button_id = f'{prefix}-scope{index}'
        components.append(a2ui.text(label_id, label))
        components.append(
            a2ui.button_with_values(
                button_id,
                label_id,
                action,
                # The link travels with whichever button is pressed; there is
                # no other way for a typed value to reach the agent.
                {'agent_link': {'path': LINK_PATH}},
            )
        )
        button_ids.append(button_id)

    # "Department – All Sections" is 25 characters on its own; three of these
    # side by side run straight off the card.
    scope_rows, scope_row_ids = a2ui.button_rows(
        prefix, [label for label, _ in scopes], button_ids
    )
    components += scope_rows
    components.append(
        a2ui.column(
            f'{prefix}-main-column',
            [
                f'{prefix}-title',
                f'{prefix}-link',
                f'{prefix}-hint',
                *scope_row_ids,
            ],
        )
    )
    components.append(a2ui.card(f'{prefix}-card', f'{prefix}-main-column'))

    messages = a2ui.surface(prefix, components, f'{prefix}-card')
    messages.insert(1, a2ui.data_model(prefix, {'agent_link': ''}))
    return messages


def _fits(messages: list) -> bool:
    return (
        len(json.dumps(messages, ensure_ascii=False).encode())
        < a2ui.SURFACE_BYTE_CEILING
    )


def departments(roster: list) -> list:
    """Department names, in roster order, without duplicates."""
    seen = []
    for section in roster:
        dept = section.get('department')
        if dept and dept not in seen:
            seen.append(dept)
    return seen


def department_card(state, roster: list) -> list:
    """Step one: which department."""
    names = departments(roster)
    counts = {
        d: sum(s.get('students') or 0 for s in roster if s.get('department') == d)
        for d in names
    }
    return a2ui.build_card(
        a2ui.uid(state, 'depts'),
        ['Which department?'],
        [
            (f'{d} ({counts[d]})', PICK_DEPARTMENT, {'department': d})
            for d in names
        ],
    )


def section_card(state, roster: list, department: str) -> list:
    """Step two: which section within the chosen department.

    Falls back to fewer buttons rather than risking the size ceiling — a
    truncated card the professor can see beats a complete one GE discards.
    """
    rows = [s for s in roster if s.get('department') == department]
    if not rows:
        return []

    def build(subset, note=None):
        lines = [f'{department} — pick a section']
        if note:
            lines.append(note)
        return a2ui.build_card(
            a2ui.uid(state, 'secs'),
            lines,
            [
                (
                    f'Year {s.get("year")} · Sec {s.get("section")}'
                    f' ({s.get("students") or 0})',
                    PICK_SECTION,
                    {'label': s['label']},
                )
                for s in subset
            ],
        )

    messages = build(rows)
    while not _fits(messages) and len(rows) > 1:
        rows = rows[:-1]
        messages = build(rows, 'Showing the first few; ask for more if needed.')
    return messages
