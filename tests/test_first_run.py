"""Safe first-run rehearsal: every write stays under a temporary directory."""
import importlib.util
from pathlib import Path
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "skills/pruce-tasks/scripts/state.py"
spec = importlib.util.spec_from_file_location("pruce_first_run_state", SCRIPT)
state = importlib.util.module_from_spec(spec)
spec.loader.exec_module(state)


class IsolatedFirstRunTests(unittest.TestCase):
    def test_three_beat_profile_resumes_without_active_state_or_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "isolated-hermes/pruce/state.json"

            fresh = state.run(path, "active")
            self.assertFalse(fresh["introduced"])
            self.assertFalse(fresh["onboarding"]["complete"])
            self.assertFalse(path.exists())

            state.run(path, "profile", {
                "introduced": True,
                "profile": {
                    "preferred_name": {"status": "known", "value": "Pessoa Teste"},
                },
            })
            state.run(path, "profile", {"profile": {
                "timezone": {"status": "known", "value": "America/Sao_Paulo",
                             "city": "Belo Horizonte"},
                "university": {"status": "known", "value": "Universidade Teste"},
                "course": {"status": "known", "value": "Curso Teste"},
            }})
            finished = state.run(path, "profile", {"profile": {
                "primary_radar_preference": "university_deadlines",
            }})

            self.assertTrue(finished["onboarding"]["complete"])
            self.assertEqual(state.run(path, "active")["tasks"], [])
            self.assertFalse((Path(directory) / "isolated-hermes/pruce/sources.json").exists())


if __name__ == "__main__":
    unittest.main()
