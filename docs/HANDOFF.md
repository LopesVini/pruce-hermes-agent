# PRUCÊ — ENGINEERING / PRODUCT HANDOFF

Last updated: 2026-09-16
Owner: Vinicius
Project: Prucê
Hackathon: AI Worth Using / Plow / Hermes
Agent Index ID: `pruce`

Repository:
https://github.com/LopesVini/pruce-hermes-agent

Local workspace:
~/Developer/pruce-hackathon/pruce-hermes-agent

Agent Index:
https://aiworthusing.com/agent-index/pruce

IMPORTANT:
This document is context, not absolute authority.
The CURRENT REPOSITORY and CURRENT RUNTIME are the source of truth.

Before making changes:
- inspect git status
- inspect recent commits
- inspect the actual current Docker/runtime configuration
- reconcile this handoff with the code

Do not blindly reproduce historical architecture described here if the repo has already evolved.

---

# 1. WHAT PRUCÊ IS

Prucê is a personal follow-through agent.

It is NOT intended to be:
- just a task manager
- just Gmail + Calendar AI
- just a student app
- just a generic chatbot

Core thesis:

> Prucê finds what you're about to miss, decides what actually matters now, and keeps track of what still isn't really resolved.

Tagline:

> Less to remember. More actually handled.

Another useful positioning:

> Your life doesn’t live in one app. Prucê finds the open loops scattered across it.

The core product loop is:

Discovery
→ Prioritization
→ Execution / Preparation
→ Follow-through
→ Closure

The most important conceptual rule is:

ACTION PERFORMED != OUTCOME RESOLVED

Examples:

Refund requested
!=
Refund received

Cancellation requested
!=
Subscription cancelled

Application sent
!=
Hiring process finished

Support ticket opened
!=
Problem solved

Prucê should model one evolving process/open loop, not create five disconnected tasks.

---

# 2. PRODUCT POSITIONING

Current product direction:

GENERAL PERSONAL LIFE ASSISTANT
with specialization based on the user.

Main beachhead / acquisition niche:

Student Life + Early Adulting

Especially:
- university students
- initially UFMG students
- young adults learning to manage deadlines, replies, subscriptions, bureaucracy, work and university

Do NOT make the product student-only.

The same core should adapt to different users.

Examples:

Student:
- university
- work
- adulting

Parent:
- work
- household
- appointments
- adulting

Other adult:
- work
- personal admin
- family
- bureaucracy

The specialization should come from onboarding/profile/context, not separate products.

For UFMG marketing we can position it as:

> Prucê for university life.

without changing the global product identity.

---

# 3. CORE STATE MODEL

Canonical Prucê state currently lives in:

/var/lib/hermes/pruce/state.json

Source map:

/var/lib/hermes/pruce/sources.json

Concept:

> Memory is context. Canonical state is authority for current operational facts.

Conversation history or assistant claims are NOT authoritative current-state evidence.

Main open-loop states:

- needs_action
- in_progress
- waiting_for_user
- waiting_for_third_party
- completed

`completed` should mean:
- the real outcome is evidenced, OR
- the user explicitly tells Prucê to stop tracking it

A sent action does not mean completion.

---

# 4. TEMPORAL GROUNDING

A substantial reliability layer already exists.

Do not regress it.

Problem originally solved:

Persisting phrases such as:

due = "amanhã"

and later incorrectly reinterpreting them relative to a new day.

Prucê now grounds time using effective temporal structures such as:
- datetime
- date
- day_part
- date_range
- unresolved
- raw phrase
- timezone
- capture basis
- provenance/evidence

Concept:

RAW PERSISTED DATA != VALIDATED EFFECTIVE FACT

If an old temporal statement cannot be trusted, Prucê should ask naturally.

User-facing example:

> “Eu não confio nessa data ainda. Qual era o prazo certo?”

Do not expose internal jargon such as temporal provenance unless explicitly asked.

---

# 5. SOURCE MAP

Prucê tracks where information usually lives.

Examples:

Calendar = commitments
Gmail = replies/processes
paper notebook = academic tasks
photo = snapshot/manual source

Conceptual access states:
- connected
- manual
- unavailable

Important:

CONNECTED != LIVE AVAILABILITY VERIFIED NOW

A photo or old note is a snapshot, not eternal truth.

Current source map design is flexible but can be empty for legacy users if it was never explicitly populated.

Do not invent source availability.

Live capability checks should be authoritative for current availability.

---

# 6. ONBOARDING

The original onboarding was too shallow.

Previously:
- short introduction
- optional prose context
- `introduced=true`

This was weaker than the Life Assistant reference.

A newer structured/resumable onboarding was implemented locally.

Current intended structured profile includes:

preferred_name:
- pending
- known
- skipped

timezone:
- pending
- known
- unknown
- skipped

city may be retained when useful.

university:
- pending
- known
- skipped

course:
- pending
- known
- skipped

primary_radar_preference:
- pending
- university_deadlines
- important_replies
- adulting_bureaucracy
- skipped

Important requirements:

- onboarding must remain short and conversational
- never become a long questionnaire
- a real user task always takes priority over onboarding
- sources/integrations are optional
- existing legacy users with `introduced=true` must not suddenly receive a questionnaire
- existing free-text context must remain valid
- profile fields should persist deterministically
- onboarding should be resumable

General product direction going forward:

Do not assume everyone is a student.

Longer-term onboarding should adapt to:
- study
- work
- household
- family
- adulting

University/course should only become relevant if studying is relevant.

---

# 7. SIGNATURE EXPERIENCES

These are INTERNAL routing/product experiences.

Users do NOT need to type exact magic commands.

Natural language should route into them.

## STUDENT RADAR

Intent examples:

“Tem alguma coisa da faculdade que tô deixando passar?”

“Algum professor mandou algo importante?”

“Tenho alguma entrega essa semana?”

“Olha meus emails e vê se tem algo da UFMG.”

Intended behavior:

- read active loops once
- read source coverage once when needed
- inspect only university-relevant sources
- if Gmail + Calendar are both relevant and live-available, request them in the same external round
- return at most 3 useful findings

Priority:

1. hard deadline/conflict
2. important reply/action
3. meaningful unresolved/manual coverage gap

Do not ask permission again to inspect read-only relevant sources when the user already explicitly requested a university scan and those sources are confirmed available.

Do not claim unavailable sources are connected.

---

## WHAT NOW

Intent examples:

“Tenho duas horas, o que faço?”

“O que deveria resolver primeiro?”

“Estudo Mecânica ou faço o projeto?”

“Tenho até 18h. O que dá pra resolver?”

Use:
- grounded deadlines
- current Calendar availability
- consequences
- dependencies/unblocking value
- realistic duration

Return:
- one primary work block
- at most one secondary task if it genuinely fits

Ask one clarifying question ONLY when a missing fact could actually reverse the recommendation.

---

## FOLLOW-THROUGH

Intent examples:

“Aquilo resolveu?”

“A empresa respondeu?”

“E o reembolso?”

“Já cancelaram minha assinatura?”

“A professora respondeu?”

Reuse the SAME open-loop record.

Preserve:

action performed != outcome resolved

A sent request generally becomes:

waiting_for_third_party

not:

completed

Completion requires:
- authoritative evidence of the outcome, OR
- explicit user decision to stop pursuing it

This is one of Prucê’s strongest differentiators.

---

## ADULTING SCAN

Same underlying open-loop engine.

Useful categories:
- subscriptions
- trials
- renewals
- refunds
- documents
- applications
- expiration
- bureaucracy
- support
- payments / expected charges

Do not build a second task system for adulting.

---

# 8. GOOGLE / LATCH / PLOW

Current owner Gmail/Calendar access works through the Mac-side Plow/Latch/Google Workspace path.

Conceptually:

Prucê
→ Hermes
→ Plow/Latch
→ Mac
→ Google Workspace
→ Gmail / Calendar

Important limitation:

There is currently NO confirmed direct/cloud Google OAuth path in Prucê for users without a Mac.

The previous Life Assistant audit also found its owner Gmail/Calendar path depends on Mac/Latch.

For a non-Mac user:

chat may work

but Gmail/Calendar personal integration is NOT currently guaranteed.

Possible future solution:

deployment
→ per-user Google OAuth
→ read-only Gmail/Calendar

But that requires:
- OAuth
- per-user token storage
- refresh
- revocation
- tenant isolation
- scopes
- security handling

Do not build this casually.

First confirm with Plow whether they have or are shipping a supported non-Mac Google path.

---

# 9. CURRENT CHANNELS

iMessage / Plow Chat:
- working

WhatsApp:
- NOT integrated into current Prucê yet

Telegram:
- not a current priority

Important architecture principle:

CHANNEL != TOOL INTEGRATION

A correctly connected WhatsApp channel should still reach the same Prucê and same toolset.

Concept:

WhatsApp
→ Hermes
→ Prucê
→ Gmail/Calendar/state/tools

WhatsApp itself does not inherently prevent Calendar/Gmail use.

The current blockers are deployment/state isolation and Google auth, not the WhatsApp message format.

---

# 10. WHATSAPP / MULTIUSER

Hermes upstream supports WhatsApp.

Plow currently does not offer the same native WhatsApp distribution path as Plow Chat/iMessage.

Daniel explained that a WhatsApp deployment can be used, but many users speaking to one deployment still count as one installation for hackathon purposes.

Important distinction:

One WhatsApp number can technically serve many users WITHOUT mixing context IF the backend is multi-tenant.

Example:

sender A
→ profile/state A

sender B
→ profile/state B

However Prucê’s current canonical state is fundamentally single-user per deployment.

Current dangerous architecture:

many users
→ one deployment
→ one state.json

This risks context leakage/mixing.

Do NOT expose one existing Prucê instance publicly to many users without user-scoped state.

Correct simple architecture today:

user A
→ deployment A
→ state A
→ integrations A
→ install_id A

user B
→ deployment B
→ state B
→ integrations B
→ install_id B

A future architecture could use:

one public WhatsApp number
→ router by sender identity
→ isolated deployment/profile per user

but that is more infrastructure.

Do not build a full multi-tenant router during the hackathon unless absolutely required.

---

# 11. ONE CLICK DEPLOY

Prucê is currently:

- Agent Index ID: `pruce`
- WIP requirement satisfied
- VERIFIED

One Click Deploy was NOT yet enabled at the latest known state.

Daniel asked Vinicius to message in Discord to enable/resolve One Click Deploy.

Critical questions for Plow:

1. Does each One Click user receive:
   - isolated deployment
   - isolated persistent volume
   - unique install_id

2. Can a One Click deployment use a channel other than Plow Chat?

3. Can Hermes native WhatsApp be attached to that deployment?

4. What is the intended Google path for users without Mac/Latch?

Do not assume answers.

---

# 12. AGENT INDEX

Agent identity:

pruce

Never:
- mint a new agent accidentally
- reset Agent Index identity
- delete Agent Index state blindly
- expose install IDs/reporting credentials
- expose `.agent-index.json`
- expose `.env`

Agent Index client pin has remained:

87901f8b182a8a7c65ee3dd7267f8f835ee2a545

Demo metadata currently includes:
- public image
- YouTube video
- HTTPS install URL

WIP was successfully removed.

Verification was successfully obtained.

Agent is verified.

---

# 13. DEMO / BRAND

Brand name:

Prucê

Portuguese wordplay:
“pro cê” / “para você”

Brand direction:
- black and white
- retro/vintage cartoon mascot
- old-school illustrated advertising feel
- friendly, memorable, physical-campus-friendly
- works for stickers/posters/avatar

Mascot concept:
a cheerful, slightly mischievous “faz-tudo” character who is always resolving things.

Good phrases:

“Joga pro Prucê.”

“Deixa comigo.”

“Tá esquecendo alguma coisa?”

“Você tem coisa melhor pra fazer.”

Global tagline:

Less to remember. More actually handled.

Avoid positioning the brand literally as a “slave” even though a humorous “does things for you” concept was discussed; historical/social baggage would distract from the product.

---

# 14. UFMG DISTRIBUTION STRATEGY

UFMG is the main beachhead.

Reason:
- concentrated community
- Vinicius has direct access
- physical distribution is possible
- strong repeated student pain
- WhatsApp-heavy audience

Marketing message should NOT be technical.

Bad:

“AI agent with canonical state and source map.”

Good:

“Tá esquecendo prazo, e-mail, reunião ou burocracia? Joga pro Prucê.”

Potential first-use prompt:

“Tem alguma coisa importante que eu tô deixando passar?”

Then:

“O que eu deveria resolver primeiro?”

The desired “aha” moment is:

Prucê discovers something useful the user did NOT explicitly mention.

---

# 15. UFMG-SPECIFIC FUTURE FEATURES

Do NOT make these blockers before distribution.

Potential public-data capabilities that do NOT require Mac:

- RU menu
- academic calendar
- university public deadlines/notices
- buildings/rooms
- campus information
- transportation/public info
- UFMGo academic building/location data

Important insight:

Public UFMG capabilities can work without Mac/Latch.

Mac is mainly a limitation for PRIVATE user sources such as:
- Gmail
- Calendar

Potential Moodle integration:

Moodle supports web services/APIs in general.

UFMG’s exact supported third-party auth/token path has NOT been confirmed.

Do not implement Moodle before verifying auth/access.

Architecturally, Moodle should be another SOURCE ADAPTER feeding the existing discovery/triage model.

Do not put Moodle-specific fields into canonical task schema.

---

# 16. LIFE ASSISTANT REFERENCE

Reference repo:

~/Developer/pruce-hackathon/life-assistant-hermes-agent

Public:
https://github.com/plow-pbc/life-assistant-hermes-agent

Important historical issue:

The first comparison against Life Assistant was made against an OLD local commit:

915d297a2a7e7adbb110e000450e30938e6c100f

Later `origin/main` was updated to:

2b5c989c3094933d5cde076168ee7f2dd306afb3

There were 41 commits between them.

Current Life Assistant introduced relevant changes such as:
- newer base
- newer hermes-plugin-plow
- `life_tools`
- `ld-priorities`
- improved first boot
- calendar nudge changes
- credential/runtime changes

Do not rely on the old audit as perfect current parity.

However the durable conclusions remained:

Life Assistant strengths:
- deterministic onboarding
- stored configuration
- narrower specialized skills
- deterministic recurring experiences
- proactivity/background behavior

Prucê strengths:
- canonical outcome state
- temporal grounding
- evidence-backed transitions
- waiting_for_third_party
- action != outcome
- safer read-only policy

Do not copy Life Assistant wholesale.

---

# 17. CURRENT BASE / PLUGIN

The latest local Prucê work updated its base toward current Life Assistant parity.

Before:

plow-hermes-agent base:
8710797b6409c77df560c6198407765d138ea617

hermes-plugin-plow:
3517dab6f79df7b09bd9ca4de567775c1bec1d56

Latest local update:

plow-hermes-agent base:
80ef5024eb4b770e727a618a9b55421c73da6228

hermes-plugin-plow:
8e055e059ce774b455869d915525e63933db18fe

Agent Index client unchanged.

The newer base removed the old `.host` credential-promotion behavior; Compose was adjusted to use the credentials env file directly.

IMPORTANT:
VERIFY current repo HEAD and running container before assuming the upgrade is active.

---

# 18. CURRENT PERFORMANCE DATA

Real measured Prucê timings before/around latest routing/base work:

Simple conversation:
~9–10s

State:
~14s in earlier measurement

Student Radar:
~25s

What Now:
~10s

Targeted Calendar:
~63s

Life Assistant targeted Calendar comparison:
~36s

Earlier deep latency trace included a Gmail-heavy turn around:
~77s

Known finding:

Local state is NOT the main bottleneck.

Measured local canonical-state/source reads are roughly ~100ms.

Large latency comes mainly from:
- model passes
- remote MCP calls
- Latch
- Google
- provider instability/retries
- sequential remote/model rounds

A targeted Calendar fast-path contract was added:

Calendar intent
→ one bounded Calendar read
→ final answer

No:
- task state
- source map
- Life Scan
- Gmail
- repeated discovery

unless genuinely required.

Expected path:
2 model passes + 1 external tool round

Latest user observation after changes:
performance remained broadly similar.

Do NOT spend large Codex budget continuing blind latency optimization.

Only investigate further if:
- users are blocked
- logs reveal a concrete extra round/retry
- Daniel reports a serious performance issue

---

# 19. CURRENT TEST STATUS

Latest Codex run reported:

Full local suite:
129 passed, 0 failed

Isolated current-files image suite:
142 passed, 0 failed

Structured onboarding:
passed

Student Radar:
passed

What Now:
passed

Follow-through:
passed

Targeted Calendar contract:
passed

New-base image build:
passed

Persona/skills/plugin compatibility:
passed

Agent Index client self-check:
passed

Compose validation:
passed

git diff --check:
passed

Live Google/Latch latency was NOT proven faster.

---

# 20. EXTERNAL WRITE POLICY

For the hackathon release, consequential external writes remain intentionally restricted.

Prucê can:
- inspect
- read
- search
- compare
- discover
- prioritize
- prepare drafts
- prepare actions
- maintain internal state
- track outcomes

Prucê should NOT currently claim it can autonomously finalize consequential external actions such as:
- sending emails
- modifying Calendar
- purchasing
- submitting forms
- cancelling subscriptions
- irreversible confirmations

User-facing language:

> “Consigo deixar tudo pronto para você, mas o envio final ainda fica com você.”

Do not expose operation-journal internals unless asked.

---

# 21. OPERATION JOURNAL

There is an operation journal/reliability layer.

Operation states include:

prepared
in_flight
succeeded
failed_safe
ambiguous

Idempotency uses intent/action/target/payload hashing.

`ambiguous` and `in_flight` should block blind automatic retries.

Receipt of an operation is NOT equivalent to closing the user’s open loop.

Detailed operation/retry instructions were moved out of the common task hot path into a colder:

pruce-operations

skill.

Do not remove reliability history or `operations.py`.

---

# 22. PERFORMANCE / PROMPT CLEANUP

A recent cleanup reduced common hot-path instructions.

Reported reduction:

persona + task hot path:
5,039 → 4,516 words

~10.4% reduction

task skill:
~14.3% reduction

Do not reinsert detailed operation/retry instructions into ordinary task routing.

---

# 23. CURRENT USER ACQUISITION SITUATION

As of 2026-09-16:

Prucê:
- Verified
- WIP cleared
- appears in Agent Index
- early user count still small

A screenshot around this time showed:
- Prucê: 2 users
- success installs around 40%

Treat this only as a snapshot; numbers change.

Hackathon strategy is now heavily focused on:

REAL USAGE

not continued engineering polish.

Do not waste days optimizing small technical details while distribution is stalled.

---

# 24. DISTRIBUTION PLAN

Primary:

1. UFMG personal network
2. WhatsApp groups
3. direct in-person demos
4. physical posters
5. referrals
6. social posts/reels
7. broader online communities later

First users should be guided toward the strongest experience:

“Tem alguma coisa importante que eu tô deixando passar?”

then:

“O que eu deveria resolver primeiro?”

Retention should eventually include opt-in proactive experiences.

---

# 25. PROACTIVITY / CRON

A high-value future/near-term retention mechanism is opt-in proactive messaging.

Potential:

MORNING RADAR

Every weekday morning:
- inspect useful relevant context
- message only if something deserves attention
- otherwise stay silent

Concept:

“Bom dia. Duas coisas merecem sua atenção hoje…”

Do not spam users.

Do not build cron solely to manufacture token usage.

Use genuine opt-in utility.

The current Hermes base supports scheduled/cron behavior, but verify the exact deployed configuration before assuming delivery works.

---

# 26. FAMILY / GENERAL USERS

Vinicius wants family members to use Prucê as real testers.

This is useful.

Do NOT make the product student-only.

The same engine should work for parents:

Possible use cases:
- appointments
- work commitments
- responses
- documents
- subscriptions
- bureaucracy
- household/admin
- follow-through

Student-specific functionality should activate from profile/context.

---

# 27. CODEX BUDGET / WORKING STYLE

The previous account’s weekly Codex budget became extremely constrained.

The new account/session exists to provide fresh capacity.

Do NOT waste it.

Preferred behavior:

- inspect before editing
- group related work into one well-scoped prompt
- avoid repeated broad audits
- avoid speculative refactors
- use evidence from real users
- solve blockers
- preserve known-good architecture

For Codex prompts always think in terms of:

MODEL
EFFORT
CHAT
REASON

Historical preferred default:
GPT-5.6 Sol Medium

Low:
simple inspection

High:
only genuine hard blocker

Do not use High casually.

---

# 28. VERY IMPORTANT SAFETY / DO-NOT-BREAK RULES

NEVER:

docker compose down -v

Do not:
- delete Prucê persistent volume
- wipe `/var/lib/hermes`
- reset canonical state casually
- reset Agent Index identity
- mint a new agent accidentally
- expose `.env`
- expose credentials
- expose Agent Index reporting key
- expose install ID
- expose `.agent-index.json`
- mix multiple users in one canonical state
- turn conversational memory into current-state authority
- mark action as outcome completion
- enable broad external writes without a reliability decision

Before potentially destructive operations:
STOP AND REPORT.

---

# 29. CURRENT SAFE BUILD PATTERN

Historically safe commands:

cd ~/Developer/pruce-hackathon/pruce-hermes-agent

docker compose config --quiet

docker compose build agent

docker compose up -d --no-deps --force-recreate agent

Do NOT use:
docker compose down -v

After persona/skill/base changes:
start a fresh Hermes session with:

/new

---

# 30. NEXT PRODUCT QUESTIONS

The most important unresolved product/engineering questions are:

1. One Click Deploy enablement
2. WhatsApp POC
3. deployment isolation per user
4. Google for non-Mac users
5. proactive retention
6. UFMG public-data integrations
7. whether onboarding should become general profile specialization rather than primarily student profile
8. distribution/usage feedback

Do NOT reopen already-solved reliability architecture unless real evidence requires it.

---

# 31. CURRENT HIGH-LEVEL PRIORITY

The project has moved from:

BUILD EVERYTHING

to:

GET REAL PEOPLE USING A GOOD-ENOUGH PRODUCT

The main resource constraint is now time and distribution, not feature count.

Optimize for:

INSTALL
→ FIRST VALUE
→ REPEAT USE
→ RETENTION

not:

MORE FEATURES
→ MORE PROMPTS
→ MORE INTERNAL COMPLEXITY

---

# 32. HOW THE NEW CODEX SESSION SHOULD START

Before making any changes:

1. Read this document.
2. Inspect:
   - git status
   - git log --oneline -10
   - current Dockerfile
   - compose.yml
   - runtime/persona.md
   - skills/
3. Confirm current base/plugin pins.
4. Confirm whether working tree has uncommitted changes.
5. Treat current code as source of truth.
6. Return a concise understanding of:
   - architecture
   - product
   - current constraints
   - current priorities

Do NOT edit on the first pass unless explicitly requested.

If this handoff conflicts with current implementation:
REPORT THE DIFFERENCE.
Do not silently change the repository to match the handoff.