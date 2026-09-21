# Prucê

**The personal agent for the things you need to deal with.**

Prucê helps students and young adults move unfinished responsibilities from
mental load to a clear outcome. It is built for **Student Life + Adulting**:
exams, applications, forms, deadlines, subscriptions, refunds, documents, and
all the small obligations that become expensive when ignored.

It is not a generic chatbot or a task-board interface. Prucê keeps an **open
loop** for the outcome that still needs attention, identifies the next concrete
step, helps execute it, waits when another person or organization owns the next
move, and closes the loop only when the outcome is confirmed.

Examples:

- “I have an exam Saturday, an internship reply, and enrollment closes tomorrow.”
- “I submitted my credit-transfer request. Now the university needs to answer.”
- “Find out whether this trial is still active and help me cancel it.”
- “What is the most important thing I should deal with today?”
- “Am I missing anything?”

## What works today

- short, progressive onboarding with value before profile questions;
- persistent open loops across conversations and restarts;
- multi-loop triage using urgency, consequence, dependencies, effort, time
  stuck, and the owner's context;
- on-demand life scans over saved open loops and any connected, authorized
  sources;
- a progressively learned source map that respects paper, screenshots, local
  files, and the apps the owner already uses;
- contextual permission prompts and capability discovery;
- practical help with study plans, CV text, applications, requests, forms, and
  other next steps using the tools that are actually available;
- evidence-backed transitions between `needs_action`, `in_progress`,
  `waiting_for_user`, `waiting_for_third_party`, and `completed`.

The status values are internal. The owner gets a natural conversation, not a
Kanban board or a numerical priority score.

Prucê also offers opt-in proactive RU delivery, price watches, and a personal
news journal. These use native cloud cron and the deployment's private home;
they run while the owner's phone or computer is offline. Other task follow-ups
remain on demand. No Google, browser, or Latch account is bundled with the
image. WhatsApp, a dashboard, and a multi-tenant service are outside this release.
See [accompaniments](docs/WATCHES_RELEASE.md) for source and delivery limits.

For the hackathon release, connected external integrations are observation
sources only. Prucê can search, inspect, compare, discover, prioritize, draft
and track work in its own state, but it does not perform the final external
send, submission, deletion, purchase, booking, publication or account change.
The existing operation ledger is preserved for reliability history and future
work; it is not used to claim that external writes are enabled.

## One person, one deployment

Each Prucê installation belongs to one person. It has its own Plow line,
credential, persistent volume, memory, integrations, channels, and Agent Index
installation identity. iMessage, Plow Chat, or a future channel are ways to
reach that same installation; they are not separate user accounts.

At boot, Plow identifies exactly one active home chat containing the line's
owner and this agent. An ambiguous or missing home chat prevents the stack from
starting instead of guessing. Prucê reads or changes personal state only in the
owner's one-to-one chat. Sharing a line, credential, or home volume with another
person breaks the privacy model and is unsupported.

## Architecture

Prucê is a small variant of the official Plow Hermes image. The Dockerfile pins
the cloud-compatible base validated for this release; that base also pins its compatible
`hermes-plugin-plow` version:

- `runtime/persona.md` adds the product identity and behavioral rules;
- `pruce-onboarding` resumes a bounded structured first run while helping;
- `pruce-tasks` owns the small validated JSON open-loop record;
- `pruce-operations` keeps inactive receipt/retry instructions out of ordinary
  task turns while preserving the separate ledger and its replay blocks;
- `pruce-sources` keeps a separate source and coverage map;
- `pruce-triage` handles prioritization, life scans, progressive permissions,
  and capability discovery;
- a named Docker volume persists Hermes memory and Prucê state;
- the official Agent Index client is pinned by commit and checksum and runs as
  an s6 service when enabled.

The base image composes its `SOUL.md` with Prucê's persona on every boot and
reconciles bundled skills into the persistent home. The backward-compatible
structured first-run profile and open loops remain in
`/var/lib/hermes/pruce/state.json`; source metadata lives separately in
`/var/lib/hermes/pruce/sources.json`. There is no external database,
task-manager framework, or Prucê API.

The preserved reliability design uses a small receipt in
`/var/lib/hermes/pruce/operations.json`. Each receipt fixes one intent, action,
target, payload hash, authorization and derived idempotency key. A success,
in-flight interruption or ambiguous result blocks another attempt until the
actual service is reconciled; a confirmed safe failure can be retried under the
same key. This guard does not turn local state into proof of an external effect
and does not replace provider-side idempotency when available. It is not a
gateway or tool-call interceptor: bypassing the workflow also bypasses this
guard. The hackathon build therefore preserves the ledger without treating it
as permission to enable external writes.

Hermes snapshots the composed persona and skill guidance when a conversation
session starts. After changing those files and rebuilding, use a fresh `/new`
session for behavioral reliability tests; an already open conversation may
continue following its older prompt snapshot. The named volume, open loops,
source map and operation receipts survive `/new`. This repository does not add
hot reload because the session boundary is explicit and persistent state is
already separate from prompt state.

Deadline wording such as “tomorrow night” remains available as history, while
an optional temporal object anchors it to the capture instant and the owner's
known IANA timezone. It preserves date, exact datetime, day-part, range, or
unresolved granularity. Older records remain readable; relative legacy text
without a trustworthy capture timestamp is reconciled only when it matters and
is never reinterpreted using today's date.

## Source-aware coverage

Prucê does not assume that one app contains the owner's whole life. It learns
one relevant fact at a time: Calendar may hold appointments, university dates
may live in a paper notebook, applications in Gmail, and notes in Obsidian.

The source map records only a functional area, the source name, access mode,
the last grounded observation when useful, and the context of an accepted or
declined permission offer:

```json
{
  "sources": [
    {
      "area": "academic_planning",
      "source": "paper notebook",
      "access": "manual",
      "last_seen": "2026-09-13 — notebook photo supplied in this chat",
      "offer": null
    }
  ]
}
```

`connected` means a route was verified, `manual` means the owner supplies a
snapshot, and `unavailable` records a known coverage gap. A connected entry is
still checked live before use. A manual observation is dated context, never a
claim that the notebook or screenshot remains current forever.

A Life Scan separates known context, sources successfully consulted in that
turn, and manual or stale sources. Its confidence follows that coverage. Prucê
can therefore say that no new deadline appeared in the sources it could see
while also explaining that academic planning is less certain because the last
notebook photo is old.

## Install

Requirements: Docker with Compose v2, Git, Python 3, and a Plow account. The
current base image is `linux/amd64`; Docker Desktop can emulate it on Apple
Silicon.

Clone Prucê and the official Plow CLI:

```sh
git clone https://github.com/LopesVini/pruce-hermes-agent.git
cd pruce-hermes-agent

pruce_cli_dir="$(mktemp -d)"
git clone https://github.com/plow-pbc/plow-agents.git "$pruce_cli_dir/plow-agents"
export PATH="$pruce_cli_dir/plow-agents/bin:$PATH"
```

Authenticate, activate your account as instructed by the CLI, and choose a
line with status `free`. Use `login --new-line` if you need a new line.

```sh
plow-agents login
plow-agents lines
plow-agents mint ln_xxx
chmod 600 plow-credentials
```

Optional `.env` overrides in this repository:

```dotenv
PLOW_CREDENTIALS=./plow-credentials
AGENT_ID=pruce
```

Compose defaults to the already registered `AGENT_ID=pruce`. An explicitly
empty `AGENT_ID` disables Agent Index registration and reporting. The private
credential file defaults to `./plow-credentials`; no `.env` is required.

Start the agent:

```sh
docker compose build
docker compose up -d
docker compose logs -f agent
```

When the log shows that Plow configured the selected chat, message your line
through iMessage or Plow Chat. Reuse this repository and Compose project for
future starts. `docker compose restart agent` preserves the named volume and
the owner's open loops. Do not run two gateways with the same line or home, and
do not use `docker compose down -v` unless you intend to erase local memory.

The Compose file reads the private credential file into the container
environment, which is the current base image's credential contract. The
`PLOW_CREDENTIALS` override and legacy `PRUCE_CREDENTIALS_FILE` override support
other locations without depending on the original development layout. The file remains
excluded from Git and the Docker build context and is not mounted into the
agent's persistent home. Cloud provisioning injects its own environment and
does not use this local file; see [Cloud deployment](docs/CLOUD_DEPLOY.md).

## Optional connected capabilities

Direct Google on Linux/cloud was audited separately: see
[Google Workspace direct audit](docs/GOOGLE_WORKSPACE_DIRECT_AUDIT.md).
The native scripts remain in the image, but a hosted user authorization flow
is not enabled in this release.

The official stack reaches the owner's Mac through **Plow Latch**. When Latch
is configured and the Mac is awake, its MCP relay publishes the tools and
instructions available on that machine.

- Gmail and Google Calendar use the bundled `google-workspace` skill through
  Latch. The agent never creates or stores a local Google OAuth token.
- Browser work uses Latch's browser tools on the owner's Mac. The container's
  unsupported browser toolset is deliberately disabled.
- Files, Notes, Reminders, Obsidian, and other capabilities depend on the
  skills and paths that the connected Latch instance actually publishes. A
  bundled catalog entry alone does not establish access. This release does not
  claim a dedicated Google Drive connector.

Prucê does not ask for these integrations during a generic welcome. It offers
one only when it can explain the immediate result and initial access scope. A
connected read capability never implies permission to send email, submit a
form, delete, spend, or book. The hackathon build keeps those external actions
disabled even if the official stack exposes a write-capable tool.

Latch installation and account connection remain manual. Start with the
[official Latch page](https://plow.co/latch); do not send passwords, OAuth
tokens, or API keys to Prucê in chat.

## Privacy

Open loops, context, and source metadata live in the installation's Docker
volume. They may contain personal information, so do not publish the volume,
`state.json`, `sources.json`, `operations.json`, credential file, or unreviewed logs. The source
map stores coverage metadata, not document or message bodies. Conversations
pass through Plow and the configured model provider; their retention and
protection follow those services' policies.

Agent Index reporting is opt-in through `AGENT_ID`. The Plow base image's own client
reads Hermes' `session_model_usage` counters and sends day, model, input/output
tokens, and cache read/write tokens every five minutes. It does **not** read or
send prompts, messages, open-loop titles, documents, or the Prucê JSON state.
Reporting still reveals activity patterns by day and model.

The client generates a random `install_id` and an `aik_` reporting key for each
installation and stores them in the same private volume. Repeated reports use a
local ledger so totals are not counted as new usage. Never copy those files
between people or create an installation ID manually. Without `AGENT_ID`, the
s6 service does not invoke the client.

## Test and contribute

Run the state, source-map, and prompt-contract tests locally:

```sh
python3 -B -m unittest tests.test_first_run tests.test_state tests.test_sources tests.test_operations tests.test_product_behavior -v
AGENT_ID= docker compose config --quiet
```

`tests.test_first_run` rehearses the complete first run under a temporary
Hermes-like directory. It never reads or writes the active Docker volume.

For a targeted Calendar latency check, use a fresh `/new` session and inspect
timestamped container logs only after the reply. Keep the measurement internal:
separate the initial model interval, Google skill/tool selection, the single MCP
call and its Latch/Google return, and the final model interval. A reconnect or
retry line belongs to the MCP interval. Never include these diagnostics in the
normal user response. The product contract for this path is one bounded
Calendar read with no task/source-map/Gmail detour.

```sh
docker compose logs --timestamps --since 10m agent \
  | rg 'API call #|tool .* (completed|failed)|MCP|mcp|reconnect|plow'
```

The current Hermes base logs each model API call's latency and each tool's
duration. Docker timestamps bracket selection/dispatch and relay reconnects, so
the trace distinguishes the two model intervals from the MCP/Latch interval
without adding timing text to Prucê's reply.

Validate the exact client installed in the image without credentials, real
volumes, or network access during the test run:

```sh
docker build --platform linux/amd64 -t pruce-index-check:local .
python3 -B tests/run_in_image.py
```

The runner mounts only an explicit source allowlist into disposable containers.
It uses synthetic identity and usage data, a read-only root filesystem, tmpfs
state, `--network none`, and Python as the entrypoint, so neither the gateway
nor s6 services start. The Docker build itself downloads only public pinned
dependencies and verifies the Agent Index client checksum.

Keep contributions focused on reusable Student Life + Adulting decisions.
Prefer a small, deep behavior over domain-specific skills or a generic task
manager. Do not commit credentials, state, install identity, conversation
content, or account data.

## License

Prucê's original code and documentation are MIT licensed. The official Agent
Index client and its s6 service, shipped by the base, remain Apache-2.0; see `NOTICE` and
`LICENSES/Apache-2.0.txt`. The inherited Plow and Hermes image keeps its own
upstream licenses and notices.

- [Plow Hermes base](https://github.com/plow-pbc/plow-hermes-agent)
- [Official Agent Index client](https://github.com/plow-pbc/agent-index-client), shipped by the base
- [Official Life Assistant variant](https://github.com/plow-pbc/life-assistant-hermes-agent)

## WhatsApp

Preparação, pairing e reversão: [docs/WHATSAPP.md](docs/WHATSAPP.md).
