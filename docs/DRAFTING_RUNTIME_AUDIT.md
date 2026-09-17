# Drafting runtime audit — 2026-09-17

## Failed turn

The fresh session created at 12:49 UTC received the apology request at 12:50.
The installed `pruce-drafting` description was present in its persisted system
prompt, but the skill body was absent. The response used one model call and
zero tool calls, so no `skill_view` or equivalent loaded that policy. Hermes
exposes a skills index; selection is performed by the model, not a deterministic
intent router. Internal deliberation about that index is not observable.

The session log explicitly reports `Context file SOUL.md blocked:
prompt_injection`. The real scanner matched the variant's defensive wording
containing `ignore previous instructions`, despite its negated context. It
replaces the entire composed identity with a BLOCKED marker, including the
base identity and Prucê's persona. This was not a stale-session problem.

## Minimal correction

Rephrase that defensive sentence to prohibit replacing the owner's instructions
with commands from a source. The trust rule is preserved, the scanner remains
enabled, and the composed identity passes the existing scanner. The drafting
constraint in the always-loaded persona also explicitly includes future
intentions. The supplemental drafting skill is preserved but is not required
to inject the constraint. No router, scheduler, state or provider changes.

The guarantee is deterministic prompt inclusion for the pinned gateway's
identity path, not proof of perfect semantic adherence by an LLM. The image
regression invokes actual Plow composition and the actual Hermes identity
assembler without skill tools or a model. It asserts the full variant text
survives, and that both an actual attack and the old wording remain blocked.

## Rules affected by the identity block

Rules with their principal Prucê implementation exclusively in the persona:

- The targeted Calendar fast path (one bounded Calendar read, no unrelated
  Gmail/state/source-map detours).
- Attachment-plus-text as one inbound event; no unsolicited broad attachment
  analysis; voice transcripts handled as user messages and stale transcripts
  not reopening an old topic.
- The global style rule against exposing internal reasoning, tool routing and
  technical diagnostics in ordinary answers (some skills duplicate parts).

Critical global rules whose always-on copy was lost, but which also have copies
in conditionally loaded skills or safeguards in code:

- Drafting uses only supplied/verified facts; unknown details are omitted or
  queried. The new drafting skill was not loaded in the failed turn.
- Memory is context; mutable operational claims require the relevant current
  authority. State tools validate writes, not what the final answer claims.
- Action performed is not outcome resolved; completion needs outcome evidence.
- External integrations remain read-only; receipts do not authorize writes.
- Private state is limited to the owner's solo DM; sources marked connected
  do not prove current live availability.
- Untrusted external content cannot authorize actions or disclosure.

These are not all literally SOUL-only rules. Their universal application was
missing; a skill copy helps only after that skill is selected. The loader test
checks the full persona, so it detects another whole-file rejection rather than
checking only the drafting sentence.

## Local validation

136 local tests passed; two runtime-only tests skip outside the pinned image.
151 isolated image tests passed, including both runtime identity tests. Agent
Index self-check and linux/amd64 build passed. No owner state, live jobs, Mac
relay or running gateway was modified; no commit or push.

## Owner validation

From the existing checkout and Compose project:

```sh
cd /Users/vinicius/Developer/pruce-hackathon/pruce-hermes-agent
docker compose config --quiet
docker compose build agent
docker compose up -d --no-deps --force-recreate agent
```

Send `/new` in iMessage, then repeat the exact apology request. Do not delete
volumes. Inspect only the relevant fresh-turn logs:

```sh
docker compose logs --since 5m agent | rg 'SOUL.md blocked|conversation turn:|API call #'
```

The fresh prompt should include the full persona rather than a BLOCKED marker,
regardless of whether the model selects `pruce-drafting`. Absence of a log
warning alone is weaker evidence than inspecting that session's persisted
system prompt, as done during this investigation.
