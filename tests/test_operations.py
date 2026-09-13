import concurrent.futures
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "skills/pruce-tasks/scripts/operations.py"
spec = importlib.util.spec_from_file_location("pruce_operations", SCRIPT)
operations = importlib.util.module_from_spec(spec)
spec.loader.exec_module(operations)


class OperationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "pruce/operations.json"
        self.payload = {"application_id": 42, "document_sha256": "a" * 64}

    def prepare(self, intent_id="application:send:v1", **extra):
        data = {
            "intent_id": intent_id,
            "task_id": "task-123",
            "action": "Enviar candidatura",
            "target": "Portal da empresa — vaga 42",
            "payload": self.payload,
            "authorization": {"kind": "user_confirmation",
                              "detail": "Usuário confirmou o envio desta candidatura."},
        }
        data.update(extra)
        return operations.run(self.path, "prepare", data)

    def result(self, detail="Serviço confirmou o efeito no alvo esperado."):
        return {"kind": "tool_result", "detail": detail}

    def begin(self, operation, payload=None):
        return operations.run(self.path, "begin", {
            "id": operation["id"], "payload": self.payload if payload is None else payload,
        })

    def test_fresh_read_creates_nothing(self):
        self.assertEqual(operations.run(self.path, "read"), {"operations": []})
        self.assertFalse(self.path.exists())

    def test_prepare_is_idempotent_and_scope_is_immutable(self):
        first = self.prepare()
        self.assertEqual(self.prepare()["id"], first["id"])
        self.assertEqual(first["idempotency_key"], operations.operation_key(
            first["intent_id"], first["action"], first["target"], first["payload_sha256"]))
        with self.assertRaisesRegex(ValueError, "different operation or authorization"):
            self.prepare(action="Enviar candidatura alterada")
        with self.assertRaisesRegex(ValueError, "different operation or authorization"):
            self.prepare(payload={"application_id": 43, "document_sha256": "a" * 64})
        with self.assertRaisesRegex(ValueError, "different operation or authorization"):
            self.prepare(authorization={"kind": "user_instruction", "detail": "Outro pedido."})
        self.assertEqual(len(operations.read(self.path)["operations"]), 1)
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_payload_hash_is_canonical_and_raw_payload_is_not_persisted(self):
        first = self.prepare(payload={"subject": "Olá", "body": "Texto"})
        second = self.prepare(payload={"body": "Texto", "subject": "Olá"})
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(first["payload_sha256"], operations.payload_digest(
            {"subject": "Olá", "body": "Texto"}))
        self.assertNotIn("payload", first)
        self.assertNotIn("Texto", self.path.read_text())

    def test_new_deliberate_effect_needs_a_new_intent_id(self):
        first = self.prepare()
        second = self.prepare("application:send:v2")
        self.assertNotEqual(first["id"], second["id"])
        self.assertNotEqual(first["idempotency_key"], second["idempotency_key"])

    def test_prepare_requires_explicit_authorization_record(self):
        with self.assertRaises(ValueError):
            operations.run(self.path, "prepare", {
                "intent_id": "x", "action": "Enviar", "target": "destino", "payload": {},
            })
        self.assertFalse(self.path.exists())

    def test_caller_cannot_supply_an_arbitrary_idempotency_key(self):
        with self.assertRaisesRegex(ValueError, "unknown fields"):
            self.prepare(idempotency_key="new-key-to-bypass-a-success")

    def test_success_blocks_duplicate_execution(self):
        operation = self.prepare()
        started = self.begin(operation)
        self.assertEqual((started["status"], started["attempt"]), ("in_flight", 1))
        finished = operations.run(self.path, "finish", {
            "id": operation["id"], "status": "succeeded", "result": self.result(),
        })
        self.assertEqual(finished["status"], "succeeded")
        with self.assertRaisesRegex(ValueError, "refusing duplicate"):
            self.begin(operation)

    def test_in_flight_or_ambiguous_result_blocks_retry_until_reconciled(self):
        operation = self.prepare()
        self.begin(operation)
        with self.assertRaisesRegex(ValueError, "reconciled"):
            self.begin(operation)
        operations.run(self.path, "finish", {
            "id": operation["id"], "status": "ambiguous",
            "result": self.result("A conexão caiu após o envio; efeito desconhecido."),
        })
        with self.assertRaisesRegex(ValueError, "reconciled"):
            self.begin(operation)
        reconciled = operations.run(self.path, "reconcile", {
            "id": operation["id"], "status": "succeeded",
            "result": {"kind": "authoritative_check",
                       "detail": "Consulta ao portal encontrou a candidatura 42 enviada."},
        })
        self.assertEqual(reconciled["status"], "succeeded")

    def test_safe_failure_can_retry_same_operation_and_counts_attempts(self):
        operation = self.prepare()
        self.begin(operation)
        operations.run(self.path, "finish", {
            "id": operation["id"], "status": "failed_safe",
            "result": self.result("Validação local falhou antes de qualquer envio."),
        })
        retried = self.begin(operation)
        self.assertEqual((retried["status"], retried["attempt"]), ("in_flight", 2))

    def test_cannot_report_success_before_begin(self):
        operation = self.prepare()
        with self.assertRaisesRegex(ValueError, "in-flight"):
            operations.run(self.path, "finish", {
                "id": operation["id"], "status": "succeeded", "result": self.result(),
            })

    def test_begin_rejects_payload_drift_and_leaves_operation_prepared(self):
        operation = self.prepare()
        with self.assertRaisesRegex(ValueError, "payload differs"):
            self.begin(operation, {"application_id": 43, "document_sha256": "a" * 64})
        saved = operations.read(self.path)["operations"][0]
        self.assertEqual((saved["status"], saved["attempt"]), ("prepared", 0))

    def test_finish_and_reconcile_require_evidence_from_the_right_stage(self):
        operation = self.prepare()
        self.begin(operation)
        with self.assertRaisesRegex(ValueError, "attempted tool call"):
            operations.run(self.path, "finish", {
                "id": operation["id"], "status": "succeeded",
                "result": {"kind": "user_confirmation", "detail": "Acho que foi."},
            })
        operations.run(self.path, "finish", {
            "id": operation["id"], "status": "ambiguous",
            "result": self.result("Timeout depois do envio."),
        })
        with self.assertRaisesRegex(ValueError, "authoritative check"):
            operations.run(self.path, "reconcile", {
                "id": operation["id"], "status": "succeeded", "result": self.result(),
            })

    def test_corrupt_ledger_is_not_reset(self):
        self.prepare()
        for raw in ("{broken", '{"operations":[],"operations":[]}'):
            self.path.write_text(raw)
            with self.assertRaises(ValueError):
                self.prepare("another")
            self.assertEqual(self.path.read_text(), raw)

    def test_failed_publish_preserves_previous_ledger(self):
        self.prepare()
        before = self.path.read_bytes()
        with patch.object(operations.os, "replace", side_effect=OSError("simulated failure")):
            with self.assertRaises(OSError):
                self.prepare("another")
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(list(self.path.parent.glob(".operations-*")), [])

    def test_concurrent_prepare_with_same_intent_creates_one_record(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
            records = list(executor.map(lambda _index: self.prepare(), range(12)))
        self.assertEqual(len({record["id"] for record in records}), 1)
        self.assertEqual(len(operations.read(self.path)["operations"]), 1)

    def test_cli_treats_external_text_as_data(self):
        target = "portal $(touch /tmp/not-executed) `id`\n'alvo'"
        payload = {
            "intent_id": "literal-data", "action": "Enviar formulário",
            "target": target,
            "payload": {"body": "$(touch /tmp/not-executed)"},
            "authorization": {"kind": "user_instruction", "detail": "Pedido explícito."},
        }
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "prepare", "--state", str(self.path)],
            input=json.dumps(payload), text=True, capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(operations.read(self.path)["operations"][0]["target"], target)

    def test_cli_rejects_bad_input_without_echoing_it(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "prepare", "--state", str(self.path)],
            input="PRIVATE_INVALID_CONTENT", text=True, capture_output=True,
        )
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("PRIVATE", result.stderr)


if __name__ == "__main__":
    unittest.main()
