---
name: pruce-operations
description: Preserve and reconcile an existing Prucê consequential-operation receipt, or support a future external-write path only after that path is explicitly enabled. Never use for ordinary tasks, student requests, reads, analysis or drafts; the current hackathon release remains read-only.
---

# Consequential operation receipts

Keep this workflow intact for existing history, reconciliation and a future
release with proven enforcement. It does not enable external writes in the
current hackathon release. Do not create an operation merely to read, analyze,
draft or prepare something, and do not execute a consequential external action
even when a write-capable tool is visible. If an earlier operation is already
`in_flight` or `ambiguous`, preserve the retry block and reconcile it through a
read-only authoritative check when possible.

The separate local operation guard is the preserved workflow for prior receipts
and any future path that is explicitly proven safe and enabled. Such a path
would use it before an external action that can send, submit, delete, spend,
book, publish, change an account, or otherwise create a consequential effect.
It is not needed for ordinary read-only consultation or local drafting. The
ledger is separate from open-loop state and does not prove an effect by itself.
It also does not intercept tools: a direct tool call can bypass it. Following
this sequence alone is behavioral until a dispatcher enforces it, which is why
the current product policy keeps external writes disabled.

One operation represents one owner-authorized effect on one exact target.
Choose a stable `intent_id` for that single authorization scope. A retry of the
same intended effect reuses the same `intent_id`; a deliberately new repeat of
identical work needs a new intent ID and fresh owner authority. Never mint a new
intent ID merely because a call timed out or a new session began.

Pass the exact material tool payload to `prepare`, excluding transient
credentials and transport metadata. The script hashes canonical JSON and does
not persist the raw payload. It derives `idempotency_key` from `intent_id`,
action, target and the payload hash; callers cannot choose the key. The stored
authorization is immutable for that intent. This catches payload or target
drift inside the workflow, but cannot verify that the later tool call actually
uses the same payload.

First prepare the operation with authority actually supplied by the owner:

```sh
python3 /var/lib/hermes/skills/pruce-tasks/scripts/operations.py prepare <<'PRUCE_OPERATION_JSON'
{"intent_id":"<task id>:submit:application-42:v1","task_id":"<task id>","action":"Enviar candidatura","target":"Portal da empresa — vaga 42","payload":{"application_id":"42","document_sha256":"<digest of approved document>"},"authorization":{"kind":"user_confirmation","detail":"Usuário confirmou o envio desta candidatura e deste material."}}
PRUCE_OPERATION_JSON
```

Preparing the same intent again returns the existing receipt only if its task,
action, target, payload hash and authorization are unchanged. Inspect the
returned status before acting: `succeeded` means do not repeat it; `in_flight`
after an interruption or `ambiguous` means verify the authoritative service
before any retry; `failed_safe` may be retried only because the recorded result
established that no effect occurred.

Immediately before a future explicitly enabled tool call, change the prepared
receipt to `in_flight`:

```sh
python3 /var/lib/hermes/skills/pruce-tasks/scripts/operations.py begin <<'PRUCE_OPERATION_JSON'
{"id":"<operation id>","payload":{"application_id":"42","document_sha256":"<digest of approved document>"}}
PRUCE_OPERATION_JSON
```

`begin` hashes the material payload again and refuses the transition if it
differs from `prepare`. Use that same payload in the immediately following tool
call. The journal still cannot inspect or force the arguments sent by the tool.

After the call, use `finish` with `succeeded`, `failed_safe` or `ambiguous` and
a `tool_result` grounded in what that attempted call actually returned. Timeout,
connection loss, partial execution, an unclear response or confirmation of the
wrong target is `ambiguous`, never safe failure and never success. If a process
dies while `in_flight`, treat that receipt as ambiguous on recovery. `begin`
refuses to replay `in_flight`, `ambiguous` or `succeeded` operations.

Use `reconcile` only after an authoritative lookup or explicit owner
confirmation establishes `succeeded` or `failed_safe`; a generic result from
the original attempt is not reconciliation. If the provider accepts an
idempotency token, pass the derived key returned by `prepare` on every allowed
attempt. After confirmed success, use the operation result as evidence for the
specific task transition it supports, then separately decide whether the real
open-loop outcome is complete or merely waiting for a third party.

The default ledger is `/var/lib/hermes/pruce/operations.json`. Its commands are
`read`, `prepare`, `begin`, `finish` and `reconcile`; all writes use the same
private, locked, validated and atomic-file pattern as task state. The script
validates transitions, not the truth of authorization or external results.
