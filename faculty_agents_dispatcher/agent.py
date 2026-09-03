import contextvars
import logging

from google.adk.agents.callback_context import CallbackContext
from google.adk.agents.llm_agent import Agent
from google.adk.agents.readonly_context import ReadonlyContext
from google.genai import types

from . import a2ui, auth, config, progress_ui, section_ui, sethu_client, tools
from .sethu_client import SethuError
from .tools import (
    diagnose_identity,
    find_agent_by_link,
    list_college_sections,
    prepare_send,
    publish_agent,
    send_agent_to_sections,
    show_agent_usage,
    show_ambassadors,
    show_department_progress,
    show_leaderboard,
    show_main_menu,
    show_section_picker,
)

# How step 2 gathers sections differs by runtime, because the tools do. On
# Agent Engine the agent reads the roster and talks; on the A2A runtime it
# draws a card the professor taps.
_SECTIONS_STEP_PROSE = """\
   Call `list_college_sections` to check what they said against the roster.
   - If exactly one section matches what they said, use it.
   - If they left something out, or more than one matches, ask only for what is
     missing and show the candidates by their `label`.
   - If nothing matches, say so and show the labels that come closest.
   If it returns an error, say plainly that you could not verify the section,
   and ask them to confirm the exact department, year and section. Do not
   silently proceed."""

_SECTIONS_STEP_CARDS = """\
   - If the professor named a section precisely enough that exactly one could
     match, use it as they said it. `publish_agent` checks it against the
     roster and refuses anything it cannot resolve.
   - In every other case you MUST call `show_section_picker` before you reply.
     That includes: they were vague, gave only a section letter, want several
     sections, asked which sections exist, or you are unsure.
   You cannot show a professor the sections yourself. Buttons appear under your
   reply only when `show_section_picker` has actually run in this turn. If you
   have not called it, do not mention departments or sections at all — saying
   they are below when no tool ran leaves the professor staring at nothing.
   Once it has run, add one short sentence of your own and stop. Do not list
   the departments, do not describe the buttons.
   Taps are handled before you run, so a chosen section may already be recorded
   when you next reply. If it returns an error, say plainly that you could not
   load the sections and ask them to confirm the exact department, year and
   section."""

logger = logging.getLogger(__name__)

INSTRUCTION = """\
You are Champion Faculty. Your job is to help professors send their newly created
AI agents to their students over WhatsApp.

You already know who the professor is — Sethu identifies them from their Google
sign-in. Never ask for their name, college, department or any id.

How to handle a request:

0. Greetings never reach you — they are answered with a menu of buttons before
   you run. If you are asked what you can do mid-conversation, call
   `show_main_menu` and then add one short sentence of your own. The buttons
   appear underneath it; never list the options in words, and never claim
   buttons are there unless the tool actually ran this turn.
   Button taps are also handled before you run, so the professor may arrive at
   you with a link, a scope, or sections already recorded — read what is in the
   conversation rather than asking again for something they have given.

1. The professor gives you a link to an agent they created and asks you to
   share it. Call `find_agent_by_link` first.
   - If it is already published, you have its sections and student count
     already. Go to step 4 using `prepare_send`.
   - If it is not published, continue to step 2.

2. Work out what to publish it as. You need two things:
   - the sections, identified by Section, Year and Branch
     (e.g. "Section A, 2nd year, CSE");
   - a name for the agent.
   Never ask for a semester. Sethu does not use one.
   Professors are not tied to particular sections — any of them may send to any
   section in the college — so checking a section confirms it exists, it does
   not check ownership.
   Sections are identified by department, year and section together. A bare
   "Section A" is ambiguous: every department has one in every year.
{sections_step}
   Never guess a section, and never publish to one that is not on the roster.

3. Call `publish_agent`. This messages nobody — it registers the agent against
   those sections and tells you how many students that reaches.
   Sethu cannot delete or re-point a published agent, so be sure of the
   sections before this step.

4. CRITICAL: You must then ask the professor for confirmation. Reply with
   exactly this sentence and nothing else:

   You are about to send this agent to <sections> (<count> students) via
   WhatsApp. Do you want to proceed?

   Write <sections> the way the professor would recognise it, e.g.
   "Section A, Year 2, CSE". For several sections, separate them with "and".

   A `note` on the tool result is internal detail about where the number came
   from. Use the `count` the tool gives you and do not repeat the note to the
   professor — they do not need to hear about Sethu's internals.

   If the tool returned a `warning`, do NOT send that sentence. Tell the
   professor what the warning says instead, and do not call
   `send_agent_to_sections`. A count of zero or a missing count means the send
   would reach nobody, and quoting it as if it were an audience would mislead
   them into confirming an empty blast.

5. If they say yes, call `send_agent_to_sections`, then tell them the send is
   complete and how many students it went to. If they say no, confirm that
   nothing was sent — and say the agent is still published to those sections,
   because it is.
   If it comes back `already_sent`, this agent has gone out before and nothing
   was sent this time. Reply with its `message` word for word, and do not call
   the tool again.

6. Questions about how students are doing are answered with a card, not by
   you. Call the matching tool and then add one short sentence of your own:
   - activation progress across sections -> `show_department_progress`
   - "the leaderboard", which sections are best -> `show_leaderboard`
   - ambassadors, or which sections have gone quiet -> `show_ambassadors`
   - how much the professor's own agents are used -> `show_agent_usage`
   These read data and message nobody, so they need no confirmation.
   Never quote a figure from one of these cards in your own words. The card
   carries every number; repeating one is how a number the tool never returned
   ends up in front of a professor. If a tool returns an error, say what it
   says and quote nothing.

Rules:
- Never call `send_agent_to_sections` before the professor has confirmed.
- If the professor changes the sections after publishing, say plainly that the
  published agent cannot be re-pointed and ask whether to publish a second one.
- If a tool returns an error, tell the professor plainly what went wrong and
  what you need from them. Never claim messages were sent when they were not.
- `diagnose_identity` is for troubleshooting sign-in only. Do not call it as
  part of a normal send.
- Agent ids are internal. Talk about sections and agents by their human names.
""".replace(
    '{sections_step}',
    _SECTIONS_STEP_CARDS if config.A2UI_ENABLED else _SECTIONS_STEP_PROSE,
)


# The session state for the turn being answered, so `_reply` can draw the menu
# without every one of its two dozen call sites having to pass state through.
# A ContextVar rather than a module global because it is naturally scoped to
# the request that set it, which matters under concurrency — the same reason
# `identity.py` publishes the caller's token this way.
_TURN_STATE: contextvars.ContextVar = contextvars.ContextVar(
    'turn_state', default=None
)


def _is_menu(messages: list | None) -> bool:
    """Whether these messages are already the opening menu."""
    try:
        surface = messages[0]['surfaceUpdate']['surfaceId']
    except (TypeError, IndexError, KeyError):
        return False
    return str(surface).startswith('menu')


def _menu_parts(state, messages: list | None = None) -> list:
    """The opening menu, to sit under whatever else the turn is saying.

    Every reply ends with it so a professor always has somewhere to go next,
    rather than having to know what to type. Skipped when the reply already is
    the menu, which would otherwise draw it twice.
    """
    if state is None or not config.A2UI_ENABLED or _is_menu(messages):
        return []
    # A card with its own buttons is already somewhere to go. Stacking the
    # menu under it doubled every reply's height, and Gemini Enterprise
    # scrolls to the top of a new message — so each tap threw the conversation
    # upwards. Replies with no card, or a card that only reports something
    # (the send result), still get it.
    if a2ui.has_button(messages):
        return []
    # Someone Sethu will not act for gets the refusal and nothing else. The
    # menu is a list of things they cannot do; offering it invites them to
    # press buttons that can only fail.
    if state.get(auth.IS_FACULTY_KEY) is False:
        return []
    try:
        return a2ui.to_genai_parts(section_ui.main_menu(state))
    except Exception:  # A missing menu must never cost the actual answer.
        logger.exception('could not build the menu; answering without it')
        return []


def _reply(text: str, messages: list | None = None) -> types.Content:
    """A turn answered in code: prose, the card that goes with it, then the menu."""
    parts = [types.Part(text=text)]
    if messages:
        parts += a2ui.to_genai_parts(messages)
    parts += _menu_parts(_TURN_STATE.get(), messages)
    return types.Content(role='model', parts=parts)


def _roster(callback_context: CallbackContext) -> list:
    """The college roster, cached on the session after the first fetch."""
    state = callback_context.state
    roster = state.get(tools.ROSTER_CACHE)
    if roster:
        return roster
    roster = tools._call(callback_context, sethu_client.list_faculty_sections)
    state[tools.ROSTER_CACHE] = roster
    return roster


def _after_sections(state, text: str):
    """What to show once sections are chosen: the name, or the link first.

    Publishing needs both, and the sections can be settled first — the scope
    buttons carry the link field but nothing obliges a professor to type in it.
    Asking for a name at that point produces an agent that cannot be published
    and a question the professor has no reason to expect.
    """
    if not state.get(tools.PENDING_LINK):
        return _reply(f'{text} Now paste the agent link.',
                      section_ui.link_card(state))
    return _reply(text, section_ui.name_card(state))


def _sections_chosen(callback_context: CallbackContext, text: str):
    """After sections, ask what to call this send.

    An agent picked from the list arrives with a Gemini Enterprise name, which
    pre-fills the field — but it is still asked, because one agent goes to
    several different section sets and each send wants its own label.
    """
    state = callback_context.state
    if not state.get(tools.PENDING_LINK):
        return _reply(f'{text} Now paste the agent link.',
                      section_ui.link_card(state))
    return _reply(
        text,
        section_ui.name_card(
            state, suggested=state.get(tools.PICKED_NAME) or ''
        ),
    )


def _scope_or_sections(callback_context: CallbackContext, action: str, link: str):
    """Handle the scope buttons and the plain "Section List" button.

    All four need the roster, and all four are answered here rather than by the
    model, so a tap always produces a card.
    """
    state = callback_context.state
    try:
        roster = _roster(callback_context)
    except SethuError as exc:
        return _reply(f'I could not load the sections. {exc}')
    if not roster:
        return _reply('Sethu lists no sections for this college.')

    if action == section_ui.SCOPE_ALL:
        labels = [s['label'] for s in roster if s.get('label')]
        state[tools.CHOSEN_SECTIONS] = labels
        state[tools.SEND_SCOPE] = action
        total = sum(s.get('students') or 0 for s in roster)
        return _sections_chosen(
            callback_context,
            f'Every section selected — {_plural(len(labels), "section")} across '
            f'{_plural(len(section_ui.departments(roster)), "department")}, '
            f'{_plural(total, "student")}.',
        )

    if action in (section_ui.SCOPE_DEPARTMENT, section_ui.SCOPE_MANUAL):
        state[tools.SEND_SCOPE] = action
        prompt = (
            'Which department? Every section in it will be selected.'
            if action == section_ui.SCOPE_DEPARTMENT
            else 'Which department?'
        )
        return _reply(prompt, section_ui.department_card(state, roster))

    # Plain "Section List" — browsing, not sending. No question is being
    # asked here, so the card does not ask one.
    state[tools.SEND_SCOPE] = None
    return _reply(
        'Here are your departments — tap one to see its sections.',
        section_ui.department_card(state, roster, heading='Your departments'),
    )


def _plural(n, noun: str) -> str:
    return f'{n} {noun}' if n == 1 else f'{n} {noun}s'


def _outcome(state, title: str, lines: list, spoken: str):
    """Announce a send outcome, then clear the send and offer the menu.

    The card carries the result; `spoken` is the one line above it. Both say
    the same thing, because the card is what a professor reads and the prose is
    what a screen reader announces first.
    """
    card = section_ui.result_card(state, title, lines)
    _clear_send(state)
    return _reply(spoken, card)


def _clear_send(state) -> None:
    """Forget everything about the finished send. See `_finish`."""
    for key in (
        tools.PENDING_LINK,
        tools.CHOSEN_SECTIONS,
        tools.SEND_SCOPE,
        tools.PENDING_UI,
        tools.PICKED_NAME,
        tools.PICKING_DEPARTMENT,
    ):
        state[key] = None


def _finish(state, text: str):
    """End a send and offer the opening menu again.

    Everything about the finished send is cleared. Leaving a link or a section
    list behind would let the next send inherit it, and publishing is
    irreversible — a professor starting a second send must start from nothing.
    The roster is kept: it is the same college, and refetching it is wasted.
    """
    for key in (
        tools.PENDING_LINK,
        tools.CHOSEN_SECTIONS,
        tools.SEND_SCOPE,
        tools.PENDING_UI,
        tools.PICKED_NAME,
        tools.PICKING_DEPARTMENT,
    ):
        state[key] = None
    return _reply(text, section_ui.main_menu(state))


def _sections_text(labels: list) -> str:
    """How a professor would read a section list back."""
    if not labels:
        return 'no sections'
    if len(labels) == 1:
        return labels[0]
    if len(labels) <= 3:
        return ', '.join(labels[:-1]) + f' and {labels[-1]}'
    return f'{len(labels)} sections'


def _publish_and_confirm(callback_context: CallbackContext, name: str):
    """Publish, then offer a Yes button rather than asking them to type it."""
    state = callback_context.state
    link = state.get(tools.PENDING_LINK)
    labels = list(state.get(tools.CHOSEN_SECTIONS) or [])

    if not link:
        return _reply(
            'I still need the agent link. Paste it here and choose who it '
            'goes to.',
            section_ui.send_agent_card(state),
        )
    if not labels:
        return _reply('No sections are selected yet — pick who it goes to.',
                      section_ui.main_menu(state))
    if not name:
        return _reply('Type a name for the agent first.',
                      section_ui.name_card(state))

    state[tools.PICKED_NAME] = name

    result = tools.publish_agent(link, name, labels, callback_context)
    if result.get('status') == 'not_shared':
        # Plain text, no card. The steps were tried as four Text lines and
        # then as a List; both render with paragraph spacing between items, so
        # four short steps filled a phone screen either way. In the message
        # body they are four consecutive lines.
        return _reply(result['message'], section_ui.main_menu(state))
    if result.get('status') != 'success':
        return _reply(
            result.get('error_message')
            or result.get('message')
            or 'Publishing failed.'
        )
    if result.get('warning'):
        # Zero or unknown reach. Never offer a Yes button for a send that
        # would message nobody.
        return _reply(result['warning'])

    return _reply(
        f'Published "{name}".',
        section_ui.confirm_send_card(
            state,
            result.get('sections') or labels,
            result.get('count'),
            result['agent_id'],
        ),
    )


def _view_card(callback_context: CallbackContext, action: str,
               department: str = ''):
    """Draw a read-only view for a menu tap.

    The tool does the fetching and stages the payload; this reads it straight
    back out and paints. It cannot be left to `after_model`: returning Content
    from here ends the invocation, so nothing later runs to attach a staged
    card, and the professor gets a sentence with no card under it.
    """
    state = callback_context.state
    _label, view, line = progress_ui.MENU_VIEWS[action]
    fetch = {
        progress_ui.VIEW_DEPARTMENT: tools.show_department_progress,
        progress_ui.VIEW_LEADERBOARD: tools.show_leaderboard,
        progress_ui.VIEW_AMBASSADORS: tools.show_ambassadors,
        progress_ui.VIEW_AGENT_USAGE: tools.show_agent_usage,
    }[view]

    # Only the two department-scoped views take one; the others would reject
    # the keyword.
    result = (fetch(callback_context, department)
              if view in (progress_ui.VIEW_DEPARTMENT, progress_ui.VIEW_LEADERBOARD)
              else fetch(callback_context))
    if result.get('status') != 'success':
        return _reply(
            result.get('error_message', 'I could not load that just now.'),
            section_ui.main_menu(state),
        )

    # Answered here, so nothing is left staged for a later turn to paint.
    state[tools.PENDING_UI] = None
    payload = state.get(tools.VIEW_DATA)
    if payload is None:
        return _reply('I could not load that just now.',
                      section_ui.main_menu(state))
    return _reply(line, progress_ui.BUILDERS[view](state, payload, 0))


def _before_agent(callback_context: CallbackContext):
    """Resolve identity, then answer button presses deterministically.

    Returning Content here sets `end_invocation`, so the model never runs and
    `after_agent_callback` never runs either — which means a click must emit
    its own card here rather than staging one for later. Getting that wrong
    produces text and no card on every tap, which is the one interaction the
    cards exist for.
    """
    auth.resolve_identity(callback_context)
    if not config.A2UI_ENABLED:
        return None
    _TURN_STATE.set(callback_context.state)

    try:
        incoming = a2ui.incoming_text(callback_context)
        action = a2ui.parse_user_action(incoming)

        if not action:
            # A greeting is answered here rather than by the model, which has
            # been observed saying "how can I help you?" without calling the
            # tool that draws the buttons.
            text = '\n'.join(
                p.text
                for p in (
                    getattr(
                        getattr(callback_context, 'user_content', None),
                        'parts',
                        None,
                    )
                    or []
                )
                if getattr(p, 'text', None)
            )
            # A starter prompt from the agent card arrives as ordinary
            # text, not as a button press, so it is matched here and handed to
            # the same handler the button would have used.
            starter = section_ui.starter_action(text)
            if starter:
                action = {'name': starter, 'context': {}}
            elif section_ui.is_greeting(text):
                if auth.is_known_non_faculty(callback_context):
                    # No menu and no card. Same rule as every other reply,
                    # applied to the one path that passes its card in
                    # explicitly rather than letting `_reply` add it.
                    return _reply(
                        'This Google account is not registered with Sethu as '
                        'faculty, so I cannot act for it. Ask the Sethu team '
                        'to register it, then sign in again.'
                    )
                # A greeting is the one moment a professor is not waiting on
                # anything, so it is where the agent list gets refreshed. The
                # sync runs in the background and takes minutes, which is why
                # the reply says so rather than implying the list is current.
                tools.request_agent_sync(callback_context)
                who = auth.first_name(auth.display_name(callback_context))
                hello = f'Hi {who}, how can I help you?' if who else (
                    'How can I help you?'
                )
                hello += (
                    ' I am refreshing your agent list from Gemini Enterprise — '
                    'an agent you have just created can take a few minutes to '
                    'show up.'
                )
                return _reply(hello, section_ui.main_menu(callback_context.state))
            else:
                return None

        state = callback_context.state
        context = action.get('context') or {}
        name = action['name']

        # Every tap, not just the greeting. A professor who reopens an old
        # conversation never says hello again, so the greeting was the one
        # moment a sync could fire — and it had already fired, days ago. The
        # call itself is rate-limited to one per ten minutes per conversation.
        tools.request_agent_sync(callback_context)

        # A link typed into the card arrives with whichever button was pressed.
        link = (context.get('agent_link') or '').strip()
        if link:
            state[tools.PENDING_LINK] = link

        # So do the ticked sections, on Done and on Another Department alike —
        # which is what stops a department switch discarding them.
        ticked = context.get('sections')
        if ticked:
            if isinstance(ticked, str):
                ticked = [part.strip() for part in ticked.split(',')]
            chosen = list(state.get(tools.CHOSEN_SECTIONS) or [])
            for label in ticked:
                label = str(label).strip()
                if label and label not in chosen:
                    chosen.append(label)
            state[tools.CHOSEN_SECTIONS] = chosen

        if name == section_ui.DONE_PICKING:
            chosen = list(state.get(tools.CHOSEN_SECTIONS) or [])
            if not chosen:
                return _reply('Pick at least one section first.',
                              section_ui.main_menu(state))
            return _sections_chosen(
                callback_context, f'{_plural(len(chosen), "section")} selected.'
            )

        if name == section_ui.SAVE_LINK:
            # The link itself was stored above, if one was typed.
            if not state.get(tools.PENDING_LINK):
                return _reply('I still need the agent link — paste it here.',
                              section_ui.link_card(state))
            refusal = tools.readiness_refusal(state[tools.PENDING_LINK])
            if refusal:
                state[tools.PENDING_LINK] = None
                return _reply(refusal['message'],
                              section_ui.main_menu(state))
            if not state.get(tools.CHOSEN_SECTIONS):
                return _reply('Link saved. Now choose who it goes to.',
                              section_ui.send_agent_card(state))
            return _reply('Link saved.', section_ui.name_card(state))

        if name in (section_ui.PUBLISH, section_ui.SAVE_NAME):
            return _publish_and_confirm(
                callback_context, (context.get('agent_name') or '').strip()
            )

        if name == section_ui.CONFIRM_SEND:
            agent_id = context.get('agent_id')
            # The card stays on screen after the send, so this button can be
            # tapped again — and the tool's refusals are written for the model,
            # not for a professor. Classify the tap first and answer it here.
            status = tools.confirmation_status(state, agent_id)
            if status == 'sent':
                return _finish(state, tools.ALREADY_SENT_MESSAGE)
            if status == 'stale':
                return _finish(state, tools.STALE_CONFIRMATION_MESSAGE)
            result = tools.send_agent_to_sections(agent_id, callback_context)
            if result.get('status') == 'already_sent':
                return _finish(state, result['message'])
            if result.get('status') == 'not_shared':
                return _reply(result['message'], section_ui.main_menu(state))
            if result.get('status') != 'success':
                # Keep the send state either way: they may want to retry once
                # the reason is fixed, and clearing it would lose the sections.
                # An unconfirmed send stays retryable on purpose — the
                # Idempotency-Key means a second attempt cannot double-message
                # anyone who already got it.
                return _reply(result.get('error_message', 'The send failed.'))
            labels = list(state.get(tools.CHOSEN_SECTIONS) or [])
            # Listed one per line, like the confirmation card. This is the
            # record of what just happened, and the labels differ by a single
            # digit — read as a sentence, a professor cannot check it.
            detail = []
            if labels:
                shown = list(labels[:12])
                if len(labels) > 12:
                    shown.append(f'and {len(labels) - 12} more')
                detail = [a2ui.DIVIDER, 'Sent to:', a2ui.bullets(shown)]
            return _outcome(
                state,
                '✅  Agent sent',
                detail + [a2ui.DIVIDER,
                          'Students in those sections will get the link on '
                          'WhatsApp. This cannot be undone.'],
                'Sent.',
            )

        if name == section_ui.CANCEL_SEND:
            agent_id = context.get('agent_id')
            # Cancelling a send that already happened is not a cancellation.
            if agent_id and tools.confirmation_status(state, agent_id) == 'sent':
                return _outcome(
                    state,
                    '✅  Already sent',
                    [tools.SENT_CANNOT_CANCEL_MESSAGE],
                    'This agent has already been sent.',
                )
            return _outcome(
                state,
                'Not sent',
                ['Nothing was sent. The agent stays published to those '
                 'sections, so you can send it later.'],
                'Nothing was sent.',
            )

        if name in progress_ui.MENU_VIEWS:
            return _view_card(
                callback_context, name, (context.get('department') or '').strip()
            )

        if name == progress_ui.AMBASSADOR_VIEW:
            payload = state.get(tools.VIEW_DATA)
            if payload is None or state.get(tools.VIEW_NAME) != (
                progress_ui.VIEW_AMBASSADORS
            ):
                return _reply(
                    'That list is no longer loaded — ask me for it again and I '
                    'will fetch it fresh.',
                    section_ui.main_menu(state),
                )
            state[progress_ui.AMBASSADOR_FILTER] = context.get('filter')
            return _reply('Here you go.',
                          progress_ui.ambassador_roster(state, payload, 0))

        if name == progress_ui.AGENT_VIEW:
            # Rebuilt from the payload already in state — switching cut is a
            # question about data we hold, not a reason to call Sethu again.
            payload = state.get(tools.VIEW_DATA)
            if payload is None or state.get(tools.VIEW_NAME) != (
                progress_ui.VIEW_AGENT_USAGE
            ):
                return _reply(
                    'That list is no longer loaded — ask me for it again and I '
                    'will fetch it fresh.',
                    section_ui.main_menu(state),
                )
            state[progress_ui.AGENT_FILTER] = context.get('filter')
            return _reply(
                'Here you go.',
                progress_ui.agent_usage(state, payload, 0),
            )

        if name == progress_ui.SHOW_MORE:
            # Paged from the payload already in state. Re-fetching would cost a
            # round-trip against an API that sleeps, and could redraw the card
            # with different numbers halfway down one list.
            view = context.get('view')
            builder = progress_ui.BUILDERS.get(view)
            payload = state.get(tools.VIEW_DATA)
            # Only one payload is held at a time, so a "Show more" on an older
            # card can arrive after a different view replaced it. The builders
            # take different shapes, so a mismatch is refused rather than fed
            # to one — the card outlives its data by the whole conversation.
            if not builder or payload is None or state.get(tools.VIEW_NAME) != view:
                return _reply(
                    'That list is no longer loaded — ask me for it again and I '
                    'will fetch it fresh.',
                    section_ui.main_menu(state),
                )
            try:
                offset = int(context.get('offset') or 0)
            except (TypeError, ValueError):
                offset = 0
            return _reply('Here is the rest.', builder(state, payload, offset))

        if name == section_ui.START_SEND:
            # Offer the agents Sethu already knows about. Pasting a link stays
            # available underneath, for an agent the sync has not reached yet.
            found = tools.list_agent_choices(callback_context)
            if found.get('status') == 'success':
                return _reply(
                    'Pick the agent you want to send.',
                    section_ui.agent_picker_card(state, found['agents']),
                )
            if found.get('status') == 'signed_out':
                # Not an empty list. Offering the paste-a-link card here sent
                # professors hunting for a link that would have failed too.
                return _reply(found['message'], section_ui.main_menu(state))
            return _reply(
                'Paste the agent link, then choose who it goes to.',
                section_ui.send_agent_card(state),
            )

        if name == section_ui.PASTE_INSTEAD:
            return _reply(
                'Paste the agent link, then choose who it goes to.',
                section_ui.send_agent_card(state),
            )

        if name == section_ui.PICK_AGENT:
            picked = context.get('agent')
            if isinstance(picked, list):
                picked = picked[0] if picked else None
            choices = {a['id']: a for a in (state.get(tools.AGENT_CHOICES) or [])}
            chosen = choices.get(str(picked or '').strip())
            if not chosen:
                return _reply(
                    'Pick one of the agents first.',
                    section_ui.agent_picker_card(
                        state, list(state.get(tools.AGENT_CHOICES) or [])),
                )
            # Checked here rather than at publish. Naming the agent and
            # picking sections sit between the two, and finding out the agent
            # was private only after all that is the frustrating order.
            refusal = tools.readiness_refusal(chosen['link'], chosen['name'])
            if refusal:
                # Nothing is committed to state: they will come back through
                # Send Agent once it is shared, and a half-set send left
                # behind would collide with that.
                return _reply(refusal['message'],
                              section_ui.main_menu(state))

            state[tools.PENDING_LINK] = chosen['link']
            state[tools.PICKED_NAME] = chosen['name']
            state[tools.CHOSEN_SECTIONS] = None
            logger.info('agent picker: chose %r', chosen['name'])
            return _reply(f'"{chosen["name"]}" it is.',
                          section_ui.scope_card(state, chosen['name']))

        if name in (
            section_ui.SHOW_SECTIONS,
            section_ui.SCOPE_ALL,
            section_ui.SCOPE_DEPARTMENT,
            section_ui.SCOPE_MANUAL,
        ):
            return _scope_or_sections(callback_context, name, link)

        roster = state.get(tools.ROSTER_CACHE) or []

        if name == section_ui.PICK_DEPARTMENT and roster:
            department = context.get('department')
            if state.get(tools.SEND_SCOPE) == section_ui.SCOPE_DEPARTMENT:
                labels = [
                    s['label']
                    for s in roster
                    if s.get('department') == department and s.get('label')
                ]
                state[tools.CHOSEN_SECTIONS] = labels
                total = sum(
                    s.get('students') or 0
                    for s in roster
                    if s.get('department') == department
                )
                return _sections_chosen(
                    callback_context,
                    f'All of {department} selected — '
                    f'{_plural(len(labels), "section")}, '
                    f'{_plural(total, "student")}.',
                )
            if state.get(tools.SEND_SCOPE) is None:
                # Browsing, not sending. The list is the answer; there is
                # nothing to choose and nothing to record.
                card = section_ui.section_list_card(state, roster, department)
                if card:
                    return _reply(f'Here are the {department} sections.', card)
                return _reply(f'No sections listed for {department}.')

            state[tools.PICKING_DEPARTMENT] = department
            # Sections already held from other departments. The ticks for this
            # one live in the card's own data model until Done is pressed.
            chosen = len(state.get(tools.CHOSEN_SECTIONS) or [])
            card = section_ui.section_card(state, roster, department, chosen)
            if card:
                return _reply(f'{department} — which section?', card)
            return _reply(f'No sections listed for {department}.')

        if action['name'] == section_ui.PICK_SECTION:
            label = context.get('label')
            if not label:
                return None
            chosen = list(state.get(tools.CHOSEN_SECTIONS) or [])
            if label not in chosen:
                chosen.append(label)
            state[tools.CHOSEN_SECTIONS] = chosen

            # Picking stays open. Ending it on the first tap — which is what
            # happened once a link had been pasted — made multi-section sends
            # impossible in the order the Send Agent card asks for.
            department = state.get(tools.PICKING_DEPARTMENT)
            card = (section_ui.section_card(state, roster, department,
                                            len(chosen))
                    if roster and department else None)
            if card:
                return _reply(
                    f'Selected {label} ({len(chosen)} so far).', card
                )
            return _reply(
                f'Selected {label} ({len(chosen)} so far). Pick another, or '
                'press Done.',
                section_ui.department_card(state, roster) if roster else None,
            )
    except Exception:  # A broken card must never cost the professor an answer.
        return None
    return None


def _after_model(callback_context=None, llm_response=None):
    """Scrub A2UI out of the model's prose, then attach the card and the menu.

    Both ride on the model's own response rather than being emitted from
    `after_agent_callback`. Returning Content from after_agent is the documented
    pattern on ADK 2.4.0, but on 2.6.1 the extra event never brings the A2A task
    to a terminal state: the JSON-RPC call hangs and the server wedges for every
    later request too. Appending to the response the runner is already going to
    send avoids inventing an event at all.
    """
    a2ui.strip_a2ui_from_response(
        callback_context=callback_context, llm_response=llm_response
    )
    if llm_response is None or not config.A2UI_ENABLED:
        return None

    try:
        state = callback_context.state
        if getattr(llm_response, 'partial', False):
            return None  # A streaming fragment; wait for the complete reply.

        content = getattr(llm_response, 'content', None)
        parts = list(getattr(content, 'parts', None) or [])
        if not any(getattr(p, 'text', None) for p in parts):
            return None  # A tool call, not the reply to the professor.

        # Text sitting alongside a function call is preamble — the model
        # saying "Hi Abhishek! What can I do for you today?" on its way to
        # calling show_main_menu. It is not the answer, and the answer that
        # follows says the same thing again. Left alone it produced two
        # greetings and two menus in one turn (measured 2026-08-24, 12:40:13
        # and 12:40:14). The call is kept; only the chatter goes.
        calls = [p for p in parts if getattr(p, 'function_call', None)]
        if calls:
            llm_response.content = types.Content(
                role=getattr(content, 'role', 'model') or 'model',
                parts=calls,
            )
            logger.info('dropped preamble text ahead of a tool call')
            return llm_response

        staged = state.get(tools.PENDING_UI)
        roster = state.get(tools.ROSTER_CACHE) or []
        card = None

        if staged in progress_ui.BUILDERS:
            payload = state.get(tools.VIEW_DATA)
            if payload is not None:
                card = progress_ui.BUILDERS[staged](state, payload, 0)
        elif staged == 'menu':
            card = section_ui.main_menu(state)
        elif staged == 'departments' and roster:
            card = section_ui.department_card(state, roster)

        if card is not None:
            state[tools.PENDING_UI] = None

        # The menu goes under every reply, so a professor is never left with
        # prose and no way onward. `_menu_parts` skips it when the card above
        # already is the menu.
        extra = (a2ui.to_genai_parts(card) if card else []) + _menu_parts(
            state, card
        )
        if not extra:
            return None

        llm_response.content = types.Content(
            role=getattr(content, 'role', 'model') or 'model',
            parts=parts + extra,
        )
        logger.info('attached %s card + menu', staged or 'no')
        return llm_response
    except Exception:
        logger.exception('could not attach card; answering with text only')
        return None


def _instruction(context: ReadonlyContext) -> str:
    """The instruction, personalised once Sethu has told us who is asking."""
    name = auth.display_name(context)
    if not name:
        return INSTRUCTION
    return (
        f'{INSTRUCTION}\n'
        f'The professor you are talking to is {name}. Open your first reply of\n'
        f'a conversation by greeting them by their first name — "Hi '
        f'{auth.first_name(name)}" — and refer to them that way naturally\n'
        'afterwards. Do not repeat the greeting on every message.\n'
    )


root_agent = Agent(
    model='gemini-2.5-flash',
    name='root_agent',
    description=(
        'Champion Faculty sends a professor\'s newly created AI agent to '
        'the students of their sections over WhatsApp, via the Sethu API.'
    ),
    instruction=_instruction,
    before_agent_callback=_before_agent,
    # Scrubs A2UI out of the model's prose and attaches any staged card.
    after_model_callback=_after_model,
    tools=(
        [
            find_agent_by_link,
            show_main_menu,
            show_section_picker,
            publish_agent,
            prepare_send,
            send_agent_to_sections,
            show_department_progress,
            show_leaderboard,
            show_ambassadors,
            show_agent_usage,
            diagnose_identity,
        ]
        if config.A2UI_ENABLED
        else [
            # Agent Engine cannot render cards, so it gets the prose tool and
            # never sees the picker. Both tools answer "which sections?", and
            # offering both means the model picks the wrong one.
            find_agent_by_link,
            list_college_sections,
            publish_agent,
            prepare_send,
            send_agent_to_sections,
            diagnose_identity,
        ]
    ),
)
