# PRUCÊ — CURRENT PRIORITIES

Date: 2026-09-16

## P0 — HACKATHON USAGE / DISTRIBUTION

Prucê is:
- out of WIP
- Verified
- functional
- early in user acquisition

The hackathon now depends heavily on real usage.

Do not spend most of the remaining time polishing architecture.

Primary goal:

INSTALL
→ FIRST VALUE
→ REPEAT USE

---

## P1 — ONE CLICK DEPLOY

Still needs resolution/enabling with Daniel/Plow.

Questions:

- Does each user get isolated deployment?
- isolated volume?
- unique install_id?
- can the deployment use a non-Plow-Chat channel?
- can Hermes WhatsApp attach to it?

---

## P1 — WHATSAPP POC

WhatsApp is strategically critical in Brazil.

Goal for first POC:

WhatsApp
→ Hermes
→ Prucê
→ existing Gmail/Calendar through Vinicius’s Mac/Latch
→ response in WhatsApp

Do NOT build multi-tenant public WhatsApp yet.

First prove one-user path.

---

## P1 — RETENTION / PROACTIVITY

Test whether Prucê can proactively message using cron/scheduled behavior.

Potential first experience:

Morning Radar

Opt-in only.

Send only when useful.

Do not create artificial usage/spam.

---

## P1 — REAL USER TESTING

Test with:
- Vinicius
- family
- UFMG friends
- classmates

Collect:
- latency
- misunderstood intent
- bad source choice
- useful discoveries
- repeat usage
- onboarding friction

Fix only problems that materially hurt usage.

---

## P2 — GENERAL PROFILE SPECIALIZATION

Prucê should remain a general life assistant.

Student Life + Early Adulting is the main beachhead, not the entire product.

Future profile model should adapt to:

- study
- work
- family
- household
- adulting

Do not force university/course questions onto non-students.

---

## P2 — UFMG PUBLIC INTEGRATIONS

Useful even without Mac:

- RU menu
- public academic calendar
- buildings/rooms
- university information
- campus information

These can provide UFMG value without private Google integration.

---

## P3 — GOOGLE WITHOUT MAC

Current owner Gmail/Calendar path depends on Mac/Latch.

A proper non-Mac solution likely requires:
- per-user Google OAuth
- token storage
- refresh
- isolation
- read-only scopes

First ask Plow whether a supported path already exists.

Do not build this casually during the hackathon.

---

## P3 — MOODLE

Potentially valuable for students.

Do not implement until:
- UFMG auth/token access is understood
- user distribution justifies it

Moodle should be another source adapter, not a new task model.

---

## CURRENT PERFORMANCE SNAPSHOT

Approximate real timings:

Simple:
~10s

Student Radar:
~25s

What Now:
~10s

Targeted Calendar:
~63s

Do not spend major development budget blindly trying to reduce Calendar latency further.

Investigate only with concrete logs/evidence or user-blocking impact.

---

## DO NOT DO

- docker compose down -v
- reset Agent Index identity
- wipe persistent state
- mix users into one state.json
- enable broad external writes
- create broad new architecture without user evidence
- run another giant comparison/audit unless materially necessary