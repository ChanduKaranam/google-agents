---
name: grilling
description: Interrogate a design, plan, or decision one question at a time until shared understanding is reached. Use for the deep design rounds in /groom-ticket and /work-ticket, the lead's questions in /review-ticket, and any time a decision tree needs to be walked before code is written.
---

# Grilling

Interview the user relentlessly about every aspect of this until you reach a shared understanding. Walk down each branch of the decision tree, resolving dependencies between decisions one by one. For each question, provide your recommended answer.

Ask the questions **one at a time**, waiting for feedback on each before continuing. Asking multiple questions at once is bewildering, and it lets the user skim past the one that mattered.

If a *fact* can be found by exploring the environment — the filesystem, git history, the schema, the existing code — **look it up rather than asking.** The *decisions*, though, are the user's. Put each one to them and wait for the answer.

Do not act on any of it until the user confirms you have reached a shared understanding.

## NEVER

- Never batch questions. One per message.
- Never ask what you could have grepped for.
- Never start writing code, tickets, or plans mid-grill — the exit condition is the user's confirmation, not your own sense that you have enough.
