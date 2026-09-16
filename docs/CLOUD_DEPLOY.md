# Prucê cloud / One Click deployment

Contract checked on 2026-09-16 against official repository HEADs:

- [plow-agents](https://github.com/plow-pbc/plow-agents/commit/bf66700): image build/push and local/cloud deploy CLI.
- [plow-hermes-agent](https://github.com/plow-pbc/plow-hermes-agent/commit/910b8e3): environment-based provisioning.
- [Life Assistant](https://github.com/plow-pbc/life-assistant-hermes-agent/commit/328b0f5): reference variant image and reporter.

## Local execution

Run `plow-agents mint <free-line-id>` from this checkout. It creates a private
`./plow-credentials` containing `PLOW_API_BASE` and `PLOW_AGENT_TOKEN`. The
Compose file loads it through `env_file`, without mounting it into the home.
`PLOW_CREDENTIALS` overrides the file location; the existing
`PRUCE_CREDENTIALS_FILE` override remains supported. The default no longer
depends on a sibling checkout. Credentials are excluded from Git and the build
context. Never mint/rotate/revoke the owner's current identity for a smoke test.

Compose uses linux/amd64, keeps `agent-home:/var/lib/hermes`, and defaults to
the existing registered `AGENT_ID=pruce`. Explicit `AGENT_ID=` disables reporting;
an existing `.env` with that value continues to disable it. The credential file
is optional so an operator can inject the environment directly. Missing both
credentials and provisioning environment does not create an agent: the base's
bootstrap parks rather than guessing identity.

## Cloud execution

Cloud runs the image directly, not this local Compose file. The provisioner
injects `PLOW_API_BASE` and `AGENT_ID=pruce` and must preserve an isolated
`/var/lib/hermes` home for each owner. In the exe.dev integration model the proxy
injects the real bearer; no `PLOW_AGENT_TOKEN` secret is required inside the VM.
The base publishes the placeholder `proxied` for consumers, including the
reporter's registration exchange. A direct API connection instead needs that
deployment's own real `PLOW_AGENT_TOKEN`. Never reuse the developer's credentials.

The base asks `/v1/agents/cloud/me` for identity and the owner chat. A null
`mcp_url` disables the Mac relay and does not block bootstrap. Gmail/Calendar
remain optional. Persona and bundled skills come from the image; canonical
state, sources, operation receipts and Index identity stay in the isolated home.
The reporter depends on `plow-init`, stands down on unreadable Index state, and
passes the bearer only to registration. Do not reset persistent identities.

## Why the base pin stays unchanged

The working tree already pins base `80ef5024eb4b770e727a618a9b55421c73da6228`
by digest. It already supports environment provisioning, proxy-placeholder
authentication and no-Mac bootstrap. Comparing it with current base `910b8e3`
shows no bootstrap changes: later image changes bump the chat plugin for voice,
interrupts, invites and Plow/Latch capability wording. They do not establish a
required One Click contract change. Life Assistant uses the same Index client
pin as Prucê. Neither pin is updated solely for recency.

## Publishing and enabling the listing

The latest CLI can build linux/amd64, push to a public registry and request
`plow-agents deploy <public-image>@sha256:<digest> --line <free-line-id>`.
Those are external actions, not local validation. A custom-image request does
not itself enable the Prucê One Click listing or prove Index slug mapping.

For the official listing, send Daniel the public repo URL, the complete tested
revision and registered Index ID `pruce`. Ask him to build/publish and select
that revision in Plow's private `api/cloud-agents/agents.json` configuration,
enable One Click for Prucê, and confirm:

1. The deployment receives `AGENT_ID=pruce` and its own Plow API integration.
2. Each owner receives an isolated persistent home and install identity.
3. Boot succeeds when `mcp_url` is null, and delivery reaches that owner's chat.
4. An update retains state.json, sources.json, operations.json and Index identity.

No credentials, local state, install IDs or reporting keys should be sent.

## Validation in this task

129 local tests passed; 142 current-files image tests and the Index self-check
passed offline. Linux/amd64 build and Compose validation passed, including an
absent optional credential file. A disposable container on an internal Docker
network bootstrapped against a synthetic identity API with only PLOW_API_BASE,
no token and no Mac. It published `proxied`, reconciled skills and started s6
gateway services. Synthetic canonical state, sources and operations were checked
across restart. The fixture does not implement the live chat API: adapters
receive expected 404s, so this is bootstrap/persistence evidence, not a live
messaging or private-cloud provisioning test. The owner container was untouched.

The initial deployment commit contained only Compose and this note. The final
release also commits the existing product, packaging and test files unchanged
in behavior, so a clean checkout contains the complete tested version. Local
credentials and runtime data are not part of that revision. Final validation
runs from an exported committed tree, independently of the developer checkout.
