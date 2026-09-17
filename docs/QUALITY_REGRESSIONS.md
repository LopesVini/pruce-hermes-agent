# Surgical quality corrections — 2026-09-16

Scope: existing drafting, time, classification and follow-through behavior.
No deployment, branding, integrations or scheduler implementation changes.

## Evidence and fixes

- Owner drafts lacked an explicit factuality constraint. Persona now prohibits
  invented excuses, events and promises when representing the owner, while
  allowing neutral wording and questions only for necessary missing details.
- The R$150 record was captured on 16 September at 20:04 in America/Sao_Paulo.
  The later same-day answer called it yesterday without a fresh state/clock
  check. This is a generation/authority failure, not demonstrated timestamp
  conversion corruption. Task guidance separates capture time from the actual
  request date and response-window start; unnecessary relative labels are omitted.
- A concrete parser defect also existed: “em 5 dias úteis” matched ordinary
  calendar days. Business-day phrases now remain unresolved with a specific
  reason. No holidays or counting convention are assumed. “até N dias” is
  recognized as relative wording and cannot be newly written without metadata.
  This does not migrate or rewrite existing records.
- The future assessment was not saved as a third-party wait. The What Now
  answer grouped it with refunds without reading canonical state. Task and
  triage contracts now classify each obligation by its own next actor, preserve
  actionable preparation despite missing details, and distinguish blocked user
  input from an evidenced external wait. No assessment keyword classifier added.
- The recorded R$150 turn explicitly requested a message that day at 20:04.
  Cron was created at 20:05:22 with a 20:04 schedule already past. It was not
  automatically derived from the five-business-day window. The R$160 follow-up
  also offered to reuse that reminder time. Guidance now rejects arbitrary
  process reminders, cross-record reminder reuse and past-time scheduling claims.
  The upstream scheduler is unchanged; no live jobs were changed or deleted.

## Student Radar investigation

The identified 16 September Radar ran from approximately 22:40:32 to
22:42:06 UTC: runtime reports 93.7 seconds, not 67. Six model passes total
49.8 seconds. Five external command calls total about 41.6 seconds:

1. Gmail search with a fields projection: 8.96s.
2. Calendar window read: 8.49s.
3. Gmail search again, without that projection: 7.05s.
4. Read one candidate email: 8.01s.
5. Read another candidate email: 9.10s.

The first search and Calendar were requested in one model round, as were the
two email reads, but runtime completion times show sequential execution. Skill
loads and the local state read add about 0.6 seconds of measured tool time.
No retry/timeout was observed in this turn. A keepalive failure/recovery exists
elsewhere in the logs and cannot be attributed to this turn. The repeated search
is visible; this note does not establish that the second search was unnecessary
without inspecting the first result's semantics. No source-map read occurred.

The only 67.2-second turn identified in the retained log was a historical form
tracking request on 13 September, not Student Radar. The reported 67-second
Radar therefore remains uncorrelated. There is no performance code change.
Next useful investigation: correlate the exact Radar turn and check upstream
tool batching and the search projection result before proposing optimization.

## Validation and limits

Six regressions added: business-day uncertainty and relative-write guard;
same-local-day capture across UTC midnight and later persisted reads; independent
actionable preparation beside a third-party wait; drafting factuality contract;
classification contract; follow-up/time contract.

135 local tests and 148 isolated current-files image tests passed. Agent Index
self-check and linux/amd64 test-image build passed; diff whitespace check passed.
Prompt checks verify instructions, not actual LLM compliance. Validate the new
behavior with a fresh Hermes `/new` after an authorized runtime update. This
task did not restart or replace the owner runtime and did not change live state.
