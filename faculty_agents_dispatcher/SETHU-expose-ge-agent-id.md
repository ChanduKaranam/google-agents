# Faculty agents — one API change unblocks the picker, plus one product call

> Message to the Sethu build team, 2026-08-12.
> Replies to `faculty-agents-sync-questions.md`.

Thanks for the write-up — that answered all three questions and corrected two
things we had wrong on our side. Noting those first so we don't keep building
on them:

- We'd framed the usage-stats gap as "app-level vs section-published agents".
  Wrong distinction — it's `geAgentId != null`, and hand-pasted rows can never
  match because they have no resource id.
- We'd been treating "section-published" as a GE category. Understood now that
  `sections` is Sethu-only and assigned at claim time. We'll stop describing it
  that way.

**The main takeaway for us was your line about the sync being the source of
truth — faculty claiming a synced row rather than pasting a new one.** That
reframes what we're building. Pasting is what creates the duplicate rows we've
been seeing (*Champion Faculty (A2UI)* appears twice; two rows point at the
same GE agent), and a claimed row would carry `geAgentId`, so usage stats would
follow automatically. We'd like to move to that flow.

## What we need to do it — one change

Expose **`geAgentId`** and **`createdByEmail`** in `FacultyAgentResponse`.

Even better, if it's cheap on your side: **compose and store `geUrl` during
sync** from `geAgentId` + the engine path. We've confirmed the format from live
records —

```
https://vertexaisearch.cloud.google.com/home/cid/{clientId}/r/agent/{agentId}/session/-
```

— where the client id is constant per GE app and the agent id is the last
segment of the resource path. If the sync stores that, `unclaimed` comes to
mean only "faculty hasn't chosen sections yet", and nobody pastes a URL at all.
We can compose it client-side from `geAgentId` if you'd rather not, but storing
it once server-side keeps a single definition of the link.

## The product call from your section 3(a)

Please add the filter so app-level and dispatcher agents aren't offered as
claimable faculty agents. Right now *Champion Faculty*, *Champion Faculty
(A2UI)* and *Document Q&A Agent* are the three synced rows a professor sees,
and they'd be the first things in any agent picker — our own infrastructure
presented as their teaching agents.

## Security note on what to expose — and on what already is

Two of these fields carry different risk, so we would rather ask for the
narrower version of each than have you expose the raw ones.

**`geAgentId` — prefer the composed `geUrl` instead.** The resource path
carries your GCP project number and engine id, which would then be readable by
every faculty client. Knowing a path grants no access — IAM decides that — but
it is infrastructure detail reaching end users for no gain. A composed `geUrl`
carries only the per-app client id and is already meant to reach students, so
it discloses strictly less while giving us the same capability.

**`createdByEmail` — please send a boolean, not the address.** It is personal
data, and `GET /faculty/agents` currently returns tenant-wide rows: our last
reading was 14 agents, not all created by the caller. Exposing the field would
let any professor read every colleague's email address off the API. We only
need it to show a professor their own agents, so **`createdByYou: true|false`**
computed server-side does the job and discloses nothing. Filtering the list to
the caller's own agents would suit us equally well and need no new field.

**`shareToken` is already in the response, and we think that is worth a look.**
It is returned on every row today. If it is the bearer value behind the `/go`
link, then any faculty caller can read the share token of every agent in the
tenant — including agents they did not create — which would let them
distribute, or pre-empt, another professor's link. We are not using the field
and would be glad to see it removed from the response, or restricted to the
agent's owner. Flagging it because it is a live exposure rather than a
proposed one, and it was easy to miss while looking at the fields we asked
about.

## Two smaller questions

1. Does `PATCH /faculty/agents/:id/claim` still require a `geUrl` in the body,
   or would it work with sections alone once the row has a link from sync? That
   decides whether the claim flow can be link-free end to end.
2. Is `createdByEmail` reliable enough to filter a professor's own agents by?
   Our tenant currently resolves the test account as admin/non-roster, so we
   cannot tell from here.

## Nothing is blocked for users meanwhile

The current paste-a-link flow works and is deployed. We're holding off on the
picker until `geAgentId` or a composed `geUrl` is in the response — a picker
over rows with no link would list agents it can't send.

No urgency from our side; mainly we'd like a rough sense of timing so we know
whether to keep the paste flow as the primary path or as a fallback.

---

## Context: what we measured

Readings from the live dev tenant, logged by the agent on each **My Agents**
tap.

```
2026-08-12 05:53
geUrl coverage: 11 of 14 agents carry a link, 3 unclaimed
unclaimed: 3 of 14 agents; 0 carry a link

unclaimed record: id=5e787d5c8de34de7a835c52fc111c1a3
                  name='Champion Faculty (A2UI)' link=(none) sections=[]
                  status=needs-attention
                  keys=['attention','geUrl','id','name','publishedAt','sections',
                        'semester','shareToken','stats','statsSyncedAt','status',
                        'studentCount','subject','unclaimed']
```

The three rows without a link are exactly the three the sync created; every row
with a link has one because a professor pasted it. Neither `geAgentId` nor
`createdByEmail` appears in the response.

Link format confirmed from three live `geUrl` values on 2026-08-11 — the client
id `e3dbb82d-1ec1-4ba6-a6a3-c58782d1eeb2` was identical across all of them, and
the varying segment was the GE agent id.
