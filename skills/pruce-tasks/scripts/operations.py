"""Prucê's local guard for consequential external operations.

This is bookkeeping, not an integration, a tool-call interceptor, or proof that
an external effect happened. When callers use this workflow, it refuses to
silently replay a prepared intent after a success, interruption, or ambiguity.
"""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import uuid


STATUSES = {"prepared", "in_flight", "succeeded", "failed_safe", "ambiguous"}
AUTHORIZATION_KINDS = {"user_instruction", "user_confirmation"}
RESULT_KINDS = {"tool_result", "authoritative_check", "user_confirmation"}
DEFAULT_PATH = (Path(os.environ.get("HERMES_HOME", "/var/lib/hermes"))
                / "pruce/operations.json")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def text(value, name, limit=1000):
    require(isinstance(value, str) and bool(value.strip()) and len(value) <= limit,
            f"invalid {name}")


def keys(value, allowed, required=()):
    require(isinstance(value, dict), "expected a JSON object")
    require(not (value.keys() - allowed), "unknown fields")
    require(set(required) <= value.keys(), "missing required fields")


def parse_aware_datetime(value, name):
    text(value, name, 64)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"invalid {name}") from error
    require(parsed.tzinfo is not None and parsed.utcoffset() is not None,
            f"{name} must include a UTC offset")


def validate_note(value, name, kinds):
    keys(value, {"kind", "detail"}, {"kind", "detail"})
    require(value["kind"] in kinds, f"invalid {name} kind")
    text(value["detail"], f"{name} detail", 1000)


def payload_digest(payload):
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                           separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def operation_key(intent_id, action, target, payload_sha256):
    identity = {"intent_id": intent_id, "action": action, "target": target,
                "payload_sha256": payload_sha256}
    canonical = json.dumps(identity, ensure_ascii=False, sort_keys=True,
                           separators=(",", ":"), allow_nan=False)
    return "op_" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate_operation(operation):
    fields = {"id", "intent_id", "idempotency_key", "task_id", "action", "target",
              "payload_sha256", "status", "authorization", "attempt", "result",
              "created_at", "updated_at"}
    keys(operation, fields, fields)
    text(operation["id"], "operation id", 64)
    text(operation["intent_id"], "intent id", 200)
    text(operation["idempotency_key"], "idempotency key", 200)
    if operation["task_id"] is not None:
        text(operation["task_id"], "task id", 64)
    text(operation["action"], "action", 300)
    text(operation["target"], "target", 500)
    require(isinstance(operation["payload_sha256"], str)
            and len(operation["payload_sha256"]) == 64
            and all(character in "0123456789abcdef"
                    for character in operation["payload_sha256"]),
            "invalid payload digest")
    require(operation["idempotency_key"] == operation_key(
        operation["intent_id"], operation["action"], operation["target"],
        operation["payload_sha256"]), "idempotency key disagrees with operation identity")
    require(operation["status"] in STATUSES, "invalid operation status")
    validate_note(operation["authorization"], "authorization", AUTHORIZATION_KINDS)
    require(type(operation["attempt"]) is int and operation["attempt"] >= 0,
            "invalid attempt")
    parse_aware_datetime(operation["created_at"], "created_at")
    parse_aware_datetime(operation["updated_at"], "updated_at")
    if operation["status"] == "prepared":
        require(operation["attempt"] == 0 and operation["result"] is None,
                "prepared operation cannot have an attempt or result")
    elif operation["status"] == "in_flight":
        require(operation["attempt"] >= 1 and operation["result"] is None,
                "in-flight operation has invalid attempt or result")
    else:
        require(operation["attempt"] >= 1 and operation["result"] is not None,
                "resolved operation requires an attempt and result")
        validate_note(operation["result"], "result", RESULT_KINDS)


def validate(state):
    keys(state, {"operations"}, {"operations"})
    require(isinstance(state["operations"], list), "operations must be a list")
    ids, intent_ids, idempotency_keys = set(), set(), set()
    for operation in state["operations"]:
        validate_operation(operation)
        require(operation["id"] not in ids, "duplicate operation id")
        require(operation["intent_id"] not in intent_ids, "duplicate intent id")
        require(operation["idempotency_key"] not in idempotency_keys,
                "duplicate idempotency key")
        ids.add(operation["id"])
        intent_ids.add(operation["intent_id"])
        idempotency_keys.add(operation["idempotency_key"])


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


def now():
    return datetime.now(timezone.utc).isoformat()


def read(path):
    try:
        state = parse(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        require(not path.is_symlink(), "operation path is a dangling symlink")
        state = {"operations": []}
    validate(state)
    return state


def find_by_id(state, operation_id):
    operation = next((item for item in state["operations"]
                      if item["id"] == operation_id), None)
    require(operation is not None, "unknown operation id")
    return operation


def apply(state, command, data):
    if command == "prepare":
        fields = {"intent_id", "task_id", "action", "target", "payload", "authorization"}
        keys(data, fields, {"intent_id", "action", "target", "payload", "authorization"})
        validate_note(data["authorization"], "authorization", AUTHORIZATION_KINDS)
        for name, limit in (("intent_id", 200), ("action", 300), ("target", 500)):
            text(data[name], name.replace("_", " "), limit)
        if data.get("task_id") is not None:
            text(data["task_id"], "task id", 64)
        digest = payload_digest(data["payload"])
        idempotency_key = operation_key(data["intent_id"], data["action"],
                                        data["target"], digest)
        existing = next((item for item in state["operations"]
                         if item["intent_id"] == data["intent_id"]), None)
        if existing is not None:
            immutable = {"task_id": data.get("task_id"), "action": data["action"],
                         "target": data["target"], "payload_sha256": digest,
                         "authorization": data["authorization"]}
            require(all(existing[key] == value for key, value in immutable.items()),
                    "intent id belongs to a different operation or authorization")
            return existing
        timestamp = now()
        operation = {
            "id": uuid.uuid4().hex[:16],
            "intent_id": data["intent_id"],
            "idempotency_key": idempotency_key,
            "task_id": data.get("task_id"),
            "action": data["action"],
            "target": data["target"],
            "payload_sha256": digest,
            "status": "prepared",
            "authorization": data["authorization"],
            "attempt": 0,
            "result": None,
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        state["operations"].append(operation)
        result = operation
    elif command == "begin":
        keys(data, {"id", "payload"}, {"id", "payload"})
        operation = find_by_id(state, data["id"])
        require(payload_digest(data["payload"]) == operation["payload_sha256"],
                "execution payload differs from the prepared operation")
        if operation["status"] == "succeeded":
            raise ValueError("operation already succeeded; refusing duplicate execution")
        if operation["status"] in {"in_flight", "ambiguous"}:
            raise ValueError("operation outcome must be reconciled before retry")
        require(operation["status"] in {"prepared", "failed_safe"},
                "operation cannot begin from this status")
        operation.update({"status": "in_flight", "attempt": operation["attempt"] + 1,
                          "result": None, "updated_at": now()})
        result = operation
    elif command == "finish":
        keys(data, {"id", "status", "result"}, {"id", "status", "result"})
        operation = find_by_id(state, data["id"])
        require(operation["status"] == "in_flight", "only an in-flight operation can finish")
        require(data["status"] in {"succeeded", "failed_safe", "ambiguous"},
                "invalid finish status")
        validate_note(data["result"], "result", RESULT_KINDS)
        require(data["result"]["kind"] == "tool_result",
                "finish requires the result of the attempted tool call")
        operation.update({"status": data["status"], "result": data["result"],
                          "updated_at": now()})
        result = operation
    else:
        require(command == "reconcile", "unknown command")
        keys(data, {"id", "status", "result"}, {"id", "status", "result"})
        operation = find_by_id(state, data["id"])
        require(operation["status"] in {"in_flight", "ambiguous"},
                "only an uncertain operation can be reconciled")
        require(data["status"] in {"succeeded", "failed_safe"},
                "reconciliation must establish success or safe failure")
        validate_note(data["result"], "result", RESULT_KINDS)
        require(data["result"]["kind"] in {"authoritative_check", "user_confirmation"},
                "reconciliation requires an authoritative check or user confirmation")
        operation.update({"status": data["status"], "result": data["result"],
                          "updated_at": now()})
        result = operation
    validate(state)
    return result


def write(path, state):
    descriptor, temporary = tempfile.mkstemp(prefix=".operations-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
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
        return read(path)
    require(command in {"prepare", "begin", "finish", "reconcile"}, "unknown command")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(str(path) + ".lock", os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(descriptor, "a") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        state = read(path)
        result = apply(state, command, data)
        write(path, state)
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("read", "prepare", "begin", "finish", "reconcile"))
    parser.add_argument("--state", type=Path, default=DEFAULT_PATH)
    args = parser.parse_args()
    try:
        data = None if args.command == "read" else parse(sys.stdin.read())
        result = run(args.state, args.command, data)
    except (ValueError, OSError, TypeError) as error:
        message = "invalid JSON" if isinstance(error, json.JSONDecodeError) else (
            "operation I/O failed" if isinstance(error, OSError) else str(error))
        print(json.dumps({"ok": False, "error": message}), file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, "result": result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
