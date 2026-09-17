# Public UFMG RU menu

## Verified official HTTP contract — 2026-09-17

The script embedded in https://fump.ufmg.br/cardapio-do-dia/ uses two public
HTTPS GET requests. No POST, session, cookie, nonce, browser, Google or Latch:

* `https://fump.ufmg.br:3003/cardapios/restaurantes` returns `{id,nome}[]`.
* `https://fump.ufmg.br:3003/cardapios/cardapio?id=1&dataInicio=2026-09-17&dataFim=2026-09-17`
  returns `{id,nome,cardapios:[{data,refeicoes:[{tipoRefeicao,tipo,pratos:[{tipoPrato,descricaoPrato}]}]}]}`.

IDs observed: Setorial II = 1; Saúde **and Direito share ID 2** and the API name
`RU Saúde e Direito`; ICA = 5; Setorial I = 6. Five physical units, four API
records. We retain five distinct user preferences and disclose the combined menu.
Dates in requests are YYYY-MM-DD; response date is an ISO timestamp at midnight
UTC used as a date label, **not** converted to the preceding day in Brazil.
Meals are `Almoço` and `Jantar`; a date can contain only one meal.
Unpublished dates return `cardapios: []`; an absent meal/empty dish list is also
treated as unpublished, not a network failure. Bad schema, wrong RU/date,
non-JSON, timeout or HTTP errors produce source-unavailable, without substitution.
The endpoint is site-observed, not a published versioned API guarantee. Cloud
needs outbound HTTPS access to fump.ufmg.br **port 3003** and working TLS/DNS.

The API does not label vegetarian ingredients or dietary certification.
`--field vegetariano` selects the published `Prato protéico 3` alternative and
explicitly states the classification/ingredients limitation. No dish-name-based
claims about vegetarian/vegan suitability or allergens are made.

## Implementation and preference

`pruce-ru` is bundled/discoverable in Hermes, with an always-on persona route
and a standard-library-only HTTP reader. Defaults: today's lunch in the RUs'
America/Sao_Paulo timezone, computed from the live clock. Supports tomorrow,
ISO and DD/MM/YYYY dates, aliases, dinner and requested dish categories.
One GET per menu query, six-second socket timeout, bounded response size,
no retry/browser/generic search. No cache: observed latency is already low,
and a new query should see updates. The timeout is a socket timeout, not a
guaranteed whole-turn deadline. Model/tool overhead is additional.

Optional `profile.preferred_ru` is null or `setorial_1|setorial_2|saude|direito|ica`.
The existing state.py `profile` command validates and writes it atomically under
the existing lock. Old profiles remain valid without migration; missing RU uses
this preference or asks. Explicit RU overrides it without writing. Other profile
fields, context, introduction and tasks remain intact. No open loop is created.
Missing state reads create nothing; corrupt state is not reset. The persistent
`/var/lib/hermes/pruce/state.json` remains canonical.

## Real observations in the built linux/amd64 image

Isolated read-only container; no owner volume, credentials, Mac or Latch.
On 2026-09-17:

* RU I lunch dessert: `Doce tablete` (0.305 s).
* RU II tomorrow lunch principal: `Lagarto Assado` (0.244 s).
* Saúde tomorrow: includes `Cuscuz de legumes com coentro` (0.220 s).
* Direito lunch protein alternative: `Quibe de Cenoura` (0.190 s), with qualification.
* ICA lunch dessert: `Doce de Paçoca` (0.298 s).
* RU I on 2099-01-01: unpublished (0.172 s).

These are dated observations, not immutable fixtures or a live iMessage test.
Fump warns that menus may change without notice. Unit fixtures are synthetic;
real public API smoke checks are separate from the offline regression suite.

## Daily opt-in through native Hermes cron

### Query versus delivery — real failure and corrected entry

Read-only inspection of the owner's failed 10h54 turn confirmed: `skill_view`
loaded pruce-ru, then `terminal` invoked menu.py, then a menu was returned;
subscription.py was never called. The prior skill's unconditional reader
instruction came before intent selection, and the adapter only implemented
recurrence. No one-off scheduling path existed. No personal transcript,
identity or credential is copied into this report.

All conversational RU requests now go through `request.py` with the user's
actual wording as JSON. Its intent classifier runs before a source request:
query, once, recurring, change or cancel. A future request cannot return menu
items through this entry: it schedules or asks for a missing detail. The
always-on persona and real Hermes skill-loading regression require this route.
This verifies deterministic dispatch inside the entry, not an unconditional
guarantee that an LLM can never disregard an instruction to use it.

* “O que tem no RU II hoje?” returns the current menu.
* “Me manda o RU II hoje às 10h54” creates a native `kind=once` job if future;
  a past time asks for another date/time, without showing a menu.
* “Me manda o RU II daqui a 5 minutos” computes the timestamp from the live
  runtime clock, creates one native job with repeat.times=1 and confirms only.
* “Me manda o RU II todo dia às 11h” creates/updates the recurring job.

One-offs use `pruce-ru-once:<key>` names, generated bootstrap scripts in the
existing Hermes scripts directory, and prompt metadata marker
`pruce_ru_once_v1`. Key hashes the aware timestamp and one destination;
repeating that same timestamp reuses its job. One-offs coexist with the one
recurring subscription. The bootstrap selects exactly its own job, not a
different subscription. Cancellation removes managed one-offs and recurrence.
Native job storage, provider registration, due checks and terminal lifecycle
remain Hermes' responsibility; there is no new scheduler.

### Persisted lunch-time opt-in

Optional `profile.ru_delivery` contains stage, pending_lunch_time,
usual_lunch_time and RU reference. Legacy profiles remain valid without it.
After a successful query without configured recurrence or offer history, the
entry appends “Você costuma almoçar que horas?” once and records its stage.
A time answer records only a pending candidate and offers a concrete send
time one hour before lunch, Monday–Friday by default, with alterable days.
Only acceptance creates the cron and saves usual_lunch_time. Known preferred_ru
is honored. “Sim, mas todos os dias” selects daily instead of weekdays.

Decline and cancellation persist and suppress further automatic offers across
queries, sessions and restarts. Bare “sim” without a pending offer is not
consent. Direct explicit subscription requests remain allowed after decline.
Changing usual lunch time offers the new send time for fresh confirmation;
existing delivery is unchanged until acceptance. Direct RU/send-time changes
update the same recurring job. No offer counter or unsolicited send is added.

No task or open loop is created by this onboarding. Failed source queries do
not initiate the offer. A lunch time that would shift the send to the previous
day asks for an explicit send time rather than guessing weekday semantics.

Implemented by `subscription.py` (management adapter) and `daily.py` (delivery
payload). No new scheduling engine, polling loop, subscription database or
task/open loop. The normal menu reader remains unchanged.

Only explicit owner consent enables delivery. A first request needs RU, exact
local HH:MM, `daily` or `weekdays`, and known/confirmed IANA timezone. “Antes do
almoço” asks for a time before creating anything. Missing RU uses canonical
preferred_ru, otherwise asks. A known America/Sao_Paulo profile is honored;
unknown timezone asks for confirmation rather than assuming the server clock.

The adapter captures the destination with native `_origin_from_env`, from the
fresh session vars that Hermes' local terminal injects on each command. This
is not a model-guessed chat ID or home-channel fallback. Group context is
rejected. One explicit destination and the captured origin are stored; failure
notices stay `local`. A deployment/backend that does not bridge a verified DM
destination fails closed; do not claim notifications were enabled there.

### Native persisted record

The persistent volume contains:

* `/var/lib/hermes/cron/jobs.json`: one managed job named `pruce-ru-daily`, with
  `script: pruce-ru-daily.py`, `no_agent: true`, native schedule, destination,
  origin and `failure_deliver: local`. Its ignored-by-model `prompt` stores
  JSON metadata: `kind: pruce_ru_daily_v1`, RU, agreed time/days/timezone and
  opt_in. Native APIs handle job locking/storage and provider registration.
* `/var/lib/hermes/scripts/pruce-ru-daily.py`: atomic installed bootstrap that
  invokes the current installed skill code. No menu snapshot or personal path.
* `/var/lib/hermes/pruce/state.json`: existing optional preferred_ru, saved
  after successful subscription. Other profile fields and tasks are untouched.
* `/var/lib/hermes/pruce/ru-subscription.lock`: management-only advisory lock
  preventing concurrent duplicate subscriptions, not another scheduler/store.

Repeated requests update the same job ID; RU/time changes reuse established
details/destination. Existing duplicates are consolidated only when name,
script and metadata marker match. Unrelated jobs are preserved. A failed cloud
registration can leave a native record; retry updates/registers that record,
not a duplicate. Never confirm success after a registration error.
Cancelling removes managed jobs, preserves preferred_ru and other state, and
is idempotent. A later preference-only save does not change an existing
subscription's RU; an explicit subscription change does.

Hermes cron uses its profile timezone, not a per-job timezone. The adapter
translates the agreed local time and weekdays into that scheduler clock when
their relative offset is stable (checked across 400 days). Example: 11h Brasília
becomes `0 14 * * *` on UTC; weekdays becomes `0 14 * * 1,2,3,4,5`.
On a matching America/Sao_Paulo scheduler it is `0 11 * * *`. A DST mismatch
is refused instead of flattening a changing offset. Configure the Hermes
profile timezone consistently before enabling that case. Do not later change
the scheduler timezone without updating the subscription.

### Execution and silence

Native `no_agent` execution calls the current reader once for today's lunch.
Only `status=ok` with nonempty items prints menu text. Unpublished, unavailable,
invalid, cancelled, ambiguous or corrupt subscription yields empty stdout and
successful silent exit. Hermes already suppresses empty stdout; no model,
Mac, Google, repeated failure DM, retry loop or catch-up send is involved.
Delivery still uses the installation's existing messaging transport; fetching
does not need Latch, but an iMessage transport may have its own dependencies.

The persisted lunch-time offer above replaces the former conversational
suggestion. Do not append a second offer to each query; no unsolicited
scheduled question or counter is created. Decline/cancellation suppress it.

### iMessage validation after activation

1. `/new`, then “Me manda o cardápio do RU II todo dia antes do almoço.”
   Expect a time question and no job yet. Reply with an exact time.
2. With a known RU/fuso, “Todo dia às 11h me manda o bandejão.” Expect one
   confirmed subscription. Repeat and inspect status: the job ID stays the same.
3. “Me avisa o cardápio do RU I de segunda a sexta às 11h.” Then “Troca para
   o RU II.” Expect an update, not a second subscription.
4. For an end-to-end send, explicitly request a time a few minutes ahead during
   a day with published menus. Keep the gateway running; confirm one useful
   menu at that time. Do not use an already-past time to test immediate delivery.
5. “Para de me mandar o bandejão” or “Não quero mais o cardápio diário.”
   Expect cancellation; the native job is removed and no next scheduled send.

Single future send: “Me manda o cardápio do RU II daqui a 5 minutos.” Expect
confirmation only and a native once job with repeat.times=1; no menu now.
Keep the gateway running and confirm a useful published menu at execution.
Onboarding: query a menu with no offer history, answer “12h”, then accept the
11h Monday–Friday offer. Refuse on a separate fresh test deployment and confirm
later queries do not repeat the offer. Do not reset the owner's real profile
just to manufacture a clean onboarding test.

Offline tests use temporary Hermes homes and synthetic destinations, including
real native store/provider APIs, fresh terminal routing bridge, concurrent
requests, updates/cancellation, timezone conversion, provider failure retry,
the native no-agent silence gate and a real cancelled wrapper subprocess.
Source/menu and native delivery-gate fixtures are synthetic; actual owner
iMessage delivery and private Plow scheduler availability are not claimed as
validated by those tests. No subscription was created in the owner's runtime.

Additional live-public smoke in an ephemeral read-only linux/amd64 container:
native `scheduler.run_job` executed the installed bootstrap and current reader,
returned the real RU II menu in 0.799 s, then returned Hermes' SILENT_MARKER
after cancellation. No channel sender was invoked. A separate direct reader
run in the same packaging took 0.238 s and a RU change retained the job ID.

## Validation and activation

### Clean proactive message body

The real iMessage one-off delivery succeeded, but Hermes added “Cronjob
Response”, job ID and its English management footer in `_deliver_result`.
The same renderer is used for recurring menus. The native wrap_response flag
is global, so toggling it would also change unrelated jobs.

The image now applies `image/patch_ru_delivery.py` to the pinned delivery
renderer. It changes only whether the header/footer is added: an opted-in
no_agent RU record must match our name, script and JSON marker (plus generated
key for one-offs). Its content reaches both live-adapter and standalone sender
unchanged. Other jobs, failure rendering and the native global flag keep their
existing behavior. Cron storage, due checks, execution, targets and cancellation
are untouched. Existing valid RU jobs benefit after restart; do not recreate
their schedules or modify personal config.yaml.

The build verifies the original renderer's exact SHA256 and unique patch
anchor; a different base source fails closed and requires review. The base
image pin/digest is unchanged. Regression invokes the real native delivery
formatter and captures only synthetic sender boundaries: once and daily must
deliver the exact menu without internal metadata, through both transport paths.
No owner channel is contacted by these tests.

Offline suite: `python3 -B tests/run_in_image.py` after
`docker build --platform linux/amd64 -t pruce-index-check:local .`.
Includes alias/date/failure/preference tests, real Hermes skill discovery/load,
real composed persona injection and the existing Agent Index self-check.
Compose validation: `docker compose config --quiet`.

The owner runtime was not restarted. To activate after review:

```sh
docker compose build agent
docker compose up -d --no-deps --force-recreate agent
```

Then `/new` in iMessage and ask a RU question. Keep the existing persistent
volume. No commit or push is part of this change.
