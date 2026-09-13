"""Prucê's small local record. Standard library only; no network or scheduler."""
import argparse
import copy
from datetime import date, datetime, time, timedelta, timezone as datetime_timezone
import fcntl
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import unicodedata
import uuid
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


STATUSES = {
    "needs_action", "in_progress", "waiting_for_user",
    "waiting_for_third_party", "completed",
}
EVIDENCE_STATES = {"completed", "waiting_for_third_party"}
COMPLETED_NEXT_STEP = "Nenhuma ação pendente."
DEFAULT_PATH = Path(os.environ.get("HERMES_HOME", "/var/lib/hermes")) / "pruce/state.json"
TEMPORAL_KINDS = {"datetime", "date", "day_part", "date_range", "unresolved"}
TRUSTED_CAPTURE_BASES = {"original_message_timestamp", "live_runtime_clock_at_capture"}
LEGACY_CAPTURE_BASES = {"message_timestamp", "runtime_clock"}
CAPTURE_BASES = TRUSTED_CAPTURE_BASES | LEGACY_CAPTURE_BASES | {"unknown"}
DAY_PARTS = {"morning", "afternoon", "evening", "night"}
WEEKDAYS = {
    "segunda": 0, "segunda-feira": 0, "terca": 1, "terca-feira": 1,
    "quarta": 2, "quarta-feira": 2, "quinta": 3, "quinta-feira": 3,
    "sexta": 4, "sexta-feira": 4, "sabado": 5, "domingo": 6,
}


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


def parse_aware_datetime(value, name):
    text(value, name, 64)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"invalid {name}") from error
    require(parsed.tzinfo is not None and parsed.utcoffset() is not None,
            f"{name} must include a UTC offset")
    return parsed


def parse_date(value, name):
    text(value, name, 10)
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"invalid {name}") from error


def timezone(value):
    text(value, "timezone", 100)
    try:
        return ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as error:
        raise ValueError("invalid timezone") from error


def live_utc_now():
    """Read the clock inside normalization so a model cannot reuse an old now."""
    return datetime.now(datetime_timezone.utc)


def validate_evidence(evidence):
    if evidence is not None:
        keys(evidence, {"kind", "detail"}, {"kind", "detail"})
        require(evidence["kind"] in ("tool_result", "user_confirmation"),
                "invalid evidence kind")
        text(evidence["detail"], "evidence detail")


def validate_temporal(temporal):
    if temporal is None:
        return
    fields = {"raw", "captured_at", "capture_basis", "timezone", "kind",
              "value", "reason", "source", "evidence"}
    keys(temporal, fields, fields)
    text(temporal["raw"], "temporal raw", 300)
    require(temporal["capture_basis"] in CAPTURE_BASES, "invalid capture basis")
    text(temporal["source"], "temporal source", 100)
    require(temporal["kind"] in TEMPORAL_KINDS, "invalid temporal kind")
    if temporal["captured_at"] is None:
        require(temporal["capture_basis"] == "unknown",
                "missing captured_at requires unknown capture basis")
    else:
        parse_aware_datetime(temporal["captured_at"], "captured_at")
        require(temporal["capture_basis"] != "unknown",
                "captured_at requires a known capture basis")
    if temporal["timezone"] is not None:
        timezone(temporal["timezone"])
    kind = temporal["kind"]
    value = temporal["value"]
    if kind == "unresolved":
        require(value is None, "unresolved temporal value must be null")
        text(temporal["reason"], "temporal reason", 300)
    else:
        require(temporal["captured_at"] is not None and temporal["timezone"] is not None,
                "resolved temporal values require captured_at and timezone")
        require(temporal["reason"] is None, "resolved temporal reason must be null")
        if kind == "datetime":
            instant = parse_aware_datetime(value, "temporal datetime")
            require(instant.utcoffset() == instant.astimezone(timezone(temporal["timezone"])).utcoffset(),
                    "temporal datetime offset disagrees with timezone")
        elif kind == "date":
            parse_date(value, "temporal date")
        elif kind == "day_part":
            keys(value, {"date", "part"}, {"date", "part"})
            parse_date(value["date"], "day-part date")
            require(value["part"] in DAY_PARTS, "invalid day part")
        elif kind == "date_range":
            keys(value, {"start", "end"}, {"start", "end"})
            start = parse_date(value["start"], "range start")
            end = parse_date(value["end"], "range end")
            require(start <= end, "invalid temporal range")
    validate_evidence(temporal["evidence"])


def validate_temporal_write(temporal):
    validate_temporal(temporal)
    if temporal is not None:
        require(temporal["capture_basis"] in TRUSTED_CAPTURE_BASES
                or (temporal["kind"] == "unresolved"
                    and temporal["capture_basis"] == "unknown"),
                "new temporal writes require verifiable anchor provenance")


def validate_task(task):
    required = {"id", "title", "status", "next_step", "due", "evidence"}
    keys(task, required | {"temporal"}, required)
    text(task["id"], "id", 64)
    text(task["title"], "title", 300)
    text(task["next_step"], "next_step")
    require(isinstance(task["status"], str) and task["status"] in STATUSES, "invalid status")
    if task["due"] is not None:
        text(task["due"], "due", 300)
    evidence = task["evidence"]
    validate_evidence(evidence)
    validate_temporal(task.get("temporal"))
    if task.get("temporal") is not None:
        require(task["due"] == task["temporal"]["raw"],
                "due must preserve temporal raw text")
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


def folded(value):
    return "".join(character for character in unicodedata.normalize("NFKD", value.casefold())
                   if not unicodedata.combining(character))


def looks_relative(value):
    value = folded(value)
    terms = ("hoje", "amanha", "ontem", "essa semana", "esta semana",
             "daqui a", *WEEKDAYS.keys())
    return (any(re.search(rf"\b{re.escape(term)}\b", value) for term in terms)
            or bool(re.search(r"\bem\s+\d+\s+dias?\b", value)))


def temporal_record(raw, captured_at, capture_basis, timezone_name, kind,
                    value, reason, source, evidence):
    result = {
        "raw": raw, "captured_at": captured_at, "capture_basis": capture_basis,
        "timezone": timezone_name, "kind": kind, "value": value,
        "reason": reason, "source": source, "evidence": evidence,
    }
    validate_temporal(result)
    return result


def normalize_temporal(data):
    fields = {"raw", "captured_at", "capture_basis", "timezone", "source", "evidence"}
    keys(data, fields, {"raw", "capture_basis", "timezone", "source"})
    raw = data["raw"]
    text(raw, "temporal raw", 300)
    source = data["source"]
    text(source, "temporal source", 100)
    evidence = data.get("evidence")
    validate_evidence(evidence)
    capture_basis = data["capture_basis"]
    timezone_name = data["timezone"]
    if capture_basis == "live_runtime_clock_at_capture":
        require("captured_at" not in data,
                "live runtime capture reads its own clock; do not supply captured_at")
        captured = live_utc_now()
        captured_raw = (captured.astimezone(timezone(timezone_name)).isoformat()
                        if timezone_name is not None else captured.isoformat())
    else:
        require(capture_basis == "original_message_timestamp",
                "normalization requires verifiable anchor provenance")
        require("captured_at" in data,
                "original message provenance requires captured_at from the event")
        captured_raw = data["captured_at"]
        captured = parse_aware_datetime(captured_raw, "captured_at")
    if timezone_name is None:
        return temporal_record(raw, captured_raw, capture_basis, None, "unresolved", None,
                               "timezone_unknown", source, evidence)
    zone = timezone(timezone_name)
    local = captured.astimezone(zone)
    phrase = folded(raw)
    clock = re.search(r"\b(?:as)\s*(\d{1,2})(?::(\d{2}))?\s*h?\b", phrase)
    calendar_date = re.search(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{4}))?\b", phrase)
    if calendar_date:
        day, month = int(calendar_date.group(1)), int(calendar_date.group(2))
        explicit_year = calendar_date.group(3)
        year = int(explicit_year) if explicit_year else local.year
        try:
            target = date(year, month, day)
        except ValueError as error:
            raise ValueError("invalid deadline date") from error
        if explicit_year is None and target < local.date():
            return temporal_record(raw, captured_raw, capture_basis, timezone_name,
                                   "unresolved", None, "year_ambiguous", source, evidence)
        if clock:
            hour, minute = int(clock.group(1)), int(clock.group(2) or 0)
            require(0 <= hour <= 23 and 0 <= minute <= 59, "invalid deadline time")
            value = datetime.combine(target, time(hour, minute), zone).isoformat()
            return temporal_record(raw, captured_raw, capture_basis, timezone_name,
                                   "datetime", value, None, source, evidence)
        if re.search(r"\b(?:a|de) noite\b", phrase):
            value = {"date": target.isoformat(), "part": "night"}
            return temporal_record(raw, captured_raw, capture_basis, timezone_name,
                                   "day_part", value, None, source, evidence)
        return temporal_record(raw, captured_raw, capture_basis, timezone_name,
                               "date", target.isoformat(), None, source, evidence)
    target = None
    relative_days = re.search(r"\b(?:daqui a|em)\s+(\d+)\s+dias?\b", phrase)
    if relative_days:
        target = local.date() + timedelta(days=int(relative_days.group(1)))
    elif re.search(r"\bamanha\b", phrase):
        target = local.date() + timedelta(days=1)
    elif re.search(r"\bhoje\b", phrase):
        target = local.date()
    elif re.search(r"\bontem\b", phrase):
        target = local.date() - timedelta(days=1)
    if target is not None:
        if clock:
            hour, minute = int(clock.group(1)), int(clock.group(2) or 0)
            require(0 <= hour <= 23 and 0 <= minute <= 59, "invalid deadline time")
            value = datetime.combine(target, time(hour, minute), zone).isoformat()
            return temporal_record(raw, captured_raw, capture_basis, timezone_name,
                                   "datetime", value, None, source, evidence)
        if re.search(r"\b(?:a|de) noite\b", phrase):
            value = {"date": target.isoformat(), "part": "night"}
            return temporal_record(raw, captured_raw, capture_basis, timezone_name,
                                   "day_part", value, None, source, evidence)
        return temporal_record(raw, captured_raw, capture_basis, timezone_name,
                               "date", target.isoformat(), None, source, evidence)
    if re.search(r"\b(?:essa|esta) semana\b", phrase):
        start = local.date() - timedelta(days=local.weekday())
        value = {"start": start.isoformat(), "end": (start + timedelta(days=6)).isoformat()}
        return temporal_record(raw, captured_raw, capture_basis, timezone_name,
                               "date_range", value, None, source, evidence)
    for name, weekday in WEEKDAYS.items():
        if re.search(rf"\b{re.escape(name)}\b", phrase):
            delta = (weekday - local.weekday()) % 7
            explicit_next = (re.search(r"\bproxim[oa]\b", phrase)
                             or re.search(r"\bque vem\b", phrase))
            if delta == 0 and not explicit_next:
                return temporal_record(raw, captured_raw, capture_basis, timezone_name,
                                       "unresolved", None, "weekday_same_day_ambiguous",
                                       source, evidence)
            target = local.date() + timedelta(days=delta or 7)
            if re.search(r"\b(?:a|de) noite\b", phrase):
                value = {"date": target.isoformat(), "part": "night"}
                return temporal_record(raw, captured_raw, capture_basis, timezone_name,
                                       "day_part", value, None, source, evidence)
            return temporal_record(raw, captured_raw, capture_basis, timezone_name,
                                   "date", target.isoformat(), None, source, evidence)
    return temporal_record(raw, captured_raw, capture_basis, timezone_name,
                           "unresolved", None, "unsupported_or_ambiguous_expression",
                           source, evidence)


def temporal_identity(temporal):
    if temporal is None or temporal["kind"] == "unresolved":
        return None
    return temporal["kind"], temporal["value"], temporal["timezone"]


def effective_temporal(raw_temporal, raw_due=None):
    validate_temporal(raw_temporal)
    if raw_temporal is None:
        if isinstance(raw_due, str) and looks_relative(raw_due):
            return temporal_record(raw_due, None, "unknown", None, "unresolved", None,
                                   "legacy_relative_without_capture", "legacy", None)
        return None
    if raw_temporal["capture_basis"] in LEGACY_CAPTURE_BASES:
        return temporal_record(
            raw_temporal["raw"], None, "unknown", raw_temporal["timezone"],
            "unresolved", None, "legacy_unverifiable_anchor_provenance",
            raw_temporal["source"], raw_temporal["evidence"],
        )
    return copy.deepcopy(raw_temporal)


def operational_task(task):
    view = copy.deepcopy(task)
    raw_due = view.pop("due")
    raw_temporal = view.pop("temporal", None)
    view["raw_due"] = raw_due
    view["raw_temporal"] = raw_temporal
    view["effective_temporal"] = effective_temporal(raw_temporal, raw_due)
    return view


def operational_state(state, active_only=False):
    view = {"introduced": state["introduced"], "context": state["context"], "tasks": []}
    for task in state["tasks"]:
        if not active_only or task["status"] != "completed":
            view["tasks"].append(operational_task(task))
    return view


def temporal_status(data):
    keys(data, {"temporal", "now"}, {"temporal", "now"})
    temporal = effective_temporal(data["temporal"])
    if temporal is None or temporal["kind"] == "unresolved":
        return {"relation": "unresolved", "effective_temporal": temporal}
    now = parse_aware_datetime(data["now"], "now").astimezone(timezone(temporal["timezone"]))
    kind, value = temporal["kind"], temporal["value"]
    if kind == "datetime":
        instant = parse_aware_datetime(value, "temporal datetime")
        relation = "past" if instant < now else "future"
    elif kind in {"date", "day_part"}:
        target = parse_date(value if kind == "date" else value["date"], "temporal date")
        relation = "past" if target < now.date() else "future" if target > now.date() else "today"
    else:
        start, end = parse_date(value["start"], "range start"), parse_date(value["end"], "range end")
        relation = "future" if now.date() < start else "past" if now.date() > end else "current"
    return {"relation": relation, "effective_temporal": temporal}


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
        keys(data, {"title", "next_step", "status", "due", "temporal"}, {"title", "next_step"})
        if "temporal" in data and data["temporal"] is not None:
            validate_temporal_write(data["temporal"])
            if "due" in data:
                require(data["due"] == data["temporal"]["raw"],
                        "due must preserve temporal raw text")
            data = {**data, "due": data["temporal"]["raw"]}
        elif isinstance(data.get("due"), str) and looks_relative(data["due"]):
            raise ValueError("relative due requires anchored temporal metadata")
        task = {"id": uuid.uuid4().hex[:12], "status": "needs_action", "due": None,
                "evidence": None, "temporal": None, **data}
        validate_task(task)
        require(not any(t["title"].strip().casefold() == task["title"].strip().casefold()
                        and t["status"] != "completed" for t in state["tasks"]),
                "an open task has this title; read and update its id")
        state["tasks"].append(task)
        result = task
    else:
        keys(data, {"id", "title", "status", "next_step", "due", "evidence", "temporal"}, {"id"})
        require(len(data) > 1, "empty update")
        task = next((t for t in state["tasks"] if t["id"] == data["id"]), None)
        require(task is not None, "unknown task id")
        if "temporal" in data and data["temporal"] is not None:
            validate_temporal_write(data["temporal"])
            if "due" in data:
                require(data["due"] == data["temporal"]["raw"],
                        "due must preserve temporal raw text")
            data = {**data, "due": data["temporal"]["raw"]}
            old_identity = temporal_identity(task.get("temporal"))
            new_identity = temporal_identity(data["temporal"])
            if old_identity is not None and new_identity is not None and old_identity != new_identity:
                require(data["temporal"]["evidence"] is not None,
                        "changed resolved deadline requires reconciliation evidence")
        elif isinstance(data.get("due"), str) and looks_relative(data["due"]):
            raise ValueError("relative due requires anchored temporal metadata")
        elif data.get("temporal", "not-present") is None and "due" not in data \
                and task.get("temporal") is not None and looks_relative(task.get("due", "")):
            raise ValueError("clearing temporal metadata also requires clearing due")
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
    if command == "normalize-time":
        return normalize_temporal(data)
    if command == "time-status":
        return temporal_status(data)
    if command in {"read", "active"}:
        state = read(path)  # Read-only: keep closed records intact on disk.
        return operational_state(state, active_only=command == "active")
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
    parser.add_argument("command", choices=("read", "active", "profile", "create", "update",
                                             "normalize-time", "time-status"))
    parser.add_argument("--state", type=Path, default=DEFAULT_PATH,
                        help="override the state file for isolated local tests")
    args = parser.parse_args()
    try:
        data = None if args.command in {"read", "active"} else parse(sys.stdin.read())
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
