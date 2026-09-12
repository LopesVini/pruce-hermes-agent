import concurrent.futures
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "skills/pruce-tasks/scripts/state.py"
spec = importlib.util.spec_from_file_location("pruce_state", SCRIPT)
state = importlib.util.module_from_spec(spec)
spec.loader.exec_module(state)


class StateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "pruce/state.json"

    def create(self, title="Estudar termodinâmica"):
        return state.run(self.path, "create", {"title": title, "next_step": "Receber os tópicos"})

    def test_fresh_read_creates_nothing(self):
        self.assertEqual(state.run(self.path, "read"),
                         {"introduced": False, "context": "", "tasks": []})
        self.assertFalse(self.path.parent.exists())

    def test_profile_and_task_survive_new_process(self):
        state.run(self.path, "profile", {"introduced": True, "context": "Estuda engenharia."})
        task = self.create()
        output = subprocess.check_output([sys.executable, str(SCRIPT), "read", "--state", str(self.path)])
        saved = json.loads(output)["result"]
        self.assertTrue(saved["introduced"])
        self.assertEqual(saved["tasks"][0], task)
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_lifecycle_requires_fresh_evidence_and_reopens(self):
        task = self.create()
        evidence = {"kind": "user_confirmation", "detail": "Usuário confirmou que pediu os tópicos ao professor."}
        for status in ("in_progress", "waiting_for_user", "needs_action"):
            state.run(self.path, "update", {"id": task["id"], "status": status})
        for status in ("waiting_for_third_party", "completed"):
            before = self.path.read_bytes()
            with self.assertRaises(ValueError):
                state.run(self.path, "update", {"id": task["id"], "status": status})
            self.assertEqual(before, self.path.read_bytes())
            evidence = {"kind": "user_confirmation", "detail": "Confirmação explícita do resultado desta etapa."}
            state.run(self.path, "update", {"id": task["id"], "status": status, "evidence": evidence})
        reopened = state.run(self.path, "update", {"id": task["id"], "status": "needs_action"})
        self.assertIsNone(reopened["evidence"])

    def test_invalid_mutations_preserve_existing_state(self):
        task = self.create()
        before = self.path.read_bytes()
        cases = [("profile", {"introduced": "yes"}), ("profile", {"unknown": 1}),
                 ("update", {"id": "missing", "status": "completed"}),
                 ("update", {"id": task["id"], "status": "done"}),
                 ("update", {"id": task["id"], "title": " "}),
                 ("update", {"id": task["id"], "status": []}),
                 ("update", {"id": task["id"], "evidence": {"kind": "guess", "detail": "maybe"}}),
                 ("create", {"title": "", "next_step": "x"})]
        for command, data in cases:
            with self.subTest(data=data), self.assertRaises((ValueError, TypeError)):
                state.run(self.path, command, data)
            self.assertEqual(self.path.read_bytes(), before)

    def test_duplicate_does_not_create_second_open_loop(self):
        self.create()
        with self.assertRaises(ValueError):
            self.create("  ESTUDAR TERMODINÂMICA ")
        self.assertEqual(len(state.read(self.path)["tasks"]), 1)

    def test_partial_update_preserves_other_fields(self):
        task = self.create()
        updated = state.run(self.path, "update", {"id": task["id"], "due": "Sábado; data ainda a confirmar"})
        self.assertEqual(updated["next_step"], task["next_step"])
        self.assertEqual(updated["title"], task["title"])

    def test_corruption_is_not_reset(self):
        self.create()
        for raw in ("{broken", '{"introduced":false}', '{"introduced":NaN}',
                    '{"introduced":true,"introduced":false}'):
            self.path.write_text(raw)
            with self.assertRaises(ValueError):
                state.run(self.path, "profile", {"introduced": True})
            self.assertEqual(self.path.read_text(), raw)

    def test_failed_publish_keeps_previous_file(self):
        self.create()
        before = self.path.read_bytes()
        with patch.object(state.os, "replace", side_effect=OSError("simulated failure")):
            with self.assertRaises(OSError):
                state.run(self.path, "profile", {"introduced": True})
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(list(self.path.parent.glob(".state-*")), [])

    def test_concurrent_writes_do_not_lose_tasks(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
            list(executor.map(lambda i: self.create(f"Pendência {i}"), range(18)))
        self.assertEqual(len(state.read(self.path)["tasks"]), 18)

    def test_cli_rejects_bad_input_without_echoing_it(self):
        result = subprocess.run([sys.executable, str(SCRIPT), "create", "--state", str(self.path)],
                                input="private-content-invalid-json", text=True, capture_output=True)
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("private-content", result.stderr)
        self.assertFalse(self.path.exists())

    def test_literal_user_text_is_data(self):
        title = "Cancelar assinatura $(touch /tmp/not-executed) `id`\n'aspas'"
        result = subprocess.run([sys.executable, str(SCRIPT), "create", "--state", str(self.path)],
                                input=json.dumps({"title": title, "next_step": "Identificar o serviço"}),
                                text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(state.read(self.path)["tasks"][0]["title"], title)


if __name__ == "__main__":
    unittest.main()
