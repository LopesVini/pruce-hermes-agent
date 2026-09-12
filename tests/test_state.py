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
            state.run(self.path, "update", {"id": task["id"], "status": status, "evidence": evidence,
                      "next_step": "Nenhuma ação pendente." if status == "completed" else "Aguardar resposta do professor"})
        reopened = state.run(self.path, "update", {"id": task["id"], "status": "needs_action"})
        self.assertIsNone(reopened["evidence"])

    def test_sent_cv_keeps_application_open_until_final_outcome(self):
        task = self.create("Mandar currículo para vaga de estágio")
        pending = state.run(self.path, "update", {
            "id": task["id"], "title": "Candidatura à vaga de estágio",
            "status": "waiting_for_third_party", "next_step": "Aguardar resposta da empresa",
            "evidence": {"kind": "user_confirmation", "detail": "Enviei o currículo e estou esperando eles responderem."},
        })
        self.assertEqual(state.read(self.path)["tasks"], [pending])
        self.assertEqual(pending["status"], "waiting_for_third_party")
        closed = state.run(self.path, "update", {
            "id": task["id"], "status": "completed", "next_step": "Nenhuma ação pendente.",
            "evidence": {"kind": "user_confirmation", "detail": "A empresa encerrou a seleção; minha candidatura terminou."},
        })
        self.assertEqual(closed["status"], "completed")
        self.assertEqual(len(state.read(self.path)["tasks"]), 1)

    def test_completed_rejects_external_wait_and_preserves_saved_state(self):
        task = self.create("Reembolso da compra")
        before = self.path.read_bytes()
        for next_step in (
            "Nenhuma ação pendente; aguardando retorno da empresa",
            "Aguardar resposta da faculdade", "Esperar o estorno da loja",
            "Support will get back to me", "O órgão ainda precisa emitir o documento",
        ):
            with self.subTest(next_step=next_step), self.assertRaisesRegex(ValueError, "waiting_for_third_party"):
                state.run(self.path, "update", {
                    "id": task["id"], "status": "completed", "next_step": next_step,
                    "evidence": {"kind": "user_confirmation", "detail": "Já enviei a solicitação."},
                })
            self.assertEqual(self.path.read_bytes(), before)

    def test_completed_cannot_receive_wait_in_partial_update(self):
        task = self.create("Cancelamento de assinatura")
        state.run(self.path, "update", {
            "id": task["id"], "status": "completed", "next_step": "Nenhuma ação pendente.",
            "evidence": {"kind": "tool_result", "detail": "Serviço confirmou assinatura cancelada, protocolo 123."},
        })
        before = self.path.read_bytes()
        with self.assertRaisesRegex(ValueError, "waiting_for_third_party"):
            state.run(self.path, "update", {"id": task["id"], "next_step": "Aguardar confirmação do suporte"})
        self.assertEqual(self.path.read_bytes(), before)

    def test_user_can_explicitly_stop_tracking_without_success(self):
        task = self.create("Inscrição no programa de estágio")
        closed = state.run(self.path, "update", {
            "id": task["id"], "status": "completed", "next_step": "Nenhuma ação pendente.",
            "evidence": {"kind": "user_confirmation", "detail": "Não quero mais acompanhar essa inscrição."},
        })
        self.assertEqual(closed["status"], "completed")
        self.assertIn("Não quero mais", closed["evidence"]["detail"])

    def test_legacy_completed_wait_is_readable_and_repairable(self):
        task = self.create("Mandar currículo para vaga de estágio")
        legacy = state.read(self.path)
        legacy["tasks"][0].update({
            "status": "completed", "next_step": "Nenhuma ação pendente; aguardando retorno da empresa",
            "evidence": {"kind": "user_confirmation", "detail": "Usuário confirmou que enviou o currículo."},
        })
        self.path.write_text(json.dumps(legacy))
        self.assertEqual(state.read(self.path), legacy)
        fixed = state.run(self.path, "update", {
            "id": task["id"], "title": "Candidatura à vaga de estágio",
            "status": "waiting_for_third_party", "next_step": "Aguardar resposta da empresa",
            "evidence": legacy["tasks"][0]["evidence"],
        })
        self.assertEqual(state.read(self.path)["tasks"], [fixed])
        self.assertEqual(fixed["id"], task["id"])

    def test_active_excludes_completed_with_legacy_wait_without_changing_history(self):
        self.create("Mandar currículo para vaga de estágio")
        legacy = state.read(self.path)
        closed = legacy["tasks"][0]
        closed.update({
            "status": "completed", "next_step": "Nenhuma ação pendente; aguardando retorno da empresa",
            "evidence": {"kind": "user_confirmation", "detail": "Usuário confirmou que enviou o currículo."},
        })
        active_statuses = sorted(state.STATUSES - {"completed"})
        for status in active_statuses:
            legacy["tasks"].append({**closed, "id": status, "title": f"Pendência {status}", "status": status})
        self.path.write_text(json.dumps(legacy))
        before = self.path.read_bytes()
        output = subprocess.check_output([
            sys.executable, str(SCRIPT), "active", "--state", str(self.path)], input=b"")
        active = json.loads(output)["result"]
        self.assertEqual([task["status"] for task in active["tasks"]], active_statuses)
        self.assertNotIn(closed["id"], [task["id"] for task in active["tasks"]])
        self.assertEqual(state.run(self.path, "read"), legacy)
        self.assertEqual(self.path.read_bytes(), before)

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
