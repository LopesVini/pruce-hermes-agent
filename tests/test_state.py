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

    def normalize(self, raw, captured_at="2026-09-13T17:00:00-03:00",
                  timezone="America/Sao_Paulo", **extra):
        return state.run(self.path, "normalize-time", {
            "raw": raw, "captured_at": captured_at, "capture_basis": "message_timestamp",
            "timezone": timezone, "source": "user", **extra,
        })

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
        temporal = self.normalize("sábado", captured_at="2026-09-12T10:00:00-03:00")
        updated = state.run(self.path, "update", {"id": task["id"], "temporal": temporal})
        self.assertEqual(updated["next_step"], task["next_step"])
        self.assertEqual(updated["title"], task["title"])

    def test_tomorrow_is_anchored_and_does_not_move_next_day(self):
        temporal = self.normalize("vence amanhã")
        self.assertEqual(temporal["kind"], "date")
        self.assertEqual(temporal["value"], "2026-09-14")
        self.assertEqual(state.temporal_status({
            "temporal": temporal, "now": "2026-09-14T09:00:00-03:00",
        }), {"relation": "today"})
        self.assertEqual(temporal["value"], "2026-09-14")

    def test_tomorrow_at_time_becomes_absolute_datetime(self):
        temporal = self.normalize("amanhã às 18h")
        self.assertEqual(temporal["kind"], "datetime")
        self.assertEqual(temporal["value"], "2026-09-14T18:00:00-03:00")

    def test_explicit_local_date_and_time_becomes_absolute_datetime(self):
        temporal = self.normalize("prazo prorrogado até 21/09 às 18h")
        self.assertEqual(temporal["kind"], "datetime")
        self.assertEqual(temporal["value"], "2026-09-21T18:00:00-03:00")

    def test_explicit_date_at_night_keeps_day_part(self):
        temporal = self.normalize("21/09 à noite")
        self.assertEqual(temporal["kind"], "day_part")
        self.assertEqual(temporal["value"], {"date": "2026-09-21", "part": "night"})

    def test_tomorrow_at_night_preserves_day_part_without_fake_hour(self):
        temporal = self.normalize("amanhã à noite")
        self.assertEqual(temporal["kind"], "day_part")
        self.assertEqual(temporal["value"], {"date": "2026-09-14", "part": "night"})
        self.assertNotIn("time", temporal["value"])

    def test_weekday_from_wednesday_resolves_and_same_day_is_ambiguous(self):
        wednesday = self.normalize("prova sábado", "2026-09-16T12:00:00-03:00")
        self.assertEqual((wednesday["kind"], wednesday["value"]), ("date", "2026-09-19"))
        saturday = self.normalize("prova sábado", "2026-09-19T08:00:00-03:00")
        self.assertEqual(saturday["kind"], "unresolved")
        self.assertEqual(saturday["reason"], "weekday_same_day_ambiguous")
        next_saturday = self.normalize("sábado que vem", "2026-09-19T08:00:00-03:00")
        self.assertEqual(next_saturday["value"], "2026-09-26")

    def test_relative_day_offset_is_anchored_for_future_conditions(self):
        temporal = self.normalize("se não responderem em 3 dias")
        self.assertEqual((temporal["kind"], temporal["value"]), ("date", "2026-09-16"))

    def test_this_week_is_a_date_range(self):
        temporal = self.normalize("essa semana", "2026-09-16T12:00:00-03:00")
        self.assertEqual(temporal["kind"], "date_range")
        self.assertEqual(temporal["value"], {"start": "2026-09-14", "end": "2026-09-20"})

    def test_legacy_relative_due_is_unresolved_only_in_active_view(self):
        task = self.create("Matrícula")
        saved = state.read(self.path)
        saved["tasks"][0].pop("temporal")
        saved["tasks"][0]["due"] = "amanhã à noite"
        self.path.write_text(json.dumps(saved))
        active = state.run(self.path, "active")["tasks"][0]
        self.assertEqual(active["temporal"]["kind"], "unresolved")
        self.assertEqual(active["temporal"]["reason"], "legacy_relative_without_capture")
        self.assertIsNone(active["temporal"]["captured_at"])
        self.assertNotIn("temporal", state.run(self.path, "read")["tasks"][0])
        self.assertEqual(active["id"], task["id"])

    def test_new_relative_due_requires_temporal_metadata(self):
        with self.assertRaisesRegex(ValueError, "anchored temporal metadata"):
            state.run(self.path, "create", {
                "title": "Matrícula", "next_step": "Enviar documentos", "due": "amanhã",
            })
        unresolved = state.temporal_record(
            "amanhã", None, "unknown", None, "unresolved", None,
            "message_timestamp_unavailable", "user", None,
        )
        task = state.run(self.path, "create", {
            "title": "Matrícula", "next_step": "Confirmar a data", "temporal": unresolved,
        })
        self.assertEqual(task["due"], "amanhã")
        self.assertEqual(task["temporal"]["kind"], "unresolved")

    def test_past_deadline_is_not_treated_as_future(self):
        temporal = self.normalize("vence amanhã")
        relation = state.temporal_status({
            "temporal": temporal, "now": "2026-09-15T08:00:00-03:00",
        })
        self.assertEqual(relation, {"relation": "past"})

    def test_normalization_uses_selected_timezone(self):
        captured = "2026-09-14T01:00:00+00:00"
        sao_paulo = self.normalize("amanhã", captured, "America/Sao_Paulo")
        tokyo = self.normalize("amanhã", captured, "Asia/Tokyo")
        self.assertEqual(sao_paulo["value"], "2026-09-14")
        self.assertEqual(tokyo["value"], "2026-09-15")
        unknown = self.normalize("amanhã", captured, None)
        self.assertEqual((unknown["kind"], unknown["reason"]),
                         ("unresolved", "timezone_unknown"))

    def test_external_conflicting_deadline_needs_reconciliation_evidence(self):
        original = self.normalize("a inscrição fecha sexta")
        task = state.run(self.path, "create", {
            "title": "Inscrição", "next_step": "Enviar inscrição", "temporal": original,
        })
        newer = self.normalize("prazo prorrogado até 21/09 às 18h", source="gmail")
        before = self.path.read_bytes()
        with self.assertRaisesRegex(ValueError, "reconciliation evidence"):
            state.run(self.path, "update", {"id": task["id"], "temporal": newer})
        self.assertEqual(self.path.read_bytes(), before)
        newer["evidence"] = {"kind": "tool_result", "detail": "E-mail mais recente anunciou a prorrogação."}
        updated = state.run(self.path, "update", {"id": task["id"], "temporal": newer})
        self.assertEqual(updated["temporal"]["value"], "2026-09-21T18:00:00-03:00")

    def test_open_loop_without_due_still_works(self):
        task = self.create("Cancelar assinatura")
        self.assertIsNone(task["due"])
        self.assertIsNone(task["temporal"])
        self.assertEqual(state.run(self.path, "active")["tasks"][0]["id"], task["id"])

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
