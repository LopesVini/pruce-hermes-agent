"""Official client against synthetic stores and fake HTTP; never live accounts.

Run in the built image with --network none (see README), or provide a verified
PRUCE_INDEX_CLIENT path. No automatic download or fallback to real credentials.
"""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
CLIENT = Path(os.environ.get("PRUCE_INDEX_CLIENT", "/opt/plow/agent-index-client.py"))
PIN = dict(line.split("=", 1) for line in (ROOT / "vendor/client.pin").read_text().splitlines()
           if line and not line.startswith("#"))
SERVICE = ROOT / "image/s6-overlay/s6-rc.d/agent-index"


class IndexTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.code = CLIENT.read_bytes()
        if hashlib.sha256(cls.code).hexdigest() != PIN["sha256"]:
            raise AssertionError("official client checksum mismatch; refusing to execute")

    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="pruce-index-test-")
        self.addCleanup(temp.cleanup)
        self.home = Path(temp.name)
        env = {"HOME": str(self.home), "HERMES_HOME": str(self.home),
               "PATH": os.defpath, "PLOW_AGENT_TOKEN": "synthetic-plow-token",
               "PLOW_API_BASE": "http://127.0.0.1:9876", "AGENT_ID": "synthetic-pruce"}
        self.addCleanup(patch.stopall)
        patch.dict(os.environ, env, clear=True).start()
        # Fail closed if any unmocked Python network operation is attempted.
        patch.object(socket.socket, "connect", side_effect=AssertionError("network forbidden")).start()
        patch.object(socket, "create_connection", side_effect=AssertionError("network forbidden")).start()
        self.client = types.ModuleType("synthetic_index_client")
        self.client.__file__ = str(CLIENT)
        exec(compile(self.code, str(CLIENT), "exec"), self.client.__dict__)
        self.requests = []
        self.joining = False
        self.client._open_no_redirect = self.fake_http
        # Do not search executables or data outside this synthetic home.
        self.client.from_agentsview = lambda days: {}
        self.addCleanup(self.release_lock)

    def release_lock(self):
        if self.client._STATE_LOCK is not None:
            self.client._STATE_LOCK.close()
            self.client._STATE_LOCK = None

    def fake_http(self, request, timeout=30):
        body = json.loads(request.data) if request.data else None
        auth = request.get_header("Authorization")
        self.requests.append((request.full_url, body, auth))
        if request.full_url.endswith("/v1/auth/index-identity"):
            self.assertEqual(auth, "Bearer synthetic-plow-token")
            result = {"assertion": "synthetic-assertion"}
        elif "/v1/agents?" in request.full_url:
            self.assertEqual(auth, "Bearer synthetic-assertion")
            if self.joining:
                import urllib.error
                raise urllib.error.HTTPError(request.full_url, 409, "already owned", {},
                                             io.BytesIO(b'{"error":"already owned"}'))
            result = {"result": "registered", "url": "https://example.invalid/pruce"}
        elif request.full_url.endswith("/v1/keys"):
            self.assertEqual(auth, "Bearer synthetic-assertion")
            # The CLIENT generates this ID; the fake server only echoes it.
            result = {"key": "aik_" + "a" * 64, "install_id": body["install_id"]}
        elif "/v1/usage?" in request.full_url:
            self.assertEqual(auth, "Bearer aik_" + "a" * 64)
            result = {"ok": True}
        else:
            raise AssertionError("unexpected HTTP endpoint")
        response = io.BytesIO(json.dumps(result).encode())
        response.status = 200
        return response

    def call(self, *args):
        # Model separate client invocations, releasing process-lifetime locks.
        self.release_lock()
        self.client.FAILURES.clear()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            try:
                result = self.client.main(list(args))
            except SystemExit as stop:
                return stop.code
        return 0 if result is None else result

    def register(self):
        self.assertEqual(self.call("--register", "--agent", "synthetic-pruce"), 0)
        return json.loads((self.home / ".agent-index.json").read_text())

    def store(self):
        with contextlib.closing(sqlite3.connect(self.home / "state.db")) as db:
            db.execute("CREATE TABLE session_model_usage (session_id TEXT, model TEXT, "
                       "input_tokens INT, output_tokens INT, cache_read_tokens INT, "
                       "cache_write_tokens INT, first_seen REAL, last_seen REAL)")
            db.execute("INSERT INTO session_model_usage VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                       ("private-session-id", "test-model", 100, 20, 30, 5, time.time(), time.time()))
            db.execute("CREATE TABLE messages (content TEXT)")
            db.execute("INSERT INTO messages VALUES ('PRIVATE_CONVERSATION_SENTINEL')")
            db.commit()
        (self.home / "pruce").mkdir()
        (self.home / "pruce/state.json").write_text('{"context":"PRIVATE_OPEN_LOOP_SENTINEL"}')

    def test_verified_client_is_installed_and_wired(self):
        self.assertEqual(hashlib.sha256(CLIENT.read_bytes()).hexdigest(), PIN["sha256"])
        self.assertFalse(CLIENT.stat().st_mode & 0o022)
        dockerfile = (ROOT / "Dockerfile").read_text()
        self.assertIn("sha256sum /opt/plow/agent-index-client.py", dockerfile)
        self.assertIn('"$got" = "$want"', dockerfile)
        self.assertEqual((SERVICE / "type").read_text().strip(), "longrun")
        self.assertTrue((SERVICE / "dependencies.d/plow-init").exists())
        self.assertTrue((SERVICE.parent / "user/contents.d/agent-index").exists())
        if str(CLIENT) == "/opt/plow/agent-index-client.py":
            installed = Path("/etc/s6-overlay/s6-rc.d/agent-index")
            self.assertEqual((installed / "run").read_bytes(), (SERVICE / "run").read_bytes())
            self.assertTrue(os.access(installed / "run", os.X_OK))
            self.assertEqual(CLIENT.stat().st_uid, 0)
            self.assertEqual((installed / "type").read_text().strip(), "longrun")
            self.assertTrue((installed / "dependencies.d/plow-init").exists())
            self.assertTrue((installed.parent / "user/contents.d/agent-index").exists())

    def test_status_absent_valid_and_corrupt_no_http(self):
        self.assertEqual(self.call("status"), 3)
        self.assertEqual(self.requests, [])
        self.register()
        self.requests.clear()
        self.assertEqual(self.call("status"), 0)
        (self.home / ".agent-index.json").write_text("{broken")
        self.assertEqual(self.call("status"), 2)
        self.assertEqual(self.requests, [])

    def test_install_id_persists_and_independent_install_gets_its_own(self):
        first = self.register()
        self.assertEqual(first["install_id"], self.register()["install_id"])
        self.assertEqual((self.home / ".agent-index.json").stat().st_mode & 0o777, 0o600)
        # Fresh process module, same volume: no identity change.
        self.release_lock()
        exec(compile(self.code, str(CLIENT), "exec"), self.client.__dict__)
        self.client._open_no_redirect = self.fake_http
        self.assertEqual(self.client.load_state()["install_id"], first["install_id"])
        other = self.home / "independent"
        other.mkdir()
        with patch.dict(os.environ, {"HERMES_HOME": str(other)}):
            self.assertEqual(self.call("--register", "--agent", "synthetic-pruce"), 0)
            self.assertNotEqual(self.client.load_state()["install_id"], first["install_id"])

    def test_installer_joins_existing_agent_on_409(self):
        self.joining = True
        self.register()
        self.assertEqual(self.call("status"), 0)
        self.assertTrue(any(url.endswith("/v1/keys") for url, _, _ in self.requests))

    def test_repeated_reports_are_totals_not_duplicate_increments(self):
        self.register()
        self.store()
        self.requests.clear()
        self.assertEqual(self.call(), 0)
        first = self.requests[-1][1]
        self.assertEqual(self.call(), 0)
        self.assertEqual(self.requests[-1][1], first)
        with contextlib.closing(sqlite3.connect(self.home / "state.db")) as db:
            db.execute("UPDATE session_model_usage SET input_tokens=125")
            db.commit()
        self.assertEqual(self.call(), 0)
        row = self.requests[-1][1]["days"][0]["models"][0]
        self.assertEqual(row, {"model": "test-model", "input": 125, "output": 20,
                               "cache_read": 30, "cache_write": 5})
        for _, payload, auth in self.requests:
            self.assertEqual(set(payload), {"days"})
            self.assertNotIn("PRIVATE_", json.dumps(payload))
            self.assertNotIn("private-session-id", json.dumps(payload))
            self.assertNotIn("synthetic-plow-token", auth)

    def test_missing_store_does_not_publish_partial_metrics(self):
        self.register()
        self.requests.clear()
        self.assertNotEqual(self.call(), 0)
        self.assertEqual(self.requests, [])

    def test_dry_run_only_touches_synthetic_ledger(self):
        self.register()
        self.store()
        self.requests.clear()
        self.call("--dry-run")
        self.assertEqual(self.requests, [])
        self.assertTrue((self.home / ".agent-index-state.json").exists())


class ServiceTests(unittest.TestCase):
    def run_service(self, status=0, agent="synthetic-pruce", registration_exit=0, cycles=1):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            envdir = home / "environment"
            envdir.mkdir()
            for key, value in {"AGENT_ID": agent, "PLOW_AGENT_TOKEN": "synthetic-plow-token",
                               "PLOW_API_BASE": "https://example.invalid"}.items():
                (envdir / key).write_text(value)
            record = home / "calls.jsonl"
            stub = home / "client.py"
            stub.write_text(
                "import json, os, sys\n"
                f"with open({str(record)!r}, 'a') as f:\n"
                " f.write(json.dumps({'args':sys.argv[1:], 'env':dict(os.environ)})+'\\n')\n"
                f"sys.exit({status} if sys.argv[1:]==['status'] else "
                f"{registration_exit} if '--register' in sys.argv else 0)\n")
            script = (SERVICE / "run").read_text()
            script = (script.replace("/run/s6/container_environment", str(envdir))
                      .replace("/command/s6-setuidgid hermes", "")
                      .replace("/var/lib/hermes", str(home))
                      .replace("/opt/hermes/.venv/bin/python3", sys.executable)
                      .replace("/opt/plow/agent-index-client.py", str(stub))
                      .replace("exec /bin/sleep 86400", "exit 0")
                      .replace("/bin/sleep 300", f'ticks=$((${{ticks:-0}} + 1)); [ "$ticks" -lt {cycles} ] || exit 0'))
            result = subprocess.run(["sh", "-c", script], timeout=5, capture_output=True,
                                    text=True, env={"PATH": os.defpath,
                                    "PLOW_AGENT_TOKEN": "inherited-token-must-not-reach-reporter"})
            calls = [json.loads(line) for line in record.read_text().splitlines()] if record.exists() else []
            return calls, result

    def test_no_agent_id_never_invokes_client(self):
        calls, result = self.run_service(agent="")
        self.assertEqual(calls, [])
        self.assertIn("disabled", result.stderr)

    def test_valid_state_only_reports_with_clean_environment(self):
        calls, _ = self.run_service(status=0)
        self.assertEqual([c["args"] for c in calls], [["status"], []])
        self.assertTrue(all("PLOW_AGENT_TOKEN" not in c["env"] for c in calls))

    def test_unregistered_bootstrap_gets_token_but_reporting_does_not(self):
        calls, _ = self.run_service(status=3)
        self.assertEqual([c["args"] for c in calls],
                         [["status"], ["--register", "--agent", "synthetic-pruce"], []])
        self.assertEqual(calls[1]["env"]["PLOW_AGENT_TOKEN"], "synthetic-plow-token")
        self.assertEqual(calls[1]["env"]["PLOW_API_BASE"], "https://example.invalid")
        self.assertNotIn("PLOW_AGENT_TOKEN", calls[2]["env"])

    def test_corrupt_state_neither_registers_nor_reports(self):
        calls, result = self.run_service(status=2)
        self.assertEqual([c["args"] for c in calls], [["status"]])
        self.assertIn("unreadable", result.stderr)

    def test_failed_registration_never_reports(self):
        calls, result = self.run_service(status=3, registration_exit=1)
        self.assertEqual(len(calls), 2)
        self.assertIn("not reporting", result.stderr)

    def test_valid_install_reports_on_subsequent_cycles_without_registration(self):
        calls, _ = self.run_service(status=0, cycles=2)
        self.assertEqual([c["args"] for c in calls], [["status"], [], ["status"], []])


if __name__ == "__main__":
    unittest.main()
