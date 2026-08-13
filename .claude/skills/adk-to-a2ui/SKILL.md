---
name: adk-to-a2ui
description: Use when adding interactive cards, buttons, or chips (A2UI) to a Google ADK agent in Gemini Enterprise, when converting an agent registered via adkAgentDefinition or deployed on Agent Engine / Agent Runtime so it can draw UI, or when a card renders blank, renders as raw JSON, shows a red "This content could not be displayed" box, drops its buttons, or paints once and never again.
---

# Turning an ADK agent into an A2UI agent

## Overview

A2UI is agent-drawn UI in the Gemini Enterprise chat surface: cards, buttons,
text fields. This skill converts an existing ADK agent — plain or already A2A —
into one that draws it.

**Core principle: the code composes the UI, never the model.** A widget built
from session state cannot show a number a tool did not return. A widget the
model composes can invent one, and will.

Everything here is extracted from an agent painting in production
(`ambassador_agent/` in this repo). The guards exist because each failure
happened. **A2UI failures are silent** — no server-side log, at most a red box
in the chat — so a design that "looks right" and a design that works are
indistinguishable until you deploy.

**REQUIRED BACKGROUND:** `gemini-enterprise-agents` covers the platform, the
wire format, and the naming. This skill is the conversion procedure. Read that
one for anything about GE itself.

## Step 0: Decide whether this is a UI task or a migration

Check how the agent is registered in GE:

```bash
curl -s -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "X-Goog-User-Project: $PROJECT" \
  ".../engines/$ENGINE/assistants/default_assistant/agents" \
  | grep -E 'displayName|AgentDefinition'
```

| Registration | What this is |
|---|---|
| `a2aAgentDefinition` | A UI task. Go to Step 1. |
| `adkAgentDefinition` (Agent Engine / Agent Runtime) | **A runtime migration.** A2UI will never render for this registration whatever the agent emits. The agent must move to a self-hosted A2A endpoint first — read `references/serving.md` before writing any UI code. |
| `lowCodeAgentDefinition` (Agent Designer) | Not supported. Rebuild in ADK. |

Say this out loud to whoever asked. "Add some buttons" and "move off the
managed runtime, keeping sessions, memory and identity intact" are different
sized jobs, and the second one is what was actually requested.

## Step 1: Copy `a2ui.py`

Copy `a2ui.py` from this skill directory into the agent package unchanged.
Do not rewrite the builders from the spec — the component tree is the part
models fabricate, and the guards in that file are load-bearing.

It gives you: `build_card`, `uid`, `to_genai_parts`, `parse_user_action`,
`incoming_text`, `strip_a2ui_from_response`, and the primitives.

## Step 2: Wire the three callbacks

```python
root_agent = Agent(
    ...,
    before_agent_callback=handle_click,             # clicks, deterministic
    after_model_callback=strip_a2ui_from_response,  # scrub JSON from prose
    after_agent_callback=render_surface,            # normal turns
)
```

**The rule that decides the whole design:**

> Whichever callback short-circuits the turn must emit the A2UI parts *itself*.

`before_agent_callback` returning `Content` sets `ctx.end_invocation = True`
(`base_agent.py:505`), and the runner then returns at `:301-302` — **the model
never runs and `after_agent_callback` never runs.** The intuitive design
(before_agent writes state → after_agent draws the card) produces text and no
card on every button press: the card appears for typed questions and vanishes
for taps, which is the one interaction A2UI exists for.

So `handle_click` returns text parts *and* `to_genai_parts(...)` together, and
`render_surface` opens by returning `None` for any turn `handle_click` already
answered.

`after_agent_callback` returning `Content` **adds** an event beside the model's
reply (`:557-565`); it does not replace it.

**Guard both callbacks with `try/except` returning `None`.** A broken widget
must never cost the user their text answer.

## Step 3: A fresh surfaceId per render

```python
messages = build_card(uid(callback_context.state, "attendance"), lines, buttons)
```

A repeated `surfaceId` is an **update** to the earlier surface. Reusing one
rewrites the card further up the transcript and leaves the new turn **blank**.
Hardcoding `surfaceId: "attendance"` is the most common A2UI bug — both
independent baseline attempts made it, and it took three live reports to spot.

## Step 4: Feed it structured state, not prose

The renderer reads `state.get("attendance_data")`, written by the tool:

```python
def get_attendance(section: str, tool_context: ToolContext = None) -> dict:
    result = {"section": section, **SECTIONS[section]}
    if tool_context is not None:
        tool_context.state["attendance_data"] = result
    return result
```

Do **not** add an `output_schema` agent to restructure data a tool already
returns structured. `output_schema` cannot coexist with tool calling, so it
forces a two-agent split for nothing, and puts a model back in the path the
whole design exists to keep it out of.

Read state with `.get()`. `dict(state)` raises `KeyError: 0`.

## Quick reference

| Need | Do |
|---|---|
| Card with buttons | `build_card(uid(state, "x"), lines, [(label, action, ctx)])` |
| Collect typed input | `text_field(...)` + `button_with_values(..., {"k": {"path": "/k"}})` — TextField alone cannot notify the agent |
| Read a click | `parse_user_action(incoming_text(callback_context))` |
| A link | Render the URL as text. No link primitive in v0.8; `openUrl` is v0.9 and GE activates v0.8 only |
| Emit | `types.Content(role="model", parts=to_genai_parts(messages))` |
| Debug a red box | The fragment in the box names the offending component id. Nothing is logged server-side |

Keep a surface under ~6KB. GE drops an oversized one silently — text arrives,
card does not. Measured: 5.6KB rendered, 12.7KB did not.

## Common mistakes

Every row was produced by a real attempt at this conversion, not imagined.

| Mistake | Consequence |
|---|---|
| `before_agent` writes state, `after_agent` draws | No card on any button press. `end_invocation` skipped it |
| Fixed `surfaceId` across turns | Second card silently blanks the new turn |
| Keeping `to_a2a()`'s default runner on Cloud Run | In-memory sessions + no Memory Bank. State vanishes between turns; nothing raises |
| `google-adk[a2a]` alone in requirements | No `sse-starlette`; container dies at *startup*, not import, while every test passes |
| Unpinned `a2a-sdk` | Resolves to 1.1.2, a different package layout |
| Registering the repo's `agent_card.json` | GE calls `localhost`; the agent looks alive and does nothing |
| Forgetting `GOOGLE_GENAI_USE_VERTEXAI=1` | Boots green, fails the first model call |
| No `run.invoker` for the GE service agent | Every turn 403s |
| Skipping `after_model_callback` | Model copies A2UI JSON out of history into its reply |
| `application/a2ui+json` | v0.9 spelling. GE is v0.8-only; nothing renders |
| Bare `root`/`body` ids | Validator rejects the card. `surface()` raises on these |

## Verification — nothing here is provable offline

Structural tests catch id collisions and reserved names. They cannot catch a
card GE refuses. Before claiming it works, in the GE chat:

1. A typed question draws the card.
2. **Tap a button** — the card must redraw, not just text.
3. Ask the same question twice — the second card must appear (Step 3).
4. Type into a field, submit, confirm the value arrived.
5. New conversation, ask about something from the last one — sessions and
   memory survived the move.

If a turn comes back blank, read the session events before assuming the agent
broke: an empty final text, a crash, and a 429 are indistinguishable in the UI.

## Red flags

- "I'll just have the model output the card JSON" — it will invent data
- "The card renders, so it works" — you have not tapped a button yet
- "In-memory sessions are fine, this agent is stateless" — Cloud Run recycles
  instances mid-conversation
- About to write a component tree from memory instead of using `a2ui.py`
- Claiming it works without having opened Gemini Enterprise
