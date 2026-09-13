"""Prucê's small source and coverage map. Standard library only."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import sys
import tempfile


ACCESS = {"connected", "manual", "unavailable"}
DECISIONS = {"accepted", "declined"}
DEFAULT_PATH = Path(os.environ.get("HERMES_HOME", "/var/lib/hermes")) / "pruce/sources.json"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def text(value, name, limit=500):
    require(isinstance(value, str) and bool(value.strip()) and len(value) <= limit,
            f"invalid {name}")


def keys(value, allowed, required=()):
    require(isinstance(value, dict), "expected a JSON object")
    require(not (value.keys() - allowed), "unknown fields")
    require(set(required) <= value.keys(), "missing required fields")


def validate_entry(entry):
    fields = {"area", "source", "access", "last_seen", "offer"}
    keys(entry, fields, fields)
    text(entry["area"], "area", 100)
    text(entry["source"], "source", 200)
    require(isinstance(entry["access"], str) and entry["access"] in ACCESS,
            "invalid access")
    if entry["last_seen"] is not None:
        text(entry["last_seen"], "last_seen", 300)
    if entry["offer"] is not None:
        keys(entry["offer"], {"decision", "context"}, {"decision", "context"})
        require(isinstance(entry["offer"]["decision"], str)
                and entry["offer"]["decision"] in DECISIONS,
                "invalid offer decision")
        text(entry["offer"]["context"], "offer context", 500)


def validate(state):
    keys(state, {"sources"}, {"sources"})
    require(isinstance(state["sources"], list), "sources must be a list")
    identities = set()
    for entry in state["sources"]:
        validate_entry(entry)
        identity = (entry["area"].strip().casefold(), entry["source"].strip().casefold())
        require(identity not in identities, "duplicate source")
        identities.add(identity)


def strict_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate JSON key")
        result[key] = value
    return result


def parse(raw):
    return json.loads(raw, object_pairs_hook=strict_object,
                      parse_constant=lambda _value: require(False, "non-finite JSON number"))


def read(path):
    try:
        state = parse(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        require(not path.is_symlink(), "source map path is a dangling symlink")
        state = {"sources": []}
    validate(state)
    return state


def apply(state, data):
    allowed = {"area", "source", "access", "last_seen", "offer"}
    keys(data, allowed, {"area", "source"})
    identity = (data["area"].strip().casefold(), data["source"].strip().casefold())
    entry = next((item for item in state["sources"]
                  if (item["area"].strip().casefold(), item["source"].strip().casefold())
                  == identity), None)
    if entry is None:
        require("access" in data, "new source requires access")
        entry = {"last_seen": None, "offer": None, **data}
        state["sources"].append(entry)
    else:
        require(len(data) > 2, "empty update")
        entry.update({key: value for key, value in data.items()
                      if key not in {"area", "source"}})
    validate(state)
    return entry


def write(path, state):
    descriptor, temporary = tempfile.mkstemp(prefix=".sources-", dir=path.parent)
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
    require(command == "upsert", "unknown command")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(str(path) + ".lock", os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(descriptor, "a") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        state = read(path)
        result = apply(state, data)
        write(path, state)
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("read", "upsert"))
    parser.add_argument("--state", type=Path, default=DEFAULT_PATH)
    args = parser.parse_args()
    try:
        data = None if args.command == "read" else parse(sys.stdin.read())
        result = run(args.state, args.command, data)
        print(json.dumps({"ok": True, "result": result}, ensure_ascii=False))
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
