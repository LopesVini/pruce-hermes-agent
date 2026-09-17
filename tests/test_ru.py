import importlib.util
import json
from datetime import datetime
from pathlib import Path
import tempfile
import sys
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ru = load("ru", "skills/pruce-ru/scripts/menu.py")
state = load("ru_state", "skills/pruce-tasks/scripts/state.py")
NOW = datetime.fromisoformat("2026-09-18T01:00:00+00:00")  # still 17th in BH


def fixture(identifier, day):
    return {"id": identifier, "nome": "Official RU", "cardapios": [{
        "data": day.isoformat() + "T00:00:00.000Z", "refeicoes": [{
            "tipoRefeicao": "Almoço", "pratos": [
                {"tipoPrato": "Prato protéico 1", "descricaoPrato": "Frango"},
                {"tipoPrato": "Prato protéico 3", "descricaoPrato": "Quibe de Cenoura"},
                {"tipoPrato": "Sobremesa 1 (uma porção)", "descricaoPrato": "Banana"}]},
            {"tipoRefeicao": "Jantar", "pratos": [
                {"tipoPrato": "Sobremesa 1 (uma porção)", "descricaoPrato": "Laranja"}]}]}]}


class RUTests(unittest.TestCase):
    def test_bandejao_today_returns_only_useful_text_without_internal_preamble(self):
        leaked = ('"Bandejão" here without an RU specified — I already have today\'s '
                  'data for RU I and RU II from earlier in this conversation, no need to re-fetch.')
        self.assertEqual(self.query()['text'],
                         'Qual RU você usa: I, II, Saúde, Direito ou ICA?')
        self.fetch.assert_not_called()
        state.run(self.path, 'profile', {'profile': {'preferred_ru': 'setorial_2'}})
        result = self.query()
        self.assertTrue(result['text'].startswith('🍽️ RU II — almoço de 17/09/2026\n'))
        self.assertNotIn(leaked, result['text'])
        for internal in ('re-fetch', 'cache', 'pruce-ru', 'skill', 'tool', 'here without'):
            self.assertNotIn(internal, result['text'])
        self.assertEqual(self.fetch.call_count, 1)

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "state.json"
        self.fetch = Mock(side_effect=fixture)

    def query(self, **kwargs):
        return ru.query(state_path=self.path, now=NOW, fetch=self.fetch, **kwargs)

    def test_ru_i_today_live_local_date(self):
        result = self.query(ru="RU I")
        self.assertEqual(result["date"], "2026-09-17")
        self.assertEqual(result["ru"], "setorial_1")
        self.assertEqual(self.fetch.call_args.args[0], 6)
        self.assertEqual(self.fetch.call_count, 1)
        self.assertFalse(self.path.exists())

    def test_ru_ii_tomorrow(self):
        result = self.query(ru="RU II", when="amanhã")
        self.assertEqual(result["date"], "2026-09-18")
        self.assertEqual(self.fetch.call_args.args[0], 1)

    def test_all_aliases_and_canonical_ids(self):
        for alias, canonical in {**ru.ALIASES, **{key: key for key in ru.RESTAURANTS}}.items():
            with self.subTest(alias=alias):
                self.assertEqual(ru.resolve_ru(alias), canonical)
        self.assertEqual(ru.resolve_ru("  RU SAÚDE  "), "saude")

    def test_saude_direito_ica(self):
        for alias, identifier, canonical in (("Saúde", 2, "saude"),
                ("RU Direito", 2, "direito"), ("Montes Claros", 5, "ica")):
            result = self.query(ru=alias)
            self.assertEqual(result["ru"], canonical)
            self.assertEqual(self.fetch.call_args.args[0], identifier)
            if identifier == 2:
                self.assertIn("conjunto Saúde/Direito", result["text"])

    def test_missing_ru_asks_without_network_or_state_write(self):
        self.assertEqual(self.query()["status"], "ru_required")
        self.fetch.assert_not_called()
        self.assertFalse(self.path.exists())

    def test_preference_and_explicit_override_preserve_tasks_and_profile(self):
        task = state.run(self.path, "create", {"title": "Existing", "next_step": "Do it"})
        state.run(self.path, "profile", {"context": "Keep", "introduced": True})
        before = state.run(self.path, "read")
        state.run(self.path, "profile", {"profile": {"preferred_ru": "setorial_2"}})
        after = state.run(self.path, "read")
        self.assertEqual(after["tasks"], before["tasks"])
        self.assertEqual(after["context"], "Keep")
        self.assertTrue(after["introduced"])
        self.assertEqual(after["onboarding"]["complete"], before["onboarding"]["complete"])
        self.assertEqual(after["onboarding"]["remaining"], before["onboarding"]["remaining"])
        raw = self.path.read_bytes()
        self.assertEqual(self.query()["ru"], "setorial_2")
        self.assertEqual(self.query(ru="RU I")["ru"], "setorial_1")
        self.assertEqual(self.path.read_bytes(), raw)
        state.run(self.path, "profile", {"profile": {"preferred_ru": None}})
        self.assertEqual(self.query()["status"], "ru_required")

    def test_old_profile_remains_valid_and_bad_preference_rejected(self):
        state.validate_profile(state.default_profile())
        for value in ("ru 2", "unknown", [], 1):
            with self.assertRaises(ValueError):
                state.run(self.path, "profile", {"profile": {"preferred_ru": value}})

    def test_no_menu_and_missing_meal(self):
        self.fetch.side_effect = lambda identifier, day: {"id": identifier, "cardapios": []}
        self.assertEqual(self.query(ru="RU I")["status"], "not_published")
        self.fetch.side_effect = fixture
        original = fixture(6, ru.resolve_date("hoje", NOW))
        original["cardapios"][0]["refeicoes"] = []
        self.fetch.side_effect = lambda *args: original
        self.assertEqual(self.query(ru="RU I")["status"], "not_published")

    def test_source_failure_schema_identity_and_date_mismatch(self):
        for value in (OSError("timeout"), ValueError("json"), {},
                      {"id": 1, "cardapios": []}, {"id": 6, "cardapios": None},
                      fixture(6, ru.resolve_date("amanhã", NOW))):
            self.fetch.side_effect = value if isinstance(value, Exception) else lambda *args: value
            result = self.query(ru="RU I")
            self.assertEqual(result["status"], "source_unavailable")
            self.assertNotIn("items", result)

    def test_subset_meal_explicit_dates_and_no_vegetarian_certification(self):
        result = self.query(ru="RU I", field="sobremesa", when="17/09/2026")
        self.assertEqual([i["descricao"] for i in result["items"]], ["Banana"])
        self.assertNotIn("Frango", result["text"])
        result = self.query(ru="RU I", meal="jantar", when="2026-09-17")
        self.assertEqual(result["items"][0]["descricao"], "Laranja")
        result = self.query(ru="RU I", field="vegetariano")
        self.assertIn("Quibe de Cenoura", result["text"])
        self.assertIn("não informa ingredientes", result["text"])

    def test_invalid_date_never_fetches(self):
        self.assertEqual(self.query(ru="RU I", when="31/02/2026")["status"], "invalid_request")
        self.fetch.assert_not_called()

    def test_corrupt_state_not_reset_explicit_ru_still_works(self):
        self.path.write_text("broken")
        self.assertEqual(self.query()["status"], "invalid_request")
        self.fetch.assert_not_called()
        self.assertEqual(self.query(ru="RU I")["status"], "ok")
        self.assertEqual(self.path.read_text(), "broken")

    def test_http_get_contract_timeout_and_exact_one_day(self):
        response = Mock()
        response.read.return_value = b'{"id": 6, "cardapios": []}'
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        with patch.object(ru, "urlopen", return_value=response) as request:
            ru.fetch_menu(6, ru.resolve_date("hoje", NOW))
        url = request.call_args.args[0]
        self.assertEqual(url.get_method(), "GET")
        self.assertEqual(url.full_url, ru.ENDPOINT + "?id=6&dataInicio=2026-09-17&dataFim=2026-09-17")
        self.assertEqual(request.call_args.kwargs["timeout"], 6)

    def test_packaging_and_always_on_route(self):
        self.assertIn("pruce-ru", (ROOT / "runtime/persona.md").read_text())
        self.assertIn("!skills/pruce-ru/scripts/menu.py", (ROOT / ".dockerignore").read_text())
        self.assertIn("/opt/hermes/skills/pruce-ru/scripts/menu.py", (ROOT / "Dockerfile").read_text())
        installed = Path("/opt/hermes/skills/pruce-ru")
        if installed.exists():
            for name in ("SKILL.md", "scripts/menu.py", "scripts/subscription.py", "scripts/daily.py", "scripts/request.py"):
                self.assertEqual((installed / name).read_bytes(),
                                 (ROOT / "skills/pruce-ru" / name).read_bytes())

    @unittest.skipUnless(Path('/opt/hermes/tools/skills_tool.py').exists(),
                         'requires pinned Hermes runtime')
    def test_real_hermes_discovers_and_loads_installed_skill(self):
        sys.path.insert(0, '/opt/hermes')
        from tools import skills_tool
        with patch.object(skills_tool, 'SKILLS_DIR', Path('/opt/hermes/skills')):
            found = [s for s in skills_tool._find_all_skills() if s['name'] == 'pruce-ru']
            self.assertEqual(len(found), 1)
            self.assertIn('future send', found[0]['description'])
            self.assertLessEqual(len(found[0]['description']), 60)
            viewed = skills_tool.skill_view('pruce-ru', preprocess=False)
        self.assertIn('request.py', viewed)
        self.assertIn('preferred_ru', viewed)


if __name__ == "__main__":
    unittest.main()
