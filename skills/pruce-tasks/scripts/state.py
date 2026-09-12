"""Prucê's small local record. Standard library only; no network or scheduler."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import sys
import tempfile
import uuid


STATUSES = {
    "needs_action", "in_progress", "waiting_for_user",
    "waiting_for_third_party", "completed",
}
EVIDENCE_STATES = {"completed", "waiting_for_third_party"}
COMPLETED_NEXT_STEP = "Nenhuma ação pendente."
DEFAULT_PATH = Path(os.environ.get("HERMES_HOME", "/var/lib/hermes")) / "pruce/state.json"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def text(value, name, limit=2000, empty=False):
    require(isinstance(value, str), f"{name} must be text")
    require(len(value) <= limit and (empty or bool(value.strip())), f"invalid {name}")


def keys(value, allowed, required=()):
    require(isinstance(value, dict), "expected a JSON object")
    require(not (value.keys() - allowed), "unknown fields")
    require(set(required) <= value.keys(), "missing required fields")


def validate_task(task):
    fields = {"id", "title", "status", "next_step", "due", "evidence"}
    keys(task, fields, fields)
    text(task["id"], "id", 64)
    text(task["title"], "title", 300)
    text(task["next_step"], "next_step")
    require(isinstance(task["status"], str) and task["status"] in STATUSES, "invalid status")
    if task["due"] is not None:
        text(task["due"], "due", 300)
    evidence = task["evidence"]
    if evidence is not None:
        keys(evidence, {"kind", "detail"}, {"kind", "detail"})
        require(evidence["kind"] in ("tool_result", "user_confirmation"), "invalid evidence kind")
        text(evidence["detail"], "evidence detail")
    require(task["status"] not in EVIDENCE_STATES or evidence is not None,
            "this status requires evidence or user confirmation")


def validate(state):
    keys(state, {"introduced", "context", "tasks"}, {"introduced", "context", "tasks"})
    require(type(state["introduced"]) is bool, "introduced must be boolean")
    text(state["context"], "context", 4000, empty=True)
    require(isinstance(state["tasks"], list), "tasks must be a list")
    ids = set()
    for task in state["tasks"]:
        validate_task(task)
        require(task["id"] not in ids, "duplicate task id")
        ids.add(task["id"])


def strict_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate JSON key")
        result[key] = value
    return result


def reject_constant(_value):
    raise ValueError("non-finite JSON number")


def parse(raw):
    return json.loads(raw, object_pairs_hook=strict_object, parse_constant=reject_constant)


def read(path):
    try:
        state = parse(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        # A dangling symlink is damaged state, not a fresh install.
        require(not path.is_symlink(), "state path is a dangling symlink")
        state = {"introduced": False, "context": "", "tasks": []}
    validate(state)
    return state


def apply(state, command, data):
    if command == "profile":
        keys(data, {"introduced", "context"})
        require(bool(data), "empty update")
        state.update(data)
        result = {"introduced": state["introduced"], "context": state["context"]}
    elif command == "create":
        keys(data, {"title", "next_step", "status", "due"}, {"title", "next_step"})
        task = {"id": uuid.uuid4().hex[:12], "status": "needs_action", "due": None,
                "evidence": None, **data}
        validate_task(task)
        require(not any(t["title"].strip().casefold() == task["title"].strip().casefold()
                        and t["status"] != "completed" for t in state["tasks"]),
                "an open task has this title; read and update its id")
        state["tasks"].append(task)
        result = task
    else:
        keys(data, {"id", "title", "status", "next_step", "due", "evidence"}, {"id"})
        require(len(data) > 1, "empty update")
        task = next((t for t in state["tasks"] if t["id"] == data["id"]), None)
        require(task is not None, "unknown task id")
        target = data.get("status", task["status"])
        changed = target != task["status"]
        if changed and target in EVIDENCE_STATES:
            require(data.get("evidence") is not None, "new status requires fresh evidence")
        if changed:
            task["evidence"] = None
        task.update(data)
        result = task
    # Write-time convention, not a language classifier. Keep legacy records
    # readable so the agent can repair the same ID without a data migration.
    if command != "profile" and result["status"] == "completed":
        require(result["next_step"] == COMPLETED_NEXT_STEP,
                "completed requires next_step 'Nenhuma ação pendente.'; "
                "if awaiting an external response, use waiting_for_third_party")
    validate(state)
    return result


def write(path, state):
    fd, temporary = tempfile.mkstemp(prefix=".state-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            os.fchmod(handle.fileno(), 0o600)
            json.dump(state, handle, ensure_ascii=False, allow_nan=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def run(path, command, data=None):
    path = Path(path)
    if command == "read":
        return read(path)  # Atomic replacement makes reads safe without creating files.
    require(command in {"profile", "create", "update"}, "unknown command")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Lock a separate inode: the state itself is replaced on each write.
    fd = os.open(str(path) + ".lock", os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(fd, "a") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        state = read(path)
        result = apply(state, command, data)
        write(path, state)
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("read", "profile", "create", "update"))
    parser.add_argument("--state", type=Path, default=DEFAULT_PATH,
                        help="override the state file for isolated local tests")
    args = parser.parse_args()
    try:
        data = None if args.command == "read" else parse(sys.stdin.read())
        result = run(args.state, args.command, data)
    except (ValueError, OSError, TypeError) as error:
        # Never echo raw state, user text, command input or credentials on failure.
        message = "invalid JSON" if isinstance(error, json.JSONDecodeError) else (
            "state I/O failed" if isinstance(error, OSError) else str(error))
        print(json.dumps({"ok": False, "error": message}), file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, "result": result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
