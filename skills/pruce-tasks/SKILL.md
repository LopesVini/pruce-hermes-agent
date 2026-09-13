---
name: pruce-tasks
description: Capture, resume and advance a student's or young adult's unfinished responsibility in the owner's solo DM. Use for study, applications, paperwork and everyday open loops, and when checking known context. One workflow across domains, with persistent internal state.
---

# One open loop, one useful next step

Use only in a solo DM from the owner. Read context and active open loops before
listing, summarizing or resuming current responsibilities:

```sh
python3 /var/lib/hermes/skills/pruce-tasks/scripts/state.py active
```

1. Read the request and saved state. Match an existing task by meaning, not
   only wording. Resume it by ID. If two tasks could match and the distinction
   changes the work, ask one short question. Do not create a task for every
   greeting, general question, or hypothetical example.
2. Identify the outcome or ongoing subject occupying the user's attention.
   `title` names that open loop, not just today's action: "Candidatura à vaga
   de estágio" rather than "Mandar currículo". `next_step` names the concrete
   action or external response currently needed to advance it. Save promptly,
   even if details are missing; unknown
   deadlines stay null. Do not split one responsibility into a project tree.
   When one message contains several independent outcomes, save each as its own
   small open loop, then use `pruce-triage` to choose where to begin.
3. Use known context first. Ask only for the information needed for the next
   useful step. Relative time must be anchored once and never reinterpreted
   from a later conversation. Preserve the user's wording in `due`, but use
   `temporal.value` for reasoning. Preserve vague granularity: a date is not an
   end-of-day timestamp, “à noite” is a day part without an invented hour, and
   “essa semana” is a date range. If “sábado” is said on Saturday without enough
   context, ask “Você quer dizer hoje ou sábado que vem?” for an important
   deadline, or keep it unresolved until it matters.
4. Do the authorized next step using currently available tools: prepare a study
   plan, improve supplied CV text, draft a request, organize supplied paperwork.
   If an account is inaccessible, say so and prepare what can be prepared.
   Never claim to have read an inbox, submitted a form or cancelled something
   without a successful result from that service.
5. Save what changed and the next step. Translate the result into conversational
   language: "Deixei o pedido pronto. Falta você conferir o histórico e enviar."
   Do not show a board, IDs, status codes or administrative receipts unless asked.
   Do not bring up unrelated stored responsibilities in every conversation.

## Internal states

| status | When to use |
| --- | --- |
| needs_action | Captured; the next action has not started. |
| in_progress | Concrete work has started. Does not imply a background worker. |
| waiting_for_user | The next step needs the user's information, decision, authorization or action. Say exactly what in next_step. |
| waiting_for_third_party | An external request was actually made; next_step identifies whose response is awaited. Preparation alone does not qualify. |
| completed | The final outcome is confirmed, or the user explicitly chooses to stop tracking this subject. Evidence must support that closure, not merely a finished step. |

Finishing a next_step does not necessarily close the open loop. After an action,
check what remains before choosing status. If the user awaits a company,
professor, university, support team, shop or public agency, use
`waiting_for_third_party`, never `completed`. This applies equally to
applications, credit transfers, refunds, cancellations, support, documents,
registrations and other administrative processes. Do not invent ongoing work
beyond what the user wants tracked.

Example: "Já mandei o currículo para a empresa. Agora estou esperando eles
responderem" updates the SAME record to:

```json
{"id":"<saved id>","title":"Candidatura à vaga de estágio","status":"waiting_for_third_party","next_step":"Aguardar resposta da empresa","evidence":{"kind":"user_confirmation","detail":"Usuário confirmou que enviou o currículo e aguarda resposta da empresa."}}
```

Sending the CV is evidence of submission, not of the application's closure.
Only close when its final outcome is confirmed or the user explicitly says
they no longer want it tracked (record that choice, not a claim of success).
On closure set `next_step` to exactly `Nenhuma ação pendente.`. This internal
convention prevents a completed record from retaining an external wait; the
writer rejects other next_step text for completed records. Never replace an
actual wait with that phrase just to pass validation: save waiting status.
For existing records, status is authoritative: `completed` always means closed,
even if legacy next_step text says "aguardando". Never present it as a current
pending responsibility or reopen it based on that text. `active` excludes every
completed record and is the source for current open-loop lists and summaries.
Use `read` only when historical records are needed, such as an explicit request
to review or reopen a closed subject; closed records remain history until the
user requests reopening. Both reads preserve the stored state unchanged.

An exam-preparation task stays open after drafting a plan. An application
stays open after sending the CV if a response is awaited. If the request was only to write a draft,
producing and verifying that draft can complete that narrower task. Never
silently shrink the agreed outcome to make it look completed. If the user asks
to reopen a closed subject, update the same ID and explain the correction.

## Small state interface

Default file: `/var/lib/hermes/pruce/state.json`, in the persistent home volume.
All writes go through this script. Never overwrite the state directly. A failed
read/write leaves work unrecorded; explain that briefly and do not claim a save.
Do not reset corrupt state or fabricate missing records.

Commands `profile`, `create`, `update` take one JSON object from stdin. Send
JSON as data, never interpolate user text into shell code. If using a quoted
heredoc, choose a delimiter absent as a complete line from its body; never use
an unquoted heredoc, shell substitutions or `echo` with user text.

```sh
python3 /var/lib/hermes/skills/pruce-tasks/scripts/state.py create <<'PRUCE_JSON'
{"title":"Aproveitamento de matéria","next_step":"Identificar a disciplina e o procedimento informado pela universidade"}
PRUCE_JSON
```

- `profile`: `{"introduced":true,"context":"Estuda engenharia."}`. Both keys
  optional; context replaces the previous string, so preserve known facts.
- `create`: required `title`, `next_step`; optional `status`, `due`, `temporal`. Returns
  the saved task including its ID. Reuse that ID for subsequent changes.
- `update`: required `id`, plus any of `title`, `next_step`, `status`, `due`,
  `temporal`, `evidence`. Unspecified fields stay unchanged. For example:
  `{"id":"<saved id>","status":"waiting_for_user","next_step":"Receber os tópicos da prova para montar o plano"}`.
- `due`: null or the original short deadline wording. A new relative `due`
  requires an anchored `temporal` object; the writer rejects relative wording
  on its own.
- `evidence`: null or `{"kind":"user_confirmation","detail":"Usuário confirmou nesta conversa que enviou o CV."}`;
  the other allowed kind is `tool_result`, with an actual receipt/result reference.
  Required for completed and waiting_for_third_party. It must support that
  particular transition. Never invent it just to satisfy validation.

The script validates structure, not truth. You must verify the evidence against
the conversation or tool result. Do not store entire emails, documents, secrets
or speculative profile facts here. Context, next steps and short evidence are
enough. Deadlines are stored only; this version schedules no notifications.

## Temporal grounding

Normalize a deadline before saving it:

```sh
python3 /var/lib/hermes/skills/pruce-tasks/scripts/state.py normalize-time <<'PRUCE_JSON'
{"raw":"amanhã à noite","capture_basis":"live_runtime_clock_at_capture","timezone":"America/Sao_Paulo","source":"user"}
PRUCE_JSON
```

For a message known to be arriving live, invoke normalization for that fact with
`capture_basis: live_runtime_clock_at_capture` and omit `captured_at`. The script
reads its own clock during that invocation; never pass a previous clock result
or infer one from conversation order. Use `original_message_timestamp` with a
supplied `captured_at` only when the current event or another trusted structure
actually exposes that original timestamp. A normal Plow message in this pinned
stack may not expose it to Hermes.

If delayed or backfilled delivery could change the date and the original
timestamp is unavailable, keep `captured_at` null, `capture_basis: unknown`, and
the temporal value unresolved; do not anchor it to processing time as if that
were the sending time. The legacy names `message_timestamp` and `runtime_clock`
remain readable, but their provenance cannot be verified under the old
interface: `active` and `time-status` treat them as unresolved until reconciled.
Use an explicitly known owner/installation IANA timezone or a timezone returned
by a live authorized device tool. Never infer the owner's timezone from the
container clock, locale, phone number or language. If the timezone is unknown,
normalization returns `kind: unresolved` with `reason: timezone_unknown`.

The returned optional object contains `raw`, `captured_at`, `capture_basis`,
`timezone`, `kind`, `value`, `reason`, `source`, and short `evidence`. Kinds are
`datetime`, `date`, `day_part`, `date_range`, and `unresolved`. Pass it as
`temporal` to `create` or `update`; the writer copies its raw wording to `due`.
Open loops without deadlines keep both fields null and work as before.

For a decision that depends on today, tomorrow, lateness or time remaining,
read the current reliable clock and call `time-status` with the saved temporal
object and an offset-aware `now`. Render from the normalized value and current
relation: “amanhã, 14/09”, “hoje, 14/09”, “o prazo era ontem, 14/09”, or simply
“14/09”. Never render the historical `raw` as a new relative fact.

The `active` view exposes legacy relative `due` text without metadata as
`unresolved` with `reason: legacy_relative_without_capture`; it does not rewrite
the file. Reconcile only when that deadline becomes relevant. Do not normalize
it using today's clock. Ask whether the loop is still pending and what the
actual date was. Never say when a legacy phrase was “said” or “saved” unless a
timestamp explicitly persisted with that fact or a trusted historical message
can be linked to it. Conversation ordering, remembered dates, file modification
time and model inference are not temporal provenance. If a real historical
message timestamp is found, normalize from it with
`original_message_timestamp` and update the same task.

When a connected source reports a changed deadline for the same open loop,
compare source, recency and meaning. Do not silently replace a resolved value.
The writer requires short reconciliation evidence for a different resolved
value. If the newer source clearly announces an extension, update the same ID
with `tool_result` evidence. If there is a real conflict, explain both dates and
ask which to use or offer to verify the authoritative source before writing.

Future follow-up conditions must reference normalized absolute temporal values
and stable conditions such as “no response by [datetime]”, rather than storing
fresh relative prose. This release only stores deadlines; it does not run cron,
send reminders or monitor conditions.
