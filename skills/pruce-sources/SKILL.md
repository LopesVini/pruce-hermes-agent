---
name: pruce-sources
description: Learn and maintain the owner's small source and coverage map: where each part of life is organized, whether Prucê can consult it directly or only through manual updates, when it was last observed, and whether a contextual access offer was declined. Use when a source is mentioned, shared, connected, unavailable, or relevant to a Life Scan. Not a connector and not a profile questionnaire.
---

# Work with the life the owner already has

Use only in a solo DM from the owner. The source map is metadata about where
information lives and what Prucê can currently verify. It is not another task
list and must never contain document bodies, messages, passwords or tokens.

Read it when source coverage affects the answer:

```sh
python3 /var/lib/hermes/skills/pruce-sources/scripts/sources.py read
```

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
