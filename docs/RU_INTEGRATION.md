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

## Remaining daily opt-in connection

No cron job, subscription or automatic send is created by this release.
Pinned Hermes already supports `cronjob` with `script`, `no_agent=true`,
`schedule`, `deliver`, `failure_deliver`; its schema explicitly says script-only
jobs deliver stdout verbatim and empty stdout sends nothing. Script paths must
resolve inside `$HERMES_HOME/scripts/`, **not directly inside the skill**.

The smallest next step after explicit consent:

1. Confirm RU (save preference), local send time/timezone and one verified
   owner DM destination. Do not assume “before lunch” means a particular time.
2. Install a small wrapper in `/var/lib/hermes/scripts/` that calls this reader
   at execution time for today/lunch. It must print **only `result['text']`**
   when `status == 'ok'` and `items` is nonempty. On all other statuses print
   nothing; never print the reader's full JSON or errors to the recipient.
3. Create one script-only Hermes cron job (`no_agent=true`) for the agreed
   time and explicit destination, with failures kept local. Persist any
   subscription metadata in profile/cron, never in task open loops. Choose
   deliberately whether later RU preference changes update the job.
4. Test port 3003 from the actual deployment, timezone, empty stdout suppression,
   channel delivery, cancellation/update and restart persistence. Prefer an
   update to duplicate subscriptions; never broadcast to all channels.

No Plow backend change is needed for public menu reads. Actual cron delivery
depends on the deployed gateway/channel configuration; this release does not
claim that delivery was validated.

## Validation and activation

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
