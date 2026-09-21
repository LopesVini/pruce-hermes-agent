# Prucê unified web release

## Audit of the current cloud image

Inspected the official Plow base pinned by `dbfec58` inside the reference
`linux/amd64` image. Hermes ships `tools.web_tools.web_search_tool` and
`web_extract_tool`, `tools.url_safety.create_ssrf_safe_client`, native
`cron.jobs`/`cron.scheduler`/provider registration, and live delivery through
the originating chat. The existing RU adapter demonstrates that contract.
The native file reader extracts PDF, DOCX and XLSX, and Hermes includes image
vision for attachments actually delivered to its gateway. This release uses
those native tools through `pruce-research`; it does not bundle an OCR service
or promise that every inbound channel forwards every format.
The home volume is persistent and isolated per deployment; Prucê's canonical
task state is `/var/lib/hermes/pruce/state.json`.

Browser code exists in the base but is disabled in this variant. The previously
documented Latch browser and Google integrations require an external device or
authorization and are not used here. iPhone-only owners can configure watches
from their private iMessage DM; the jobs and reads run inside the cloud image.

In a fresh image with no web-search key, the official keyless provider returned
a transient 503 in the smoke test. The news script tries official Hermes web
search first and falls back to public Google News RSS with publication dates.
Prices use a bounded direct HTTPS GET with Hermes' SSRF-safe client; the page
is parsed locally. Neither route needs Mac, Latch, or a new credential.

## Implementation

`pruce-watch` is one conversational route for price watches, generic public-web
watches and an opt-in news
journal. State is `/var/lib/hermes/pruce/watches.json`, written atomically
under a lock. This file is separate from the established task/RU state and
inside the same isolated deployment volume. Active jobs are named and marked
`pruce-price-watch`, `pruce-news-digest`, and `pruce-news-important`.
Generic watches have an additional `pruce-generic-watch` job. A live search
seeds each watch, then twice-daily checks compare URLs. Alerts include at most
three links and are capped at one per watch every twelve hours. Failed or empty
searches never generate a false alert; results remain leads to verify, not
confirmed offers or availability. Repeated edits update an existing native job; cancellation removes only jobs
matching all three of its name, runner script, and marker. Runners read the
installed current skill code after image upgrades. No new scheduler or
messaging service was introduced.

Price checks run three times a day in scheduler time. The current page is
read only at creation and on checks. A changed lower price alerts only when
the chosen condition is met. Observed prices retain a bounded 100-entry
history; missing/changed HTML and HTTP failures preserve the last valid price.
The supported extraction order is JSON-LD Product/Offer, explicit price
metadata, and labelled HTML. No result is treated as zero.

News checks run on the owner's chosen local time and weekdays. Important-only
mode checks at 09:29, 15:29 and 21:29 local time. Date evidence is mandatory;
articles older than 72 hours are discarded. URLs and similar titles are
deduplicated against this edition and the previous 500 delivered stories. A
quiet search produces no scheduled message. A requested immediate digest
reports that nothing new was found instead. The last 1–6 stories are saved for
conversational follow-up.
The chosen news digest adds current watch labels, open-loop titles and a live
RU menu when a preferred RU and current menu are available. If there is no
new verifiable news, the scheduled digest remains quiet. An on-demand briefing
can still combine these sources whenever the owner requests it.

`pruce-research` provides five conversational verbs: Pesquisar, Comparar,
Analisar, Acompanhar and Decidir. Research checks multiple independent pages,
separates evidence from opinion and cites URLs. Document analysis uses native
Hermes extraction/vision and must acknowledge missing or unreadable material.
Comparisons and scenarios expose assumptions and costs. The opportunity radar
researches official UFMG/employer/program pages on demand; a recurring radar
uses the generic watch only after explicit opt-in.

Cron output is rendered without the native diagnostic header only for the
exact opted-in Prucê RU or watch records. All other Hermes jobs retain their
native presentation. The official Agent Index reporter remains in the base
and `AGENT_ID=pruce` remains set. One Click files were not changed.

## Validation and limits

Automated tests run inside the isolated image with networking disabled and no
owner home mounted. Public network smoke tests use a disposable container:
Books to Scrape's product page returned *A Light in the Attic*, GBP 51.77;
an immediate UFMG journal produced dated public stories and persisted their
IDs in a temporary home. No existing deployment or iMessage user was touched.
For this unified release, a live Hermes search returned UFMG results and
`web_extract` read the UFMG home page. In a disposable linux/amd64 container,
native document extraction read generated DOCX, PDF and XLSX samples with a
value and due date. Native cron tests created, updated and removed the generic
job in an isolated store; they did not send to a real handset.

Store blocking, client-rendered prices, currency ambiguity and redirects can
prevent automated price reading. Google News RSS links can be long and lead
through Google News; the public feed is not a guaranteed API. The MVP sends
verified headlines, dates, source and URL. It does not yet read every article
body, so editorial synthesis beyond the headline is deliberately omitted.
The important-only filter is conservative keyword matching, not a semantic
importance model. Event deduplication uses URL and title overlap and can miss
substantially different headlines about the same event. Delivery receipts and
handset receipt were not available in this isolated validation; a cron run
records a story/price before the messaging transport confirms handset receipt.
