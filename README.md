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

Prucê currently runs on demand. It does not schedule reminders, scan in the
background, or promise follow-up while the agent is idle. No Google, browser,
or Latch account is bundled with the image. WhatsApp, a dashboard, and a
multi-tenant service are outside the current release.

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

Prucê is a small variant of the official Plow Hermes image:

- `runtime/persona.md` adds the product identity and behavioral rules;
- `pruce-onboarding` learns context while helping;
- `pruce-tasks` owns the small validated JSON open-loop record;
- `pruce-sources` keeps a separate source and coverage map;
- `pruce-triage` handles prioritization, life scans, progressive permissions,
  and capability discovery;
- a named Docker volume persists Hermes memory and Prucê state;
- the official Agent Index client is pinned by commit and checksum and runs as
  an s6 service when enabled.

The base image composes its `SOUL.md` with Prucê's persona on every boot and
reconciles bundled skills into the persistent home. Open loops remain in
`/var/lib/hermes/pruce/state.json`; source metadata lives separately in
`/var/lib/hermes/pruce/sources.json`. There is no external database,
task-manager framework, or Prucê API.

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

Create `.env` in this repository:

```dotenv
PRUCE_CREDENTIALS_FILE=./plow-credentials
AGENT_ID=
```

An empty `AGENT_ID` disables Agent Index registration and reporting. If you
want this installation counted for the already registered Prucê agent and
accept the reporting described below, set `AGENT_ID=pruce` before first boot.

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

The Compose file retains a legacy default credential path for the original
development layout. Setting `PRUCE_CREDENTIALS_FILE=./plow-credentials` as
shown above makes a clean installation independent of that layout. The private
file is mounted read-only and excluded from Git and the Docker build context.

## Optional connected capabilities

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
form, delete, spend, or book. Consequential actions follow the confirmation and
approval rules supplied by the official stack.

Latch installation and account connection remain manual. Start with the
[official Latch page](https://plow.co/latch); do not send passwords, OAuth
tokens, or API keys to Prucê in chat.

## Privacy

Open loops, context, and source metadata live in the installation's Docker
volume. They may contain personal information, so do not publish the volume,
`state.json`, `sources.json`, credential file, or unreviewed logs. The source
map stores coverage metadata, not document or message bodies. Conversations
pass through Plow and the configured model provider; their retention and
protection follow those services' policies.

Agent Index reporting is opt-in through `AGENT_ID`. The pinned official client
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
python3 -B -m unittest tests.test_state tests.test_sources tests.test_product_behavior -v
AGENT_ID= docker compose config --quiet
```

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
Index client and the adapted s6 supervisor remain Apache-2.0; see `NOTICE` and
`LICENSES/Apache-2.0.txt`. The inherited Plow and Hermes image keeps its own
upstream licenses and notices.

- [Plow Hermes base](https://github.com/plow-pbc/plow-hermes-agent)
- [Official Agent Index client pin](https://github.com/plow-pbc/agent-index-client/tree/87901f8b182a8a7c65ee3dd7267f8f835ee2a545)
- [Official Life Assistant variant](https://github.com/plow-pbc/life-assistant-hermes-agent)
