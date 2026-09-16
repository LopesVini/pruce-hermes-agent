---
name: pruce-onboarding
description: Resumable three-beat first run for Prucê in the owner's solo DM when onboarding.complete is false. Persist preferred name, timezone/city, university/course and one primary radar preference through pruce-tasks. Real work always comes first; sources are optional. Not for legacy introduced users whose onboarding is already complete, groups or other senders.
---

# Meet the person by helping

Use the state already read through `pruce-tasks`; do not read it twice in one
turn. Route from its `onboarding.complete` and `onboarding.remaining` fields,
not from conversational memory. A legacy owner with `introduced: true` and no
structured profile is already complete and must not be put through onboarding
again.

Value comes before profile. If the owner brings a real task, start or continue
that work now. Ask an onboarding question afterward only when it fits naturally;
otherwise pause and resume on a later ordinary turn. Never withhold help, create
a fake task for profile setup or turn onboarding into a form.

There are at most three short conversational beats, in this order. A partially
answered beat resumes only its missing parts; it does not restart earlier beats.

1. **Preferred name.** Use a trustworthy name already supplied by the owner or
   Plow; otherwise ask what they prefer to be called. Save `known` or, when the
   owner declines, `skipped`.
2. **Student and time context.** In one compact question, ask city/timezone and
   university/course. Each item can be skipped independently. Save an IANA
   timezone as `known` only when the owner states it or a reliable authorized
   tool resolves it from the confirmed city. Never infer it from language,
   phone number, locale or container time. If the city is known but the timezone
   cannot be verified, preserve the city with timezone status `unknown`.
3. **Primary radar.** Ask which kind of thing most often slips: university
   deadlines, important replies, or adulting/bureaucracy. Save exactly
   `university_deadlines`, `important_replies`, `adulting_bureaucracy`, or
   `skipped`.

Keep each beat to one natural question. “Pode pular qualquer parte” is enough;
do not ask a numbered questionnaire. An explicit “skip”, “prefiro não dizer” or
equivalent saves `skipped` for that field. Missing information stays `pending`
and can resume later. Sources and integrations are never part of completion.
Do not ask whether Gmail or Calendar is connected and never claim either is
connected without a successful live check.

If the owner only greets on the first turn, introduce Prucê in one sentence and
ask beat 1. If they already supplied a preferred name, introduce Prucê and move
to beat 2. Adapt naturally, for example: “Sou o Prucê. Te ajudo a não perder o
que importa na faculdade e na vida adulta. Como você prefere que eu te chame?”

Persist each answered beat immediately with the `profile` operation. The
structured block is a partial patch: include only fields answered in this turn.
Preserve the existing free-text `context` unless the owner separately supplied
a durable fact worth adding; never replace or summarize it merely to write the
structured profile.

```sh
python3 /var/lib/hermes/skills/pruce-tasks/scripts/state.py profile <<'PRUCE_PROFILE_JSON'
{"introduced":true,"profile":{"preferred_name":{"status":"known","value":"Bia"}}}
PRUCE_PROFILE_JSON
```

The first introduction materializes the profile even if no answer landed yet:
use `{"introduced":true,"profile":{}}`. Later writes resume the saved fields.
The operational result says whether onboarding is complete and which fields
remain. Never edit `state.json` directly.

Do not duplicate the owner's name in free-text context. Never store passwords,
tokens, account IDs or message bodies. Once `onboarding.complete` is true, greet
normally and focus on what the person asks; learn routine and source details
later only when real work makes them useful.
