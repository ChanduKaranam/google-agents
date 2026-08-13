# Faculty agents are created PRIVATE — nobody but the creator can open them

> To the Sethu build team, 2026-08-13.
> Companion to `SETHU-expose-ge-agent-id.md`.

## The problem

A student opened an agent sent over WhatsApp and got:

> I'm sorry, it seems you are not allowed to perform this operation. Please
> contact an administrator.

and on mobile:

> This conversation is read-only as the agent used is no longer available.

The link was correct — Gemini Enterprise resolved it, found the agent, and
rendered its page with the agent's name in the input box. What failed was
authorisation.

## Why

An agent created through the Gemini Enterprise console starts life as
`state: PRIVATE` with no `sharingConfig` — "available only to its creator".
Read from the Discovery Engine API on 2026-08-13, across the whole
`ai-ge_1784736359549` app:

```
4241865874029125431    PRIVATE    (unset)      Hackashop
17211992847197382667   PRIVATE    (unset)      Sync Test 13 Aug
5647010738096103633    PRIVATE    (unset)      Document Q&A Agent
2081597015756588548    PRIVATE    (unset)      Document Q&A Agent
17610637812585580016   PRIVATE    (unset)      Doubt solver
18182004238900364675   PRIVATE    (unset)      Transcript Summarizer
2108515276467869400    PRIVATE    (unset)      Gemini Enterprise Tutor
…5 more "My Agent"
------------------------------------------------------------------
5115760108249648706    ENABLED    ALL_USERS    Champion Faculty
15654412355158356535   ENABLED    ALL_USERS    Campus Ambassador
7596282539834158705    ENABLED    ALL_USERS    Job Helper Agent
13670083828638936939   ENABLED    ALL_USERS    Resume Maker (A2UI)
```

**13 of 26 agents are PRIVATE, and every one of them is a no-code agent built
in the console.** Every agent that is `ENABLED` + `ALL_USERS` was configured by
a developer who knew the setting existed.

This is not an edge case. It is the default outcome for every agent a professor
creates, so a send to a real class fails for all of them today. Faculty have no
reason to know Discovery Engine has a sharing scope, and no reason to go
looking for it.

## The fix, and whether you can do it

**Yes — it is one PATCH, on a resource your sync already reads.**

```
PATCH .../assistants/default_assistant/agents/{geAgentId}?updateMask=state,sharingConfig

{ "state": "ENABLED", "sharingConfig": { "scope": "ALL_USERS" } }
```

Both fields are writable on the `Agent` resource. There is no dedicated share
method — `create`, `get`, `list`, `patch`, `delete` are the only methods on
`agents`, so `patch` is the intended route. Enum values are from the published
discovery document: `state` accepts `ENABLED`, and
`sharingConfig.scope` accepts `ALL_USERS` (an unset scope behaves as
`RESTRICTED`, so clearing it is not enough).

**Can you do it from your side?** We believe so, and better than we can:

- `sethu-ge-sync@supadha-dev.iam.gserviceaccount.com` already enumerates every
  agent under the engine, so the credential and the resource path exist. It
  would need `discoveryengine.editor` (or a role carrying
  `discoveryengine.agents.update`) rather than read-only access.
- You already store `geAgentId`, so no extra lookup is needed.
- You own the claim lifecycle, which is the correct trigger.

**Where:** in `PATCH /faculty/agents/:id/claim`. Claiming an agent and giving it
sections is the moment a professor declares it student-facing; making it
student-accessible belongs in the same transaction.

Three properties that make this a fix rather than a script:

1. **Idempotent** — skip agents already `ENABLED`/`ALL_USERS`, so re-claims and
   retries cost nothing.
2. **Audited** — record who triggered the sharing change and when. It is a
   permission change made on a person's behalf and should be attributable.
3. **Fails loudly** — if the PATCH fails, fail the claim. Publishing an agent
   that cannot be opened is worse than refusing, because the failure surfaces
   later and to students rather than now and to the professor.

Plus a **one-time backfill** for the 13 agents already `PRIVATE`.

## Why not from the agent side

We could PATCH it ourselves, and we are choosing not to.

Champion Faculty runs as the *professor* — Gemini Enterprise forwards their
OAuth token, and that token has no Discovery Engine permission whatsoever. The
only way for us to do it is to act as our Cloud Run service account, which
holds `roles/editor`. That would mean a chat surface silently exercising a
privilege the signed-in user does not have, on a resource they own but cannot
themselves modify. It would work, and it would be the wrong place for it.

Doing it once in your claim handler also covers every client — this agent, the
Agent Engine registration, and anything built later — rather than each one
solving it separately and drifting.

## What we will do on our side

Refuse to send a link that cannot work. Before the WhatsApp send, check the
agent's `state` and `sharingConfig`; if it is not shareable, stop and tell the
professor why rather than messaging a class a link that returns "you are not
allowed to perform this operation". That needs Discovery Engine **read** access
from our service account, which we have.

This guard is worth having even after the claim-time fix lands: it fails closed
on the one action in this system that cannot be undone.

## The policy question underneath — worth deciding, not defaulting

`ALL_USERS` means every user in the organisation, not every student in the
chosen sections. Gemini Enterprise has no per-section access concept: the `/go`
link and the WhatsApp message are the targeting mechanism, and GE access is
all-or-nothing.

So: **is it acceptable that an agent sent to one section becomes openable by
every Gemini Enterprise user in the org?** If yes, the fix above is complete. If
no, then no amount of automation helps and the sharing model itself needs
rethinking before this ships to real classes.

## Still unverified

Whether students have Gemini Enterprise access at all. The failure above was
reproduced by a colleague with a Plus account who already had the agent in
their sidebar. If a genuine student needs a GE licence or org membership to open
an agent, sharing scope is not the whole problem, and that changes who this
feature can serve. Worth testing with a real student account before either side
builds anything.
