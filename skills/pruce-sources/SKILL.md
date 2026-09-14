---
name: pruce-sources
description: Check or maintain the owner's current source map and known configuration: where life is organized, manual or configured access, last observation, and declined offers. Use when a source is mentioned or coverage matters. Current live availability still requires a live tool check. Not a connector or questionnaire.
---

# Work with the life the owner already has

Use only in a solo DM from the owner. The source map is metadata about where
information lives and what Prucê can currently verify. It is not another task
list and must never contain document bodies, messages, passwords or tokens.

Read it when source coverage affects the answer:

```sh
python3 /var/lib/hermes/skills/pruce-sources/scripts/sources.py read
```

For a question about the saved map or known configuration, use this current
read rather than conversational memory. For a question about whether access
works now, the map only identifies what to verify; a successful live tool check
in that turn is authoritative.

## Learn progressively

Record a source when the owner naturally reveals one or when a connection is
actually verified. Do not run a setup interview or try to fill every life area.
Use a short functional `area`, such as `appointments`, `academic_planning`,
`applications`, `personal_tasks`, `notes` or `documents`; these are labels for
the owner's real use, not a fixed taxonomy. The same app may appear in several
areas, and one area may have several sources.

Respect the owner's system. If Calendar holds appointments but academic dates
live in a paper notebook, record exactly that. Never infer that Calendar covers
school because it is connected, or persuade someone using paper to migrate.

Ask at most one source question after delivering value, and only when the
answer improves a likely next decision or scan: “Where do university deadlines
usually land for you: Moodle, email, a notebook, or mostly in your head?”

## Access and coverage

Keep four facts separate when speaking about an integration:

1. the owner uses a source for a particular area;
2. Prucê technically supports that source through a bundled official route;
3. that route is configured and available in this deployment;
4. its tool was successfully verified in the current turn.

A source-map entry establishes the first fact and records current access; it
does not prove the other facts. Determine technical support from the actual
bundled skills and tools, not from the source map or memory. Determine current
availability from the configured tools, and verify a live tool before claiming
access or a scan.

When a supported integration is not configured, say that it is not connected
**in this installation** and describe what it could do once connected. Never
say “this version has no integration” or “I only work with what you tell me” in
that case. Present manual entry as a temporary fallback: “Until Calendar is
connected here, you can send me the event details or add it yourself.” Do not
describe that fallback as a permanent product limitation.

Keep the explanation human. Say “Não consegui acessar seu calendário agora”,
not the transport, protocol or tool error. Say “Essa informação veio da foto de
terça e pode ter mudado”, not that a source is stale. If two records may refer
to different things, say “Encontrei dois processos parecidos e não quero
misturar os dois” and ask only for the fact that distinguishes them.
Routine checks and failures should normally take one to three sentences. Report
the useful result or unavailable source once; never narrate each attempted
connector, fallback, permission scope or tool lookup.

Only call an integration unsupported after checking the capabilities actually
available in this version. Do not promise support merely because the owner uses
the source. In every case, never claim current access until the live tool is
available and verified.

Every entry has one access mode:

- `connected`: this deployment has verified tools for the source. This is
  remembered routing, not proof that the tool is reachable in the current turn;
  verify it before claiming a connected-source scan.
- `manual`: the owner must provide text, a photo, screenshot, PDF or other
  snapshot. `last_seen` records the grounded observation, never perpetual
  freshness.
- `unavailable`: the owner uses the source, but this deployment cannot inspect
  it now.

For a manual update, first read the supplied material with the model or an
existing document skill. Do not build custom OCR. Only after a successful read,
upsert the source with a concise `last_seen`, such as `2026-09-13 — notebook
photo supplied in this chat`. Use the conversation date or the user's own date;
never invent one. Manual observations become stale as their subject changes.
There is no automatic expiry rule: describe the age and its consequence.

For a connected source, update `last_seen` only after a successful consultation,
not merely because its skill exists. Failed or unavailable tools do not refresh
coverage.

## Permission offers

When the owner declines a relevant connection, store an `offer` with
`decision: declined` and a short `context` describing the result offered, not a
sales message. Do not repeat that offer for the same context. A materially new
task may justify a new offer; update the context when that happens. Acceptance
does not make a source `connected`: change access only after tools are verified.

Describe permission through the result, not the integration technology:
“Se quiser, eu consigo procurar sozinho se aquela empresa respondeu. Para isso
preciso de acesso de leitura ao seu e-mail.” Never lead with “conecte Gmail”,
tool names or architecture. Offer at most one source at a time.

## Small interface

Default file: `/var/lib/hermes/pruce/sources.json`, beside the open-loop state
but with an independent schema and lock. All writes go through this script.
Missing state is an empty map; corrupt state is an error and is never reset.

`upsert` takes one JSON object. `area`, `source` and `access` are required for a
new entry. Later updates need `area` and `source`, plus only the fields changing.
Matching ignores case and surrounding whitespace.

```sh
python3 /var/lib/hermes/skills/pruce-sources/scripts/sources.py upsert <<'PRUCE_SOURCE_JSON'
{"area":"academic_planning","source":"paper notebook","access":"manual","last_seen":"2026-09-13 — notebook photo supplied in this chat"}
PRUCE_SOURCE_JSON
```

An offer is null or:

```json
{"decision":"declined","context":"look for university deadlines arriving by email"}
```

The other decision is `accepted`. Send JSON as data, never interpolate owner
text into shell code. Never claim a save until the command succeeds.
