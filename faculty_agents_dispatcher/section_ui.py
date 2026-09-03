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
SAVE_LINK = 'save_agent_link'

# Ends manual section picking. Without it, picking has to end when something
# else happens to be true — and it did: the first tap jumped to naming the
# agent as soon as a link had been pasted, so one section was the most anyone
# could choose in the order the Send Agent card actually asks for.
DONE_PICKING = 'done_picking_sections'
SAVE_NAME = 'save_agent_name'
CONFIRM_SEND = 'confirm_send'
CANCEL_SEND = 'cancel_send'
NAME_PATH = '/agent_name'

# Where the ticked sections collect in the data model.
SECTIONS_PATH = '/sections'

# Choosing an agent instead of pasting its link.
PICK_AGENT = 'pick_agent'
PASTE_INSTEAD = 'paste_link_instead'
AGENT_PATH = '/agent'


if SHOW_SECTIONS != progress_ui.SECTION_LIST:  # pragma: no cover
    # A plain `assert` would vanish under `python -O`, and the failure it
    # guards against is a button that quietly dispatches to nothing.
    raise RuntimeError(
        'SHOW_SECTIONS and progress_ui.SECTION_LIST have diverged; the Section '
        'List button on the department card would dispatch to nothing.'
    )


def name_card(state, already_published: bool = False,
              suggested: str = '') -> list:
    """Name the agent, then publish it — or just rename an existing one.

    `suggested` pre-fills the field with the name the agent already has in
    Gemini Enterprise. It is a starting point, not the answer: one GE agent is
    often sent to several different section sets, and each send deserves its
    own label — "DBMS — CSE Year 2" and "DBMS — CIVIL Year 3" can be the same
    underlying agent.

    Naming here writes Sethu's own record and nothing else. There is no write
    path to Discovery Engine from this agent, so the agent a student opens
    keeps whatever it is called in Gemini Enterprise.
    """
    prefix = a2ui.uid(state, 'name')
    label = 'Save Agent Name' if already_published else 'Publish'
    action = SAVE_NAME if already_published else PUBLISH

    components = [
        a2ui.text(f'{prefix}-title', 'What should this agent be called?', 'h3'),
        a2ui.text(f'{prefix}-hint',
                  'This is the name on the announcement your students get. '
                  'It does not rename the agent itself.'),
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
            [f'{prefix}-title', f'{prefix}-hint', f'{prefix}-field',
             f'{prefix}-btn'],
        ),
        a2ui.card(f'{prefix}-card', f'{prefix}-main-column'),
    ]
    messages = a2ui.surface(prefix, components, f'{prefix}-card')
    messages.insert(1, a2ui.data_model(prefix, {'agent_name': suggested or ''}))
    return messages



def result_card(state, title: str, lines: list) -> list:
    """The outcome of a send, in a card of its own.

    A send is the one irreversible thing this agent does, and its result was a
    line of prose sitting above the menu — the same weight as every other
    sentence in the conversation. Giving it a card and a heading makes it the
    thing the eye lands on.
    """
    return a2ui.build_card(
        a2ui.uid(state, 'result'), [title] + list(lines)
    )


def agent_picker_card(state, agents: list) -> list:
    """Pick the agent to send, instead of pasting its link.

    Sethu's sync knows every agent in Gemini Enterprise and now returns a
    composed link for each, so the professor never has to find a URL. That
    removes the step every link problem came from: an address bar carries the
    copier's account index, their chat session and their analytics id, and
    nothing stops them copying the wrong page entirely — two live records point
    at an agent nobody meant to send.

    Single-select: one agent goes to one set of sections.
    """
    prefix = a2ui.uid(state, 'agentpick')
    # Just the agent's name. What it was called on a previous send is a
    # property of that send, not of the agent being chosen now.
    options = [(agent['name'], agent['id']) for agent in agents]

    components = [
        a2ui.text(f'{prefix}-title', 'Which agent do you want to send?', 'h3'),
        # "Pick one agent", not a description of the list. Gemini Enterprise
        # draws MultipleChoice with checkboxes whatever the limit — the v0.8
        # catalog has no radio button — so a single-select list looks like a
        # multi-select one and professors tried to tick several.
        a2ui.text(f'{prefix}-hint', 'Pick one agent.'),
        a2ui.multiple_choice(f'{prefix}-choice', AGENT_PATH, options,
                             max_selections=1),
    ]
    for suffix, label, action in (
        ('go', 'Continue', PICK_AGENT),
        ('paste', 'Paste a link instead', PASTE_INSTEAD),
    ):
        components.append(a2ui.text(f'{prefix}-{suffix}-label', label))
        components.append(a2ui.button_with_values(
            f'{prefix}-{suffix}', f'{prefix}-{suffix}-label', action,
            {'agent': {'path': AGENT_PATH}}))
    components.append(a2ui.row(f'{prefix}-buttons',
                               [f'{prefix}-go', f'{prefix}-paste']))
    components.append(a2ui.column(
        f'{prefix}-main-column',
        [f'{prefix}-title', f'{prefix}-hint', f'{prefix}-choice',
         f'{prefix}-buttons']))
    components.append(a2ui.card(f'{prefix}-card', f'{prefix}-main-column'))

    messages = a2ui.surface(prefix, components, f'{prefix}-card')
    messages.insert(1, a2ui.data_model(prefix, {'agent': []}))
    return messages


def scope_card(state, agent_name: str) -> list:
    """How much of the college this agent goes to.

    The same three choices as the Send Agent card, without the link field —
    once an agent is picked there is no link to type.
    """
    return a2ui.build_card(
        a2ui.uid(state, 'scope'),
        [f'Who should get "{agent_name}"?'],
        [
            ('All Departments', SCOPE_ALL, None),
            ('Department – All Sections', SCOPE_DEPARTMENT, None),
            ('Manual Selection', SCOPE_MANUAL, None),
        ],
    )


def link_card(state) -> list:
    """Ask for the agent link on its own.

    Needed because sections can be chosen before a link is pasted — the scope
    buttons carry the link field, but nothing makes a professor fill it in. The
    Send Agent card cannot be reused here: pressing one of its scope buttons
    again would overwrite the sections they have just picked.
    """
    prefix = a2ui.uid(state, 'link')
    components = [
        a2ui.text(f'{prefix}-title', 'Paste the agent link', 'h3'),
        a2ui.text_field(f'{prefix}-field', 'Agent link', LINK_PATH, 'shortText'),
        a2ui.text(f'{prefix}-btn-label', 'Continue'),
        a2ui.button_with_values(
            f'{prefix}-btn',
            f'{prefix}-btn-label',
            SAVE_LINK,
            {'agent_link': {'path': LINK_PATH}},
        ),
        a2ui.column(
            f'{prefix}-main-column',
            [f'{prefix}-title', f'{prefix}-field', f'{prefix}-btn'],
        ),
        a2ui.card(f'{prefix}-card', f'{prefix}-main-column'),
    ]
    messages = a2ui.surface(prefix, components, f'{prefix}-card')
    messages.insert(1, a2ui.data_model(prefix, {'agent_link': ''}))
    return messages


def confirm_send_card(state, sections: list, count, agent_id: str) -> list:
    """The last step before real WhatsApp messages go out.

    The sections are listed one per line rather than run together in a
    sentence. This is the card a professor checks before something
    irreversible, and "CSE · Year 2 · Sec A, CSE · Year 1 · Sec A and CSE ·
    Year 3 · Sec A" is a paragraph to be parsed rather than a list to be
    checked — the labels are long and nearly identical, which is exactly when
    a wrong one goes unnoticed.

    A Yes button rather than typed text: the professor is confirming something
    that cannot be recalled, and a button carries the exact agent id, so a
    confirmation can never be applied to a different agent than the one quoted.
    """
    labels = [str(label) for label in (sections or [])]
    students = f'{count} student' + ('' if count == 1 else 's')
    heading = (f'{len(labels)} section' + ('' if len(labels) == 1 else 's')
               + f' · {students}')

    # Capped so a college-wide send cannot push the card past the size ceiling
    # and vanish at the one moment it matters most.
    shown = list(labels[:12])
    if len(labels) > 12:
        shown.append(f'and {len(labels) - 12} more')

    lines = ['Send this agent over WhatsApp?', heading, a2ui.DIVIDER,
             'Going to:', a2ui.bullets(shown), a2ui.DIVIDER,
             'WhatsApp messages cannot be recalled.']

    return a2ui.build_card(
        a2ui.uid(state, 'confirm'),
        lines,
        [
            ('Yes, send it', CONFIRM_SEND, {'agent_id': agent_id}),
            # Cancel carries the id too. The card stays on screen after the
            # send, so a professor can scroll back and press Cancel on a send
            # that already went out — and without the id there is no way to
            # tell that from a genuine cancellation.
            ('Cancel', CANCEL_SEND, {'agent_id': agent_id}),
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


def section_list_card(state, roster: list, department: str) -> list:
    """The department's sections as a list, with nothing to press.

    Browsing is not the first step of a send. Offering the same tappable
    buttons here starts recording sections for a send the professor never
    asked to make — which is what "Selected CIVIL · Year 4 · Sec A (1 so far)"
    was, after a plain look at the section list.
    """
    rows = [s for s in roster if s.get('department') == department]
    if not rows:
        return []

    lines = [f'{department} — sections']
    lines += [
        f'·  Year {s.get("year")} · Sec {s.get("section")}  —  '
        f'{s.get("students") or 0} '
        f'{"student" if (s.get("students") or 0) == 1 else "students"}'
        for s in rows
    ]

    # The other departments, on the card itself. Browsing the roster means
    # comparing departments, and going back to the department list between
    # every one of them makes that a round trip each time.
    others = [d for d in departments(roster) if d != department]
    counts = {
        d: sum(s.get('students') or 0 for s in roster
               if s.get('department') == d)
        for d in others
    }
    buttons = [(f'{d} ({counts[d]})', PICK_DEPARTMENT, {'department': d})
               for d in others]
    if buttons:
        lines.append('Another department:')

    prefix = a2ui.uid(state, 'seclist')
    messages = a2ui.build_card(prefix, lines, buttons)
    # Trim sections rather than risk the ceiling, exactly as `section_card`
    # does — the department buttons are the way out of this card and are kept
    # even when the list is cut short.
    while not _fits(messages) and len(lines) > 2:
        lines.pop(1)
        messages = a2ui.build_card(
            prefix, lines + ['Showing the first few.'], buttons
        )
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
        ['Which department?',
         'The number in brackets is how many students that department has.'],
        [
            (f'{d} ({counts[d]})', PICK_DEPARTMENT, {'department': d})
            for d in names
        ],
    )


def section_card(state, roster: list, department: str,
                 chosen: int = 0) -> list:
    """Tick the sections to send to, then press Done.

    One card, one decision. Before this the picker redrew after every tap, so
    choosing four sections meant four round trips and four near-identical cards
    stacked up the transcript.

    `MultipleChoice` collects the ticks in the data model and Done carries them
    back, the same way TextField carries a typed link — an array rather than a
    string. `chosen` is how many are already held from other departments, shown
    so a professor switching department can see nothing was lost.
    """
    rows = [s for s in roster if s.get('department') == department]
    if not rows:
        return []

    prefix = a2ui.uid(state, 'secs')
    lines = [f'{department} — choose who to send to',
             'Tick every section this agent should go to, then press Done.']
    if chosen:
        lines.append(f'{chosen} already selected in other departments.')

    components = [a2ui.text(f'{prefix}-title', lines[0], 'h3')]
    for index, line in enumerate(lines[1:], 1):
        components.append(a2ui.text(f'{prefix}-line{index}', line))
    components.append(a2ui.multiple_choice(
        f'{prefix}-choice', SECTIONS_PATH,
        [(f'Year {s.get("year")} · Sec {s.get("section")}'
          f' ({s.get("students") or 0} '
          f'{"student" if (s.get("students") or 0) == 1 else "students"})',
          s['label']) for s in rows],
    ))

    # Both buttons carry the ticks, so switching department keeps them.
    picked = {'sections': {'path': SECTIONS_PATH}}
    for suffix, label, action in (
        ('done', 'Done', DONE_PICKING),
        ('more', 'Another Department', SCOPE_MANUAL),
    ):
        components.append(a2ui.text(f'{prefix}-{suffix}-label', label))
        components.append(a2ui.button_with_values(
            f'{prefix}-{suffix}', f'{prefix}-{suffix}-label', action, picked))
    components.append(a2ui.row(f'{prefix}-buttons',
                               [f'{prefix}-done', f'{prefix}-more']))
    components.append(a2ui.column(
        f'{prefix}-main-column',
        [f'{prefix}-title']
        + [f'{prefix}-line{i}' for i in range(1, len(lines))]
        + [f'{prefix}-choice', f'{prefix}-buttons'],
    ))
    components.append(a2ui.card(f'{prefix}-card', f'{prefix}-main-column'))

    messages = a2ui.surface(prefix, components, f'{prefix}-card')
    messages.insert(1, a2ui.data_model(prefix, {'sections': []}))
    return messages
